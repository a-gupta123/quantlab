"""Execute a workflow job with PostgreSQL-backed LangGraph checkpoints."""

from __future__ import annotations

from contextlib import contextmanager

from langgraph.checkpoint.postgres import PostgresSaver
from sqlalchemy.orm import Session

from quantlab import jobs
from quantlab.config import get_settings
from quantlab.db import transaction
from quantlab.models import Dataset, WorkflowRun
from quantlab.workflow.events import record_event
from quantlab.workflow.graph import RECURSION_LIMIT, WorkflowContext, build_graph
from quantlab.workflow.variants import SELECTION_CRITERION, resolve_variants


def thread_config(run_id: int) -> dict:
    return {"configurable": {"thread_id": f"workflow-{run_id}"}, "recursion_limit": RECURSION_LIMIT}


@contextmanager
def checkpointer():
    with PostgresSaver.from_conn_string(get_settings().psycopg_url) as saver:
        yield saver


def setup_checkpointer() -> None:
    """Create LangGraph's checkpoint tables. Called only by the migrate step."""
    with checkpointer() as saver:
        saver.setup()


def create_workflow(
    session: Session,
    *,
    name: str,
    dataset_id: int,
    dev_start,
    dev_end,
    holdout_start,
    holdout_end,
    initial_capital: float,
    fee_bps: float,
    slippage_bps: float,
    allow_fractional: bool,
    seed: int,
    variant_keys: list[str],
) -> WorkflowRun:
    from quantlab.services import InvalidRequest, NotFound

    if session.get(Dataset, dataset_id) is None:
        raise NotFound(f"Dataset {dataset_id} not found.")
    try:
        resolve_variants(variant_keys)
    except ValueError as exc:
        raise InvalidRequest(str(exc)) from exc
    if not (dev_start < dev_end < holdout_start < holdout_end):
        raise InvalidRequest(
            "Periods must be chronological and disjoint: development start < development end "
            "< held-out start < held-out end."
        )
    run = WorkflowRun(
        name=name,
        dataset_id=dataset_id,
        status="queued",
        dev_start=dev_start,
        dev_end=dev_end,
        holdout_start=holdout_start,
        holdout_end=holdout_end,
        initial_capital=initial_capital,
        fee_bps=fee_bps,
        slippage_bps=slippage_bps,
        allow_fractional=allow_fractional,
        seed=seed,
        variant_keys=list(dict.fromkeys(variant_keys)),
        selection_criterion=SELECTION_CRITERION,
    )
    session.add(run)
    session.flush()
    jobs.enqueue(session, "workflow", run.id, get_settings().job_max_attempts)
    return run


def execute_workflow_job(job: jobs.ClaimedJob, graph_builder=build_graph) -> None:
    from quantlab.worker import NonRetryableError

    run_id = job.target_id
    config = thread_config(run_id)
    ctx = WorkflowContext(job=job)
    with checkpointer() as saver:
        graph = graph_builder().compile(checkpointer=saver)
        snapshot = graph.get_state(config)
        if snapshot.values and snapshot.next:
            record_event(
                run_id,
                "workflow",
                "resumed",
                f"Resuming from checkpoint at {', '.join(snapshot.next)} "
                f"(job attempt {job.attempts}).",
            )
            final = graph.invoke(None, config, context=ctx)
        elif snapshot.values:
            final = snapshot.values  # already finished; only completion bookkeeping remains
        else:
            record_event(run_id, "workflow", "started", f"Workflow started (job {job.id}).")
            final = graph.invoke({"workflow_run_id": run_id, "attempts": {}}, config, context=ctx)

    err = final.get("error")
    if err:
        raise NonRetryableError(f"{err['node']}: {err['message']}")
    with transaction() as s:
        jobs.mark_completed(s, job)
    record_event(run_id, "workflow", "completed", "Workflow completed.")
