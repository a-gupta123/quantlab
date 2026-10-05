"""SQLAlchemy ORM models. The Alembic migration in `alembic/versions` is the
source of truth for the schema; these classes mirror it for querying."""

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

RUN_STATUSES = ("queued", "running", "completed", "failed")
_status_check = "status IN ('queued', 'running', 'completed', 'failed')"


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSONB, list[Any]: JSONB}


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Dataset(Base):
    __tablename__ = "datasets"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_datasets_name_version"),
        CheckConstraint("version >= 1", name="ck_datasets_version"),
        CheckConstraint("row_count > 0", name="ck_datasets_row_count"),
        CheckConstraint("start_date <= end_date", name="ck_datasets_dates"),
        CheckConstraint(
            "adjustment IN ('adjusted', 'split_adjusted', 'unadjusted', 'synthetic')",
            name="ck_datasets_adjustment",
        ),
        CheckConstraint("char_length(content_sha256) = 64", name="ck_datasets_sha_len"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False)
    adjustment: Mapped[str] = mapped_column(String(20), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    manifest: Mapped[dict[str, Any]] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = _created()


class PriceBar(Base):
    __tablename__ = "price_bars"
    __table_args__ = (
        CheckConstraint(
            "open > 0 AND high > 0 AND low > 0 AND close > 0", name="ck_price_bars_positive"
        ),
        CheckConstraint(
            "high >= low AND high >= open AND high >= close AND low <= open AND low <= close",
            name="ck_price_bars_ohlc",
        ),
        CheckConstraint("volume IS NULL OR volume >= 0", name="ck_price_bars_volume"),
    )

    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), primary_key=True
    )
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float | None] = mapped_column(Float)


