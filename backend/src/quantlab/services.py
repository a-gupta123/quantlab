"""Domain operations shared by the API, worker, and research workflow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from quantlab import ENGINE_VERSION, jobs
from quantlab.config import get_settings
from quantlab.datasets import earliest_valid_start, load_bars
from quantlab.db import transaction
from quantlab.engine.backtest import MIN_EVAL_DAYS, BacktestInputError, StrategyParams
from quantlab.engine.rules import RuleSpec
from quantlab.engine.runner import ExperimentSpec, evaluate
from quantlab.models import Dataset, Experiment, PriceBar, StrategyConfig, StrategyVersion
from quantlab.results import has_result, save_result, write_artifact
from quantlab.storage import get_storage


class NotFound(LookupError):
    pass


class InvalidRequest(ValueError):
    pass


@dataclass(frozen=True)
class ExperimentRequest:
    name: str
    dataset_id: int
    start_date: date
    end_date: date
    initial_capital: float
    short_window: int | None
    long_window: int | None
    fee_bps: float
    slippage_bps: float
    allow_fractional: bool = True
    seed: int = 42
    risk_free_rate: float = 0.0
    bootstrap_block_length: int = 20
    bootstrap_resamples: int = 2000
    confidence_level: float = 0.95
    strategy_version_id: int | None = None


def get_or_create_strategy_config(
    session: Session,
    short: int | None,
    long: int | None,
    fee_bps: float,
    slippage_bps: float,
    allow_fractional: bool,
    strategy_version_id: int | None = None,
) -> StrategyConfig:
    values = dict(
        strategy="rules" if strategy_version_id else "ma_crossover",
        short_window=short,
        long_window=long,
        strategy_version_id=strategy_version_id,
        fee_bps=fee_bps,
        slippage_bps=slippage_bps,
        allow_fractional=allow_fractional,
    )
    # Race-safe get-or-create: concurrent inserts of the same params collapse to one row.
    session.execute(pg_insert(StrategyConfig).values(**values).on_conflict_do_nothing())
    return session.scalars(select(StrategyConfig).filter_by(**values)).one()


def rule_spec(version: StrategyVersion) -> RuleSpec:
    return RuleSpec.model_validate(version.spec)


def strategy_params(req: ExperimentRequest, rules: RuleSpec | None) -> StrategyParams:
    return StrategyParams(
        req.short_window,
        req.long_window,
        req.initial_capital,
        req.fee_bps,
        req.slippage_bps,
        req.allow_fractional,
        rules=rules,
    )


def warmup_label(params: StrategyParams) -> str:
    if params.rules:
        return "this strategy's indicators"
    return f"a {params.long_window}-day moving average"


def check_range(
    session: Session,
    dataset: Dataset,
    start: date,
    end: date,
    warmup: int,
    label: str = "",
    what: str | None = None,
) -> None:
    """Pre-flight checks so users get a clear 422 instead of a failed job."""
    prefix = f"{label}: " if label else ""
    if start >= end:
        raise InvalidRequest(f"{prefix}start date must be before end date.")
    if start < dataset.start_date or end > dataset.end_date:
        raise InvalidRequest(
            f"{prefix}dates must fall within the dataset range "
            f"{dataset.start_date} to {dataset.end_date}."
        )
    what = what or f"a {warmup}-day moving average"
    first_valid = earliest_valid_start(session, dataset.id, warmup)
    if first_valid is None:
        raise InvalidRequest(
            f"{prefix}dataset has only {dataset.row_count} bars; {what} needs {warmup} "
            "bars of warm-up."
        )
    if start < first_valid:
        raise InvalidRequest(
            f"{prefix}{what} needs {warmup} trading days before the start date. "
            f"Earliest valid start is {first_valid}."
        )
    n_days = session.scalar(
        select(func.count()).where(
            PriceBar.dataset_id == dataset.id,
            PriceBar.trade_date >= start,
            PriceBar.trade_date <= end,
        )
    )
    if n_days < MIN_EVAL_DAYS:
        raise InvalidRequest(
            f"{prefix}only {n_days} trading days in range; need at least {MIN_EVAL_DAYS}."
        )


def create_experiment(
    session: Session,
    req: ExperimentRequest,
    role: str = "standalone",
    workflow_run_id: int | None = None,
    rerun_of_id: int | None = None,
    enqueue: bool = True,
) -> Experiment:
    dataset = session.get(Dataset, req.dataset_id)
    if dataset is None:
        raise NotFound(f"Dataset {req.dataset_id} not found.")
    rules = None
    if req.strategy_version_id is not None:
        version = session.get(StrategyVersion, req.strategy_version_id)
        if version is None:
            raise NotFound(f"Strategy version {req.strategy_version_id} not found.")
        rules = rule_spec(version)
    params = strategy_params(req, rules)
    try:
        params.validate()
    except BacktestInputError as exc:
        raise InvalidRequest(str(exc)) from exc
    check_range(
        session,
        dataset,
        req.start_date,
        req.end_date,
        params.warmup_bars(),
        what=warmup_label(params),
    )
    cfg = get_or_create_strategy_config(
        session,
        req.short_window,
        req.long_window,
        req.fee_bps,
        req.slippage_bps,
        req.allow_fractional,
        req.strategy_version_id,
    )
    exp = Experiment(
        name=req.name,
        dataset_id=dataset.id,
        strategy_config_id=cfg.id,
        dataset_sha256=dataset.content_sha256,
        engine_version=ENGINE_VERSION,
        seed=req.seed,
        start_date=req.start_date,
        end_date=req.end_date,
        initial_capital=req.initial_capital,
        risk_free_rate=req.risk_free_rate,
        bootstrap_block_length=req.bootstrap_block_length,
        bootstrap_resamples=req.bootstrap_resamples,
        confidence_level=req.confidence_level,
        status="queued",
        role=role,
        workflow_run_id=workflow_run_id,
        rerun_of_id=rerun_of_id,
    )
    session.add(exp)
    session.flush()
    if enqueue:
        jobs.enqueue(session, "backtest", exp.id, get_settings().job_max_attempts)
    return exp


def request_from_experiment(exp: Experiment, name: str | None = None) -> ExperimentRequest:
    cfg = exp.strategy_config
    return ExperimentRequest(
        name=name or exp.name,
        dataset_id=exp.dataset_id,
        start_date=exp.start_date,
        end_date=exp.end_date,
        initial_capital=exp.initial_capital,
        short_window=cfg.short_window,
        long_window=cfg.long_window,
        fee_bps=cfg.fee_bps,
        slippage_bps=cfg.slippage_bps,
        allow_fractional=cfg.allow_fractional,
        seed=exp.seed,
        risk_free_rate=exp.risk_free_rate,
        bootstrap_block_length=exp.bootstrap_block_length,
        bootstrap_resamples=exp.bootstrap_resamples,
        confidence_level=exp.confidence_level,
        strategy_version_id=cfg.strategy_version_id,
    )


def spec_for(exp: Experiment) -> ExperimentSpec:
    cfg = exp.strategy_config
    rules = rule_spec(cfg.strategy_version) if cfg.strategy_version_id else None
    return ExperimentSpec(
        params=StrategyParams(
            cfg.short_window,
            cfg.long_window,
            exp.initial_capital,
            cfg.fee_bps,
            cfg.slippage_bps,
            cfg.allow_fractional,
            rules=rules,
        ),
        start=exp.start_date,
        end=exp.end_date,
        seed=exp.seed,
        risk_free_rate=exp.risk_free_rate,
        bootstrap_block_length=exp.bootstrap_block_length,
        bootstrap_resamples=exp.bootstrap_resamples,
        confidence_level=exp.confidence_level,
    )


def compute_experiment(experiment_id: int) -> tuple[Experiment, dict]:
    """Read inputs in a short transaction, then compute with no transaction open."""
    with transaction() as s:
        exp = s.get(Experiment, experiment_id)
        if exp is None:
            raise NotFound(f"Experiment {experiment_id} not found.")
        dataset = s.get(Dataset, exp.dataset_id)
        if dataset.content_sha256 != exp.dataset_sha256:
            raise BacktestInputError("Dataset content changed since the experiment was created.")
        _ = exp.strategy_config.strategy_version  # load before the session closes
        bars = load_bars(s, exp.dataset_id, exp.end_date)
    return exp, evaluate(bars, spec_for(exp))


def execute_backtest_job(job: jobs.ClaimedJob) -> None:
    """Run one queued backtest and atomically store its result + completion."""
    exp, result = compute_experiment(job.target_id)
    artifact = write_artifact(get_storage(), exp, result)
    with transaction() as s:
        jobs.lock_owned(s, job)  # fencing: abort if our lease was taken over
        save_result(s, exp.id, result, artifact)
        jobs.mark_completed(s, job)


def execute_inline_experiment(experiment_id: int, fence: jobs.ClaimedJob) -> None:
    """Run an experiment owned by a workflow (no separate job row).

    Idempotent: if the result already exists (e.g. after resuming a workflow) it
    is not recomputed. Writes are fenced on the parent workflow job's lease.
    """
    with transaction() as s:
        if has_result(s, experiment_id):
            return
        s.execute(
            Experiment.__table__.update()
            .where(Experiment.id == experiment_id)
            .values(status="running", started_at=func.coalesce(Experiment.started_at, func.now()))
        )
    try:
        exp, result = compute_experiment(experiment_id)
    except BacktestInputError as exc:
        with transaction() as s:
            s.execute(
                Experiment.__table__.update()
                .where(Experiment.id == experiment_id)
                .values(status="failed", error=str(exc))
            )
        raise
    artifact = write_artifact(get_storage(), exp, result)
    with transaction() as s:
        jobs.lock_owned(s, fence)
        save_result(s, experiment_id, result, artifact)
        s.execute(
            Experiment.__table__.update()
            .where(Experiment.id == experiment_id)
            .values(status="completed", completed_at=func.now(), error=None)
        )
