import json
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select, text

from quantlab import inline
from quantlab.api import schemas
from quantlab.api.deps import Limit, Offset, SessionDep
from quantlab.api.serializers import experiment_detail, summary_query, to_summary
from quantlab.config import get_settings
from quantlab.models import Experiment, ExperimentResult, Job, Worker
from quantlab.services import (
    ExperimentRequest,
    InvalidRequest,
    NotFound,
    create_experiment,
    request_from_experiment,
)
from quantlab.storage import StorageError, get_storage

router = APIRouter(prefix="/api/experiments", tags=["experiments"])

StatusFilter = Annotated[schemas.Status | None, Query()]


def _escape_like(q: str) -> str:
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("", response_model=schemas.Page[schemas.ExperimentSummary])
def list_experiments(
    session: SessionDep,
    limit: Limit = 20,
    offset: Offset = 0,
    q: Annotated[str | None, Query(max_length=100)] = None,
    status_: Annotated[schemas.Status | None, Query(alias="status")] = None,
    dataset_id: Annotated[int | None, Query(gt=0)] = None,
    include_workflow: bool = False,
):
    filters = []
    if q and q.strip():
        filters.append(Experiment.name.ilike(f"%{_escape_like(q.strip())}%", escape="\\"))
    if status_:
        filters.append(Experiment.status == status_)
    if dataset_id:
        filters.append(Experiment.dataset_id == dataset_id)
    if not include_workflow:
        filters.append(Experiment.role == "standalone")
    with session.begin():
        total = session.scalar(select(func.count()).select_from(Experiment).where(*filters))
        rows = session.execute(
            summary_query()
            .where(*filters)
            .order_by(Experiment.created_at.desc(), Experiment.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
    return schemas.Page(
        items=[to_summary(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.get("/stats", response_model=schemas.StatsOut)
def stats(session: SessionDep):
    with session.begin():
        counts = dict(
            session.execute(
                select(Experiment.status, func.count())
                .where(Experiment.role == "standalone")
                .group_by(Experiment.status)
            ).all()
        )
        sharpe = ExperimentResult.strategy_metrics["sharpe_ratio"].as_float()
        best = session.execute(
            summary_query()
            .where(
                Experiment.role == "standalone",
                Experiment.status == "completed",
                sharpe.is_not(None),
            )
            .order_by(sharpe.desc())
            .limit(1)
        ).first()
        online = session.scalar(
            select(func.count())
            .select_from(Worker)
            .where(Worker.last_seen_at > func.now() - text("interval '60 seconds'"))
        )
    return schemas.StatsOut(
        total=sum(counts.values()),
        by_status={s: counts.get(s, 0) for s in ("queued", "running", "completed", "failed")},
        best_sharpe=to_summary(best) if best else None,
        workers_online=online,
        execution_mode=get_settings().job_execution,
    )


@router.post("", response_model=schemas.ExperimentDetail, status_code=status.HTTP_201_CREATED)
def create(body: schemas.ExperimentCreate, session: SessionDep):
    try:
        with session.begin():
            exp = create_experiment(session, ExperimentRequest(**body.model_dump()))
    except NotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except InvalidRequest as exc:
        raise HTTPException(422, str(exc)) from exc
    if inline.drain():
        session.expire_all()
    with session.begin():
        return experiment_detail(session, session.get(Experiment, exp.id))


@router.get("/compare", response_model=schemas.CompareOut)
def compare(session: SessionDep, ids: Annotated[str, Query(max_length=60)]):
    try:
        id_list = list(dict.fromkeys(int(x) for x in ids.split(",") if x.strip()))
    except ValueError as exc:
        raise HTTPException(422, "ids must be a comma-separated list of integers.") from exc
    if not 2 <= len(id_list) <= 3:
        raise HTTPException(422, "Select two or three experiments to compare.")
    with session.begin():
        exps = session.scalars(select(Experiment).where(Experiment.id.in_(id_list))).all()
        found = {e.id: e for e in exps}
        missing = [i for i in id_list if i not in found]
        if missing:
            raise HTTPException(404, f"Experiment(s) not found: {missing}")
        details = [experiment_detail(session, found[i]) for i in id_list]
    not_done = [d.id for d in details if d.result is None]
    if not_done:
        raise HTTPException(422, f"Experiment(s) {not_done} have no completed result yet.")
    periods = {(d.result.eval_start, d.result.eval_end) for d in details}
    hashes = {d.dataset_sha256 for d in details}
    if len(periods) > 1 or len(hashes) > 1:
        raise HTTPException(
            422,
            "Comparison requires the same dataset version and the same evaluation period. "
            f"Found periods {sorted(str(p) for p in periods)} across {len(hashes)} dataset(s).",
        )
    ((start, end),) = periods
    return schemas.CompareOut(
        eval_start=start, eval_end=end, dataset_sha256=hashes.pop(), experiments=details
    )


@router.get("/{experiment_id}", response_model=schemas.ExperimentDetail)
def get_experiment(experiment_id: int, session: SessionDep):
    inline.drain()
    with session.begin():
        exp = session.get(Experiment, experiment_id)
        if exp is None:
            raise HTTPException(404, f"Experiment {experiment_id} not found.")
        return experiment_detail(session, exp)


@router.get("/{experiment_id}/artifact")
def get_artifact(experiment_id: int, session: SessionDep):
    with session.begin():
        res = session.get(ExperimentResult, experiment_id)
        if res is None or not res.artifact_key:
            raise HTTPException(404, "No stored artifact for this experiment.")
        key = res.artifact_key
    try:
        data = get_storage().get_bytes(key)
    except StorageError as exc:
        raise HTTPException(502, f"Artifact storage error: {exc}") from exc
    return Response(
        content=json.dumps(json.loads(data)),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="experiment-{experiment_id}.json"'},
    )


@router.post(
    "/{experiment_id}/rerun",
    response_model=schemas.ExperimentDetail,
    status_code=status.HTTP_201_CREATED,
)
def rerun(experiment_id: int, session: SessionDep):
    """An explicit rerun is a new, separately recorded experiment."""
    try:
        with session.begin():
            src = session.get(Experiment, experiment_id)
            if src is None:
                raise NotFound(f"Experiment {experiment_id} not found.")
            if src.role != "standalone":
                raise InvalidRequest(
                    "Workflow experiments cannot be rerun individually; "
                    "start a new workflow instead."
                )
            req = request_from_experiment(src, name=f"{src.name} (rerun)"[:120])
            new = create_experiment(session, req, rerun_of_id=src.id)
    except NotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except InvalidRequest as exc:
        raise HTTPException(422, str(exc)) from exc
    if inline.drain():
        session.expire_all()
    with session.begin():
        return experiment_detail(session, session.get(Experiment, new.id))


@router.delete("/{experiment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(experiment_id: int, session: SessionDep):
    with session.begin():
        exp = session.get(Experiment, experiment_id, with_for_update=True)
        if exp is None:
            raise HTTPException(404, f"Experiment {experiment_id} not found.")
        if exp.role != "standalone":
            raise HTTPException(
                409,
                f"Experiment belongs to workflow {exp.workflow_run_id}; "
                "it is kept as part of that workflow's record.",
            )
        running = session.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.experiment_id == exp.id, Job.status == "running")
        )
        if running:
            raise HTTPException(409, "Experiment is running; wait for it to finish.")
        # Database-level ON DELETE CASCADE removes results, trades, and queued jobs.
        session.execute(sql_delete(Experiment).where(Experiment.id == exp.id))
    return Response(status_code=204)