class StrategyConfig(Base):
    __tablename__ = "strategy_configs"
    __table_args__ = (
        UniqueConstraint(
            "strategy",
            "short_window",
            "long_window",
            "fee_bps",
            "slippage_bps",
            "allow_fractional",
            name="uq_strategy_configs_params",
        ),
        CheckConstraint(
            "strategy IN ('ma_crossover', 'rules')", name="ck_strategy_configs_strategy"
        ),
        CheckConstraint(
            "(strategy = 'ma_crossover' AND strategy_version_id IS NULL AND short_window >= 1 "
            "AND short_window < long_window AND long_window <= 400) OR "
            "(strategy = 'rules' AND strategy_version_id IS NOT NULL AND short_window IS NULL "
            "AND long_window IS NULL)",
            name="ck_strategy_configs_kind",
        ),
        Index(
            "uq_strategy_configs_rules",
            "strategy_version_id",
            "fee_bps",
            "slippage_bps",
            "allow_fractional",
            unique=True,
            postgresql_where=text("strategy = 'rules'"),
        ),
        CheckConstraint("fee_bps >= 0 AND fee_bps <= 500", name="ck_strategy_configs_fee"),
        CheckConstraint(
            "slippage_bps >= 0 AND slippage_bps <= 500", name="ck_strategy_configs_slippage"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    strategy: Mapped[str] = mapped_column(String(32), nullable=False, default="ma_crossover")
    short_window: Mapped[int | None] = mapped_column(Integer)
    long_window: Mapped[int | None] = mapped_column(Integer)
    strategy_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("strategy_versions.id", ondelete="RESTRICT")
    )
    fee_bps: Mapped[float] = mapped_column(Float, nullable=False)
    slippage_bps: Mapped[float] = mapped_column(Float, nullable=False)
    allow_fractional: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = _created()

    strategy_version: Mapped["StrategyVersion | None"] = relationship()


class CustomStrategy(Base):
    """A conversation with the strategy chatbot and the versions it produced."""

    __tablename__ = "custom_strategies"
    __table_args__ = (Index("ix_custom_strategies_updated_at", "updated_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    versions: Mapped[list["StrategyVersion"]] = relationship(
        back_populates="strategy", order_by="StrategyVersion.version"
    )
    messages: Mapped[list["StrategyMessage"]] = relationship(order_by="StrategyMessage.id")


class StrategyVersion(Base):
    """An immutable, validated RuleSpec. Experiments pin a version, never a strategy."""

    __tablename__ = "strategy_versions"
    __table_args__ = (
        UniqueConstraint("strategy_id", "version", name="uq_strategy_versions_strategy_version"),
        CheckConstraint("version >= 1", name="ck_strategy_versions_version"),
        CheckConstraint("fidelity >= 0 AND fidelity <= 100", name="ck_strategy_versions_fidelity"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    strategy_id: Mapped[int] = mapped_column(
        ForeignKey("custom_strategies.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    spec: Mapped[dict[str, Any]] = mapped_column(nullable=False)
    requirements: Mapped[list[Any]] = mapped_column(nullable=False)
    fidelity: Mapped[float] = mapped_column(Float, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    assumptions: Mapped[list[Any]] = mapped_column(nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created()

    strategy: Mapped[CustomStrategy] = relationship(back_populates="versions")


class StrategyMessage(Base):
    __tablename__ = "strategy_messages"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="ck_strategy_messages_role"),
        CheckConstraint(
            "outcome IS NULL OR outcome IN ('built', 'invalid', 'error')",
            name="ck_strategy_messages_outcome",
        ),
        CheckConstraint("char_length(content) BETWEEN 1 AND 8000", name="ck_strategy_messages_len"),
        Index("ix_strategy_messages_strategy_id", "strategy_id", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    strategy_id: Mapped[int] = mapped_column(
        ForeignKey("custom_strategies.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[str | None] = mapped_column(String(16))
    version_id: Mapped[int | None] = mapped_column(
        ForeignKey("strategy_versions.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = _created()


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    __table_args__ = (
        CheckConstraint(_status_check, name="ck_workflow_runs_status"),
        CheckConstraint(
            "dev_start < dev_end AND dev_end < holdout_start AND holdout_start < holdout_end",
            name="ck_workflow_runs_split",
        ),
        CheckConstraint("initial_capital > 0", name="ck_workflow_runs_capital"),
        Index("ix_workflow_runs_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("datasets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    dev_start: Mapped[date] = mapped_column(Date, nullable=False)
    dev_end: Mapped[date] = mapped_column(Date, nullable=False)
    holdout_start: Mapped[date] = mapped_column(Date, nullable=False)
    holdout_end: Mapped[date] = mapped_column(Date, nullable=False)
    initial_capital: Mapped[float] = mapped_column(Float, nullable=False)
    fee_bps: Mapped[float] = mapped_column(Float, nullable=False)
    slippage_bps: Mapped[float] = mapped_column(Float, nullable=False)
    allow_fractional: Mapped[bool] = mapped_column(Boolean, nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    variant_keys: Mapped[list[Any]] = mapped_column(nullable=False)
    selection_criterion: Mapped[str] = mapped_column(Text, nullable=False)
    selected_strategy_config_id: Mapped[int | None] = mapped_column(
        ForeignKey("strategy_configs.id", ondelete="RESTRICT")
    )
    deterministic_summary: Mapped[str | None] = mapped_column(Text)
    llm_explanation: Mapped[str | None] = mapped_column(Text)
    llm_model: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    dataset: Mapped[Dataset] = relationship()


class Experiment(Base):
    __tablename__ = "experiments"
    __table_args__ = (
        CheckConstraint(_status_check, name="ck_experiments_status"),
        CheckConstraint(
            "role IN ('standalone', 'development', 'holdout')", name="ck_experiments_role"
        ),
        CheckConstraint(
            "(role = 'standalone') = (workflow_run_id IS NULL)", name="ck_experiments_role_wf"
        ),
        CheckConstraint("start_date < end_date", name="ck_experiments_dates"),
        CheckConstraint("initial_capital > 0", name="ck_experiments_capital"),
        CheckConstraint(
            "bootstrap_block_length >= 1 AND bootstrap_resamples BETWEEN 100 AND 20000 "
            "AND confidence_level > 0 AND confidence_level < 1",
            name="ck_experiments_bootstrap",
        ),
        Index("ix_experiments_created_at", "created_at"),
        Index("ix_experiments_status_created", "status", "created_at"),
        Index(
            "ix_experiments_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
        Index(
            "uq_experiments_wf_dev_config",
            "workflow_run_id",
            "strategy_config_id",
            unique=True,
            postgresql_where=text("role = 'development'"),
        ),
        Index(
            "uq_experiments_wf_holdout",
            "workflow_run_id",
            unique=True,
            postgresql_where=text("role = 'holdout'"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("datasets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    strategy_config_id: Mapped[int] = mapped_column(
        ForeignKey("strategy_configs.id", ondelete="RESTRICT"), nullable=False
    )
    dataset_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(20), nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    initial_capital: Mapped[float] = mapped_column(Float, nullable=False)
    risk_free_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    bootstrap_block_length: Mapped[int] = mapped_column(Integer, nullable=False)
    bootstrap_resamples: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence_level: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    error: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="standalone")
    workflow_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"), index=True
    )
    rerun_of_id: Mapped[int | None] = mapped_column(
        ForeignKey("experiments.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    dataset: Mapped[Dataset] = relationship()
    strategy_config: Mapped[StrategyConfig] = relationship()
    result: Mapped["ExperimentResult | None"] = relationship(
        back_populates="experiment", uselist=False
    )


class ExperimentResult(Base):
    __tablename__ = "experiment_results"

    experiment_id: Mapped[int] = mapped_column(
        ForeignKey("experiments.id", ondelete="CASCADE"), primary_key=True
    )
    eval_start: Mapped[date] = mapped_column(Date, nullable=False)
    eval_end: Mapped[date] = mapped_column(Date, nullable=False)
    n_days: Mapped[int] = mapped_column(Integer, nullable=False)
    strategy_metrics: Mapped[dict[str, Any]] = mapped_column(nullable=False)
    benchmark_metrics: Mapped[dict[str, Any]] = mapped_column(nullable=False)
    confidence_intervals: Mapped[dict[str, Any]] = mapped_column(nullable=False)
    equity_curve: Mapped[dict[str, Any]] = mapped_column(nullable=False)
    notes: Mapped[list[Any]] = mapped_column(nullable=False)
    artifact_key: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()

    experiment: Mapped[Experiment] = relationship(back_populates="result")


class Trade(Base):
    __tablename__ = "trades"
    __table_args__ = (
        UniqueConstraint("experiment_id", "seq", name="uq_trades_experiment_seq"),
        CheckConstraint("side IN ('buy', 'sell', 'short', 'cover')", name="ck_trades_side"),
        CheckConstraint("shares > 0 AND exec_price > 0", name="ck_trades_positive"),
        CheckConstraint("signal_date < trade_date", name="ck_trades_no_lookahead"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    experiment_id: Mapped[int] = mapped_column(
        ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    signal_date: Mapped[date] = mapped_column(Date, nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    open_price: Mapped[float] = mapped_column(Float, nullable=False)
    exec_price: Mapped[float] = mapped_column(Float, nullable=False)
    shares: Mapped[float] = mapped_column(Float, nullable=False)
    notional: Mapped[float] = mapped_column(Float, nullable=False)
    fee: Mapped[float] = mapped_column(Float, nullable=False)
    slippage_cost: Mapped[float] = mapped_column(Float, nullable=False)
    cash_after: Mapped[float] = mapped_column(Float, nullable=False)


class SentimentBatch(Base):
    __tablename__ = "sentiment_batches"
    __table_args__ = (
        CheckConstraint(_status_check, name="ck_sentiment_batches_status"),
        Index("ix_sentiment_batches_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    headlines: Mapped[list["Headline"]] = relationship(
        back_populates="batch", order_by="Headline.position"
    )


class Headline(Base):
    __tablename__ = "headlines"
    __table_args__ = (
        UniqueConstraint("batch_id", "position", name="uq_headlines_batch_position"),
        CheckConstraint("source IN ('sample', 'user')", name="ck_headlines_source"),
        CheckConstraint("char_length(text) BETWEEN 1 AND 300", name="ck_headlines_text_len"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("sentiment_batches.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(String(300), nullable=False)
    source: Mapped[str] = mapped_column(String(8), nullable=False)
    created_at: Mapped[datetime] = _created()

    batch: Mapped[SentimentBatch] = relationship(back_populates="headlines")
    result: Mapped["SentimentResult | None"] = relationship(uselist=False)


class SentimentResult(Base):
    __tablename__ = "sentiment_results"
    __table_args__ = (
        CheckConstraint(
            "label IN ('positive', 'negative', 'neutral')", name="ck_sentiment_results_label"
        ),
        CheckConstraint(
            "score_positive BETWEEN 0 AND 1 AND score_negative BETWEEN 0 AND 1 "
            "AND score_neutral BETWEEN 0 AND 1",
            name="ck_sentiment_results_scores",
        ),
    )

    headline_id: Mapped[int] = mapped_column(
        ForeignKey("headlines.id", ondelete="CASCADE"), primary_key=True
    )
    label: Mapped[str] = mapped_column(String(8), nullable=False)
    score_positive: Mapped[float] = mapped_column(Float, nullable=False)
    score_negative: Mapped[float] = mapped_column(Float, nullable=False)
    score_neutral: Mapped[float] = mapped_column(Float, nullable=False)
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    model_revision: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created()


class WorkflowEvent(Base):
    __tablename__ = "workflow_events"
    __table_args__ = (
        CheckConstraint(
            "status IN ('started', 'completed', 'retrying', 'failed', 'resumed', 'info')",
            name="ck_workflow_events_status",
        ),
        Index("ix_workflow_events_run_id", "workflow_run_id", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    workflow_run_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False
    )
    node: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created()


class Job(Base):
    """PostgreSQL-backed work queue. Exactly one target column is set per kind."""

    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(_status_check, name="ck_jobs_status"),
        CheckConstraint(
            "(kind = 'backtest' AND experiment_id IS NOT NULL AND workflow_run_id IS NULL "
            "AND sentiment_batch_id IS NULL) OR "
            "(kind = 'workflow' AND workflow_run_id IS NOT NULL AND experiment_id IS NULL "
            "AND sentiment_batch_id IS NULL) OR "
            "(kind = 'sentiment' AND sentiment_batch_id IS NOT NULL AND experiment_id IS NULL "
            "AND workflow_run_id IS NULL)",
            name="ck_jobs_target",
        ),
        CheckConstraint("attempts >= 0 AND attempts <= max_attempts", name="ck_jobs_attempts"),
        CheckConstraint("max_attempts BETWEEN 1 AND 10", name="ck_jobs_max_attempts"),
        CheckConstraint(
            "status <> 'running' OR (lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)",
            name="ck_jobs_running_lease",
        ),
        Index(
            "ix_jobs_claimable",
            "run_after",
            "id",
            postgresql_where=text("status = 'queued'"),
        ),
        Index(
            "ix_jobs_running_lease",
            "lease_expires_at",
            postgresql_where=text("status = 'running'"),
        ),
        # At most one active job per target prevents duplicate execution requests.
        Index(
            "uq_jobs_active_experiment",
            "experiment_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
        Index(
            "uq_jobs_active_workflow",
            "workflow_run_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
        Index(
            "uq_jobs_active_sentiment",
            "sentiment_batch_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    experiment_id: Mapped[int | None] = mapped_column(
        ForeignKey("experiments.id", ondelete="CASCADE")
    )
    workflow_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE")
    )
    sentiment_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("sentiment_batches.id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    run_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    lease_owner: Mapped[str | None] = mapped_column(Text)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Worker(Base):
    """Liveness record each worker process upserts on every poll."""

    __tablename__ = "workers"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    hostname: Mapped[str] = mapped_column(Text, nullable=False)
    pid: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    current_job_id: Mapped[int | None] = mapped_column(BigInteger)
    sentiment_model_status: Mapped[str] = mapped_column(Text, nullable=False)
