"""Turn ORM rows into response schemas. Queries live here so routes stay short."""

from __future__ import annotations

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from quantlab.api import schemas
from quantlab.engine.rules import RuleSpec, describe
from quantlab.models import (
    CustomStrategy,
    Dataset,
    Experiment,
    ExperimentResult,
    Job,
    StrategyConfig,
    StrategyMessage,
    StrategyVersion,
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
            CustomStrategy.name.label("rules_name"),
            StrategyVersion.version.label("rules_version"),
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
        .outerjoin(StrategyVersion, StrategyVersion.id == StrategyConfig.strategy_version_id)
        .outerjoin(CustomStrategy, CustomStrategy.id == StrategyVersion.strategy_id)
        .outerjoin(ExperimentResult, ExperimentResult.experiment_id == Experiment.id)
    )


def strategy_label(short: int | None, long: int | None, name: str | None, version: int | None):
    if name is not None:
        return f"{name} (v{version})"
    return f"MA {short}/{long}"


def to_summary(row) -> schemas.ExperimentSummary:
    data = dict(row._mapping)
    name, version = data.pop("rules_name"), data.pop("rules_version")
    data["strategy_label"] = strategy_label(
        data["short_window"], data["long_window"], name, version
    )
    return schemas.ExperimentSummary.model_validate(data)


def latest_job(session: Session, **target) -> Job | None:
    ((col, value),) = target.items()
    return session.scalars(
        select(Job).where(getattr(Job, col) == value).order_by(Job.id.desc()).limit(1)
    ).first()


def strategy_config_out(cfg: StrategyConfig) -> schemas.StrategyConfigOut:
    out = schemas.StrategyConfigOut.model_validate(cfg)
    v = cfg.strategy_version
    if v is not None:
        out.rules = schemas.RulesRef(
            strategy_id=v.strategy_id,
            name=v.strategy.name,
            version=v.version,
            fidelity=v.fidelity,
            rules_text=describe(RuleSpec.model_validate(v.spec)),
        )
    return out


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
        strategy_config=strategy_config_out(exp.strategy_config),
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


def version_out(v: StrategyVersion) -> schemas.StrategyVersionOut:
    spec = RuleSpec.model_validate(v.spec)
    return schemas.StrategyVersionOut(
        id=v.id,
        version=v.version,
        spec=v.spec,
        rules_text=describe(spec),
        requirements=v.requirements,
        fidelity=v.fidelity,
        summary=v.summary,
        assumptions=v.assumptions,
        model=v.model,
        warmup_bars=spec.warmup_bars(),
        created_at=v.created_at,
    )


def strategy_detail(session: Session, strategy_id: int) -> schemas.StrategyDetail | None:
    strat = session.get(CustomStrategy, strategy_id)
    if strat is None:
        return None
    versions = session.scalars(
        select(StrategyVersion)
        .where(StrategyVersion.strategy_id == strategy_id)
        .order_by(StrategyVersion.version)
    ).all()
    messages = session.scalars(
        select(StrategyMessage)
        .where(StrategyMessage.strategy_id == strategy_id)
        .order_by(StrategyMessage.id)
    ).all()
    return schemas.StrategyDetail(
        id=strat.id,
        name=strat.name,
        created_at=strat.created_at,
        updated_at=strat.updated_at,
        versions=[version_out(v) for v in versions],
        messages=[schemas.StrategyMessageOut.model_validate(m) for m in messages],
    )
