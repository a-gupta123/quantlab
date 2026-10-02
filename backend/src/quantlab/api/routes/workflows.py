from fastapi import APIRouter, HTTPException, status
from sqlalchemy import exists, func, select

from quantlab import jobs
from quantlab.api import schemas
from quantlab.api.deps import Limit, Offset, SessionDep
from quantlab.api.serializers import latest_job, summary_query, to_summary
from quantlab.config import get_settings
from quantlab.models import Dataset, Experiment, Job, StrategyConfig, WorkflowEvent, WorkflowRun
from quantlab.services import InvalidRequest, NotFound
from quantlab.workflow.graph import NODE_ORDER
from quantlab.workflow.runner import create_workflow
from quantlab.workflow.variants import VARIANT_LIBRARY

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


@router.get("/variants", response_model=list[schemas.VariantOut])
def variants():
    return [
        schemas.VariantOut(
            key=k, label=v["label"], short_window=v["short_window"], long_window=v["long_window"]
        )
        for k, v in VARIANT_LIBRARY.items()
    ]


@router.get("", response_model=schemas.Page[schemas.WorkflowSummary])
def list_workflows(session: SessionDep, limit: Limit = 20, offset: Offset = 0):
    with session.begin():
        total = session.scalar(select(func.count()).select_from(WorkflowRun))
        rows = session.execute(
            select(
                WorkflowRun, Dataset.name, StrategyConfig.short_window, StrategyConfig.long_window
            )
            .join(Dataset, Dataset.id == WorkflowRun.dataset_id)
            .outerjoin(StrategyConfig, StrategyConfig.id == WorkflowRun.selected_strategy_config_id)
            .order_by(WorkflowRun.created_at.desc(), WorkflowRun.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
    items = [
        schemas.WorkflowSummary(
            id=r.id,
            name=r.name,
            status=r.status,
            dataset_id=r.dataset_id,
            dataset_name=name,
            created_at=r.created_at,
            selected_label=f"{short}/{long}" if short else None,
        )
        for r, name, short, long in rows
    ]
    return schemas.Page(items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=schemas.WorkflowDetail, status_code=status.HTTP_201_CREATED)
def create(body: schemas.WorkflowCreate, session: SessionDep):
    try:
        with session.begin():
            run = create_workflow(session, **body.model_dump())
    except NotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except InvalidRequest as exc:
        raise HTTPException(422, str(exc)) from exc
    return get_workflow(run.id, session)


def _node_progress(events: list[WorkflowEvent]) -> list[dict]:
    latest: dict[str, WorkflowEvent] = {}
    for e in events:
        if e.node in NODE_ORDER:
            latest[e.node] = e
    return [
        {
            "node": n,
            "status": latest[n].status if n in latest else "pending",
            "attempt": latest[n].attempt if n in latest else 0,
            "message": latest[n].message if n in latest else None,
        }
        for n in NODE_ORDER
    ]


@router.get("/{run_id}", response_model=schemas.WorkflowDetail)
def get_workflow(run_id: int, session: SessionDep):
    with session.begin():
        run = session.get(WorkflowRun, run_id)
        if run is None:
            raise HTTPException(404, f"Workflow {run_id} not found.")
        events = session.scalars(
            select(WorkflowEvent)
            .where(WorkflowEvent.workflow_run_id == run_id)
            .order_by(WorkflowEvent.id)
        ).all()
        exps = session.execute(
            summary_query().where(Experiment.workflow_run_id == run_id).order_by(Experiment.id)
        ).all()
        selected = (
            session.get(StrategyConfig, run.selected_strategy_config_id)
            if run.selected_strategy_config_id
            else None
        )
        job = latest_job(session, workflow_run_id=run_id)
        permanent = session.scalar(
            select(
                exists().where(
                    WorkflowEvent.workflow_run_id == run_id, WorkflowEvent.node == "fail"
                )
            )
        )
        summaries = [to_summary(r) for r in exps]
        return schemas.WorkflowDetail(
            id=run.id,
            name=run.name,
            status=run.status,
            error=run.error,
            dataset=schemas.DatasetOut.model_validate(run.dataset),
            dev_start=run.dev_start,
            dev_end=run.dev_end,
            holdout_start=run.holdout_start,
            holdout_end=run.holdout_end,
            initial_capital=run.initial_capital,
            fee_bps=run.fee_bps,
            slippage_bps=run.slippage_bps,
            allow_fractional=run.allow_fractional,
            seed=run.seed,
            variant_keys=run.variant_keys,
            selection_criterion=run.selection_criterion,
            selected_strategy_config=(
                schemas.StrategyConfigOut.model_validate(selected) if selected else None
            ),
            deterministic_summary=run.deterministic_summary,
            llm_explanation=run.llm_explanation,
            llm_model=run.llm_model,
            created_at=run.created_at,
            completed_at=run.completed_at,
            resumable=run.status == "failed" and not permanent,
            job=schemas.JobOut.model_validate(job) if job else None,
            nodes=_node_progress(events),
            events=[schemas.WorkflowEventOut.model_validate(e) for e in events],
            development=[s for s in summaries if s.role == "development"],
            holdout=next((s for s in summaries if s.role == "holdout"), None),
        )


@router.post(
    "/{run_id}/resume", response_model=schemas.WorkflowDetail, status_code=status.HTTP_202_ACCEPTED
)
def resume(run_id: int, session: SessionDep):
    """Queue a new job that continues from the last LangGraph checkpoint."""
    with session.begin():
        run = session.get(WorkflowRun, run_id, with_for_update=True)
        if run is None:
            raise HTTPException(404, f"Workflow {run_id} not found.")
        if run.status != "failed":
            raise HTTPException(
                409, f"Only failed workflows can be resumed (status: {run.status})."
            )
        if session.scalar(
            select(
                exists().where(
                    WorkflowEvent.workflow_run_id == run_id, WorkflowEvent.node == "fail"
                )
            )
        ):
            raise HTTPException(
                409,
                "This workflow failed validation; resuming cannot fix it. "
                "Start a new workflow with different inputs.",
            )
        active = session.scalar(
            select(
                exists().where(Job.workflow_run_id == run_id, Job.status.in_(("queued", "running")))
            )
        )
        if not active:
            jobs.enqueue(session, "workflow", run_id, get_settings().job_max_attempts)
        run.status = "queued"
        run.error = None
    return get_workflow(run_id, session)
