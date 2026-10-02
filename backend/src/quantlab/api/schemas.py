from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantlab.engine.backtest import MAX_WINDOW
from quantlab.workflow.variants import MAX_VARIANTS

Status = Literal["queued", "running", "completed", "failed"]


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ------------------------------------------------------------------ datasets


class DatasetOut(ORM):
    id: int
    name: str
    version: int
    symbol: str
    source: str
    is_synthetic: bool
    adjustment: str
    content_sha256: str
    row_count: int
    start_date: date
    end_date: date
    created_at: datetime


class DatasetImportOut(BaseModel):
    dataset: DatasetOut
    warnings: list[dict[str, Any]]


class WarmupOut(BaseModel):
    dataset_id: int
    long_window: int
    earliest_start: date | None


# --------------------------------------------------------------- experiments


class ExperimentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    dataset_id: int = Field(gt=0)
    start_date: date
    end_date: date
    initial_capital: float = Field(ge=100, le=1_000_000_000)
    short_window: int = Field(ge=1, le=MAX_WINDOW - 1)
    long_window: int = Field(ge=2, le=MAX_WINDOW)
    fee_bps: float = Field(ge=0, le=500)
    slippage_bps: float = Field(ge=0, le=500)
    allow_fractional: bool = True
    seed: int = Field(default=42, ge=0, le=2**31 - 1)
    bootstrap_block_length: int = Field(default=20, ge=1, le=250)
    bootstrap_resamples: int = Field(default=2000, ge=100, le=20000)
    confidence_level: float = Field(default=0.95, ge=0.5, le=0.99)

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name cannot be blank.")
        return v

    @model_validator(mode="after")
    def check_relations(self):
        if self.short_window >= self.long_window:
            raise ValueError("short_window must be smaller than long_window.")
        if self.start_date >= self.end_date:
            raise ValueError("start_date must be before end_date.")
        return self


class StrategyConfigOut(ORM):
    id: int
    strategy: str
    short_window: int
    long_window: int
    fee_bps: float
    slippage_bps: float
    allow_fractional: bool


class JobOut(ORM):
    id: int
    status: Status
    attempts: int
    max_attempts: int
    lease_owner: str | None
    heartbeat_at: datetime | None
    last_error: str | None


class ExperimentSummary(BaseModel):
    id: int
    name: str
    status: Status
    role: str
    workflow_run_id: int | None
    dataset_id: int
    dataset_name: str
    dataset_is_synthetic: bool
    short_window: int
    long_window: int
    start_date: date
    end_date: date
    created_at: datetime
    total_return: float | None = None
    sharpe_ratio: float | None = None
    max_drawdown: float | None = None
    benchmark_total_return: float | None = None


class TradeOut(ORM):
    seq: int
    signal_date: date
    trade_date: date
    side: str
    open_price: float
    exec_price: float
    shares: float
    notional: float
    fee: float
    slippage_cost: float
    cash_after: float


class ResultOut(ORM):
    eval_start: date
    eval_end: date
    n_days: int
    strategy_metrics: dict[str, Any]
    benchmark_metrics: dict[str, Any]
    confidence_intervals: dict[str, Any]
    equity_curve: dict[str, Any]
    notes: list[Any]
    artifact_key: str | None


class ExperimentDetail(BaseModel):
    id: int
    name: str
    status: Status
    error: str | None
    role: str
    workflow_run_id: int | None
    rerun_of_id: int | None
    dataset: DatasetOut
    strategy_config: StrategyConfigOut
    dataset_sha256: str
    engine_version: str
    seed: int
    start_date: date
    end_date: date
    initial_capital: float
    risk_free_rate: float
    bootstrap_block_length: int
    bootstrap_resamples: int
    confidence_level: float
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    job: JobOut | None
    result: ResultOut | None
    trades: list[TradeOut]


class CompareOut(BaseModel):
    eval_start: date
    eval_end: date
    dataset_sha256: str
    experiments: list[ExperimentDetail]


class StatsOut(BaseModel):
    total: int
    by_status: dict[str, int]
    best_sharpe: ExperimentSummary | None
    workers_online: int


# ------------------------------------------------------------------ workflows


class WorkflowCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    dataset_id: int = Field(gt=0)
    dev_start: date
    dev_end: date
    holdout_start: date
    holdout_end: date
    initial_capital: float = Field(default=10_000, ge=100, le=1_000_000_000)
    fee_bps: float = Field(default=5, ge=0, le=500)
    slippage_bps: float = Field(default=5, ge=0, le=500)
    allow_fractional: bool = True
    seed: int = Field(default=42, ge=0, le=2**31 - 1)
    variant_keys: list[str] = Field(min_length=1, max_length=MAX_VARIANTS)

    @model_validator(mode="after")
    def chronological(self):
        if not (self.dev_start < self.dev_end < self.holdout_start < self.holdout_end):
            raise ValueError(
                "Periods must be chronological and disjoint: dev_start < dev_end < "
                "holdout_start < holdout_end."
            )
        return self


class WorkflowEventOut(ORM):
    id: int
    node: str
    status: str
    attempt: int
    message: str
    payload: dict[str, Any] | None
    created_at: datetime


class WorkflowSummary(BaseModel):
    id: int
    name: str
    status: Status
    dataset_id: int
    dataset_name: str
    created_at: datetime
    selected_label: str | None


class WorkflowDetail(BaseModel):
    id: int
    name: str
    status: Status
    error: str | None
    dataset: DatasetOut
    dev_start: date
    dev_end: date
    holdout_start: date
    holdout_end: date
    initial_capital: float
    fee_bps: float
    slippage_bps: float
    allow_fractional: bool
    seed: int
    variant_keys: list[str]
    selection_criterion: str
    selected_strategy_config: StrategyConfigOut | None
    deterministic_summary: str | None
    llm_explanation: str | None
    llm_model: str | None
    created_at: datetime
    completed_at: datetime | None
    resumable: bool
    job: JobOut | None
    nodes: list[dict[str, Any]]
    events: list[WorkflowEventOut]
    development: list[ExperimentSummary]
    holdout: ExperimentSummary | None


class VariantOut(BaseModel):
    key: str
    label: str
    short_window: int
    long_window: int


# ------------------------------------------------------------------ sentiment


class SentimentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headlines: list[str] = Field(default_factory=list, max_length=32)
    include_samples: bool = False

    @field_validator("headlines")
    @classmethod
    def clean(cls, v: list[str]) -> list[str]:
        out = []
        for i, h in enumerate(v):
            h = " ".join(h.split())
            if not h:
                raise ValueError(f"Headline {i + 1} is blank.")
            if len(h) > 300:
                raise ValueError(f"Headline {i + 1} is longer than 300 characters.")
            out.append(h)
        return out

    @model_validator(mode="after")
    def not_empty(self):
        if not self.headlines and not self.include_samples:
            raise ValueError("Provide at least one headline or include the samples.")
        return self


class SentimentResultOut(BaseModel):
    label: str
    score_positive: float
    score_negative: float
    score_neutral: float
    model_name: str
    model_revision: str


class HeadlineOut(BaseModel):
    id: int
    position: int
    text: str
    source: str
    result: SentimentResultOut | None


class SentimentBatchOut(BaseModel):
    id: int
    status: Status
    error: str | None
    created_at: datetime
    completed_at: datetime | None
    job: JobOut | None
    headlines: list[HeadlineOut]
