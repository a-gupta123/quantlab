"""Turn ORM rows into response schemas. Queries live here so routes stay short."""

from __future__ import annotations

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from quantlab.api import schemas
from quantlab.models import (
    Dataset,
    Experiment,
    ExperimentResult,
    Job,
    StrategyConfig,
    Trade,
)


def summary_query() -> Select:
    sm = ExperimentResult.strategy_metrics
    return (
        select(
            Experiment.id,
            Experiment.name,
            Experiment.status,
            Experiment.role,
            Experiment.workflow_run_id,
            Experiment.dataset_id,
            Dataset.name.label("dataset_name"),
            Dataset.is_synthetic.label("dataset_is_synthetic"),
            StrategyConfig.short_window,
            StrategyConfig.long_window,
            Experiment.start_date,
            Experiment.end_date,
            Experiment.created_at,
            sm["total_return"].as_float().label("total_return"),
            sm["sharpe_ratio"].as_float().label("sharpe_ratio"),
            sm["max_drawdown"].as_float().label("max_drawdown"),
            ExperimentResult.benchmark_metrics["total_return"]
            .as_float()
            .label("benchmark_total_return"),
        )
        .join(Dataset, Dataset.id == Experiment.dataset_id)
        .join(StrategyConfig, StrategyConfig.id == Experiment.strategy_config_id)
        .outerjoin(ExperimentResult, ExperimentResult.experiment_id == Experiment.id)
    )


def to_summary(row) -> schemas.ExperimentSummary:
    return schemas.ExperimentSummary.model_validate(dict(row._mapping))


def latest_job(session: Session, **target) -> Job | None:
    ((col, value),) = target.items()
    return session.scalars(
        select(Job).where(getattr(Job, col) == value).order_by(Job.id.desc()).limit(1)
    ).first()


def experiment_detail(session: Session, exp: Experiment) -> schemas.ExperimentDetail:
    result = session.get(ExperimentResult, exp.id)
    trades = session.scalars(
        select(Trade).where(Trade.experiment_id == exp.id).order_by(Trade.seq)
    ).all()
    job = latest_job(session, experiment_id=exp.id)
    return schemas.ExperimentDetail(
        id=exp.id,
        name=exp.name,
        status=exp.status,
        error=exp.error,
        role=exp.role,
        workflow_run_id=exp.workflow_run_id,
        rerun_of_id=exp.rerun_of_id,
        dataset=schemas.DatasetOut.model_validate(exp.dataset),
        strategy_config=schemas.StrategyConfigOut.model_validate(exp.strategy_config),
        dataset_sha256=exp.dataset_sha256,
        engine_version=exp.engine_version,
        seed=exp.seed,
        start_date=exp.start_date,
        end_date=exp.end_date,
        initial_capital=exp.initial_capital,
        risk_free_rate=exp.risk_free_rate,
        bootstrap_block_length=exp.bootstrap_block_length,
        bootstrap_resamples=exp.bootstrap_resamples,
        confidence_level=exp.confidence_level,
        created_at=exp.created_at,
        started_at=exp.started_at,
        completed_at=exp.completed_at,
        job=schemas.JobOut.model_validate(job) if job else None,
        result=schemas.ResultOut.model_validate(result) if result else None,
        trades=[schemas.TradeOut.model_validate(t) for t in trades],
    )
