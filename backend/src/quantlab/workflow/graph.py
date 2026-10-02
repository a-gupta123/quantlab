"""LangGraph research workflow.

    validate_dataset -> generate_configs -> run_development -> select_variant
        -> run_holdout -> summarize -> END

Every node is a deterministic Python step that reads/writes PostgreSQL. After
each node a conditional edge routes to:
  * the next node, if the node succeeded;
  * the same node again, if it hit a transient error and has attempts left
    (MAX_NODE_ATTEMPTS per job attempt);
  * `fail`, if the error is permanent (bad data, no eligible variant).
If a transient error persists, the exception escapes the graph. The checkpoint
from the last completed node remains in PostgreSQL, so the next job attempt (or
a user-triggered resume) continues from the failed node instead of restarting.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from quantlab import jobs
from quantlab.db import transaction
from quantlab.engine.backtest import BacktestInputError
from quantlab.models import Dataset, Experiment, ExperimentResult, StrategyConfig, WorkflowRun
from quantlab.services import (
    ExperimentRequest,
    InvalidRequest,
    check_range,
    create_experiment,
    execute_inline_experiment,
)
from quantlab.workflow.events import record_event
from quantlab.workflow.variants import SELECTION_CRITERION, resolve_variants, select_best

MAX_NODE_ATTEMPTS = 2
RECURSION_LIMIT = 30
NODE_ORDER = [
    "validate_dataset",
    "generate_configs",
    "run_development",
    "select_variant",
    "run_holdout",
    "summarize",
]


class TransientError(RuntimeError):
    """A failure worth retrying (database hiccup, storage timeout...)."""


class PermanentError(RuntimeError):
    """A failure no retry can fix (invalid data or configuration)."""


class WorkflowState(TypedDict, total=False):
    workflow_run_id: int
    dataset_id: int
    candidates: list[dict[str, Any]]
    dev_results: list[dict[str, Any]]
    selected: dict[str, Any] | None
    holdout: dict[str, Any] | None
    summary: str | None
    error: dict[str, Any] | None
    attempts: dict[str, dict[str, int]]


@dataclass(frozen=True)
class WorkflowContext:
    job: jobs.ClaimedJob


def _run_row(run_id: int) -> WorkflowRun:
    with transaction() as s:
        run = s.get(WorkflowRun, run_id)
        if run is None:
            raise PermanentError(f"Workflow run {run_id} not found.")
        return run


# ---------------------------------------------------------------- node bodies


def validate_dataset(state: WorkflowState, ctx: WorkflowContext) -> dict:
    run = _run_row(state["workflow_run_id"])
    variants = resolve_variants(run.variant_keys)
    longest = max(v["long_window"] for v in variants)
    with transaction() as s:
        ds = s.get(Dataset, run.dataset_id)
        if ds is None:
            raise PermanentError("Dataset no longer exists.")
        try:
            check_range(s, ds, run.dev_start, run.dev_end, longest, "Development period")
            check_range(s, ds, run.holdout_start, run.holdout_end, longest, "Held-out period")
        except InvalidRequest as exc:
            raise PermanentError(str(exc)) from exc
    return {"dataset_id": ds.id}


def generate_configs(state: WorkflowState, ctx: WorkflowContext) -> dict:
    run = _run_row(state["workflow_run_id"])
    candidates = []
    for v in resolve_variants(run.variant_keys):
        req = ExperimentRequest(
            name=f"WF{run.id} dev {v['label']}",
            dataset_id=run.dataset_id,
            start_date=run.dev_start,
            end_date=run.dev_end,
            initial_capital=run.initial_capital,
            short_window=v["short_window"],
            long_window=v["long_window"],
            fee_bps=run.fee_bps,
            slippage_bps=run.slippage_bps,
            allow_fractional=run.allow_fractional,
            seed=run.seed,
        )
        exp_id = _get_or_create_workflow_experiment(run.id, req, "development")
        candidates.append({**v, "experiment_id": exp_id})
    return {"candidates": candidates}


def _get_or_create_workflow_experiment(run_id: int, req: ExperimentRequest, role: str) -> int:
    with transaction() as s:
        q = select(Experiment).where(Experiment.workflow_run_id == run_id, Experiment.role == role)
        if role == "development":
            q = q.join(Experiment.strategy_config).where(
                StrategyConfig.short_window == req.short_window,
                StrategyConfig.long_window == req.long_window,
            )
        existing = s.scalars(q).first()
        if existing is not None:
            return existing.id
        try:
            exp = create_experiment(s, req, role=role, workflow_run_id=run_id, enqueue=False)
        except InvalidRequest as exc:
            raise PermanentError(str(exc)) from exc
        return exp.id


def _metrics(experiment_id: int) -> dict:
    with transaction() as s:
        res = s.get(ExperimentResult, experiment_id)
        if res is None:
            raise TransientError(f"Result for experiment {experiment_id} is missing.")
        return res.strategy_metrics, res.benchmark_metrics


def run_development(state: WorkflowState, ctx: WorkflowContext) -> dict:
    dev_results = []
    for c in state["candidates"]:
        try:
            execute_inline_experiment(c["experiment_id"], ctx.job)
        except BacktestInputError as exc:
            raise PermanentError(f"{c['label']}: {exc}") from exc
        strat, bench = _metrics(c["experiment_id"])
        dev_results.append(
            {
                "key": c["key"],
                "label": c["label"],
                "short_window": c["short_window"],
                "long_window": c["long_window"],
                "experiment_id": c["experiment_id"],
                "sharpe_ratio": strat["sharpe_ratio"],
                "total_return": strat["total_return"],
                "max_drawdown": strat["max_drawdown"],
                "benchmark_sharpe_ratio": bench["sharpe_ratio"],
                "benchmark_total_return": bench["total_return"],
            }
        )
    return {"dev_results": dev_results}


def select_variant(state: WorkflowState, ctx: WorkflowContext) -> dict:
    best = select_best(state["dev_results"])
    if best is None:
        raise PermanentError("No variant had a defined development Sharpe ratio.")
    with transaction() as s:
        exp = s.get(Experiment, best["experiment_id"])
        s.get(
            WorkflowRun, state["workflow_run_id"]
        ).selected_strategy_config_id = exp.strategy_config_id
    return {"selected": best}


def run_holdout(state: WorkflowState, ctx: WorkflowContext) -> dict:
    run = _run_row(state["workflow_run_id"])
    sel = state["selected"]
    req = ExperimentRequest(
        name=f"WF{run.id} held-out {sel['label']}",
        dataset_id=run.dataset_id,
        start_date=run.holdout_start,
        end_date=run.holdout_end,
        initial_capital=run.initial_capital,
        short_window=sel["short_window"],
        long_window=sel["long_window"],
        fee_bps=run.fee_bps,
        slippage_bps=run.slippage_bps,
        allow_fractional=run.allow_fractional,
        seed=run.seed,
    )
    # The unique index uq_experiments_wf_holdout guarantees one held-out run per workflow.
    exp_id = _get_or_create_workflow_experiment(run.id, req, "holdout")
    try:
        execute_inline_experiment(exp_id, ctx.job)
    except BacktestInputError as exc:
        raise PermanentError(f"Held-out run: {exc}") from exc
    strat, bench = _metrics(exp_id)
    return {
        "holdout": {
            "experiment_id": exp_id,
            "sharpe_ratio": strat["sharpe_ratio"],
            "total_return": strat["total_return"],
            "max_drawdown": strat["max_drawdown"],
            "benchmark_sharpe_ratio": bench["sharpe_ratio"],
            "benchmark_total_return": bench["total_return"],
        }
    }


def _fmt_pct(x):
    return "n/a" if x is None else f"{x * 100:.2f}%"


def _fmt_num(x):
    return "undefined" if x is None else f"{x:.2f}"


def deterministic_summary(run: WorkflowRun, dev: list[dict], sel: dict, hold: dict) -> str:
    lines = [
        "DETERMINISTIC SUMMARY (generated from stored metrics, no language model).",
        f"Development period {run.dev_start} to {run.dev_end}; held-out period "
        f"{run.holdout_start} to {run.holdout_end}.",
        f"Selection rule: {SELECTION_CRITERION}",
        "Development results:",
    ]
    for r in dev:
        lines.append(
            f"- {r['label']}: Sharpe {_fmt_num(r['sharpe_ratio'])}, total return "
            f"{_fmt_pct(r['total_return'])}, max drawdown {_fmt_pct(r['max_drawdown'])}."
        )
    lines += [
        f"Selected: {sel['label']}.",
        f"Held-out (evaluated once): Sharpe {_fmt_num(hold['sharpe_ratio'])}, total return "
        f"{_fmt_pct(hold['total_return'])}, max drawdown {_fmt_pct(hold['max_drawdown'])}; "
        f"buy-and-hold over the same days: Sharpe {_fmt_num(hold['benchmark_sharpe_ratio'])}, "
        f"total return {_fmt_pct(hold['benchmark_total_return'])}.",
        "One held-out period is a single sample; it does not establish future performance.",
    ]
    return "\n".join(lines)


def summarize(state: WorkflowState, ctx: WorkflowContext) -> dict:
    from quantlab import llm

    run_id = state["workflow_run_id"]
    run = _run_row(run_id)
    text = deterministic_summary(run, state["dev_results"], state["selected"], state["holdout"])
    explanation = model = None
    facts = {
        "development": state["dev_results"],
        "selected": state["selected"]["label"],
        "held_out": state["holdout"],
        "selection_rule": SELECTION_CRITERION,
    }
    try:
        explanation, model = llm.explain(facts)
    except llm.LLMUnavailable as exc:
        record_event(run_id, "summarize", "info", f"Optional LLM explanation skipped: {exc}")
    with transaction() as s:
        jobs.lock_owned(s, ctx.job)
        row = s.get(WorkflowRun, run_id)
        row.deterministic_summary = text
        row.llm_explanation = explanation
        row.llm_model = model
    return {"summary": text}


def fail(state: WorkflowState) -> dict:
    err = state.get("error") or {}
    record_event(
        state["workflow_run_id"],
        "fail",
        "failed",
        f"Workflow stopped at {err.get('node')}: {err.get('message')}",
    )
    return {}


# ------------------------------------------------------------ graph assembly


def _guard(name: str, body):
    """Wrap a node body with event logging and error classification."""

    def node(state: WorkflowState, runtime: Runtime[WorkflowContext]) -> dict:
        ctx = runtime.context
        run_id = state["workflow_run_id"]
        attempts = dict(state.get("attempts") or {})
        prev = attempts.get(name)
        count = prev["count"] + 1 if prev and prev["job_attempt"] == ctx.job.attempts else 1
        attempts[name] = {"job_attempt": ctx.job.attempts, "count": count}
        record_event(run_id, name, "started", f"{name} started", count)
        try:
            update = body(state, ctx)
        except jobs.LeaseLost:
            raise
        except (PermanentError, InvalidRequest, ValueError) as exc:
            record_event(run_id, name, "failed", str(exc), count)
            return {
                "error": {"node": name, "message": str(exc), "retryable": False},
                "attempts": attempts,
            }
        except (TransientError, OperationalError) as exc:
            if count < MAX_NODE_ATTEMPTS:
                record_event(run_id, name, "retrying", f"Transient error, retrying: {exc}", count)
                return {
                    "error": {"node": name, "message": str(exc), "retryable": True},
                    "attempts": attempts,
                }
            record_event(
                run_id,
                name,
                "failed",
                f"Transient error persisted after {count} attempts: {exc}",
                count,
            )
            raise
        record_event(
            run_id, name, "completed", f"{name} completed", count, _event_payload(name, update)
        )
        return {**update, "error": None, "attempts": attempts}

    return node


def _event_payload(name: str, update: dict) -> dict | None:
    if name == "run_development":
        return {"dev_results": update["dev_results"]}
    if name == "select_variant":
        return {"selected": update["selected"]}
    if name == "run_holdout":
        return {"holdout": update["holdout"]}
    if name == "generate_configs":
        return {"candidates": [c["key"] for c in update["candidates"]]}
    return None


def _router(name: str, nxt: str):
    def route(state: WorkflowState) -> str:
        err = state.get("error")
        if not err:
            return nxt
        return name if err["retryable"] else "fail"

    return route


BODIES = {
    "validate_dataset": validate_dataset,
    "generate_configs": generate_configs,
    "run_development": run_development,
    "select_variant": select_variant,
    "run_holdout": run_holdout,
    "summarize": summarize,
}


def build_graph(bodies: dict | None = None) -> StateGraph:
    bodies = {**BODIES, **(bodies or {})}
    g = StateGraph(WorkflowState, context_schema=WorkflowContext)
    for name in NODE_ORDER:
        g.add_node(name, _guard(name, bodies[name]))
    g.add_node("fail", fail)
    g.add_edge(START, NODE_ORDER[0])
    for name, nxt in zip(NODE_ORDER, [*NODE_ORDER[1:], END], strict=True):
        g.add_conditional_edges(name, _router(name, nxt), [nxt, name, "fail"])
    g.add_edge("fail", END)
    return g
