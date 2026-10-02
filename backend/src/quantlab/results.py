"""Idempotent persistence of experiment results.

`experiment_results.experiment_id` is the primary key, so a result can exist at
most once. We insert with ON CONFLICT DO NOTHING and only write trades when this
call created the result row; a retry after a crash (or a duplicate worker) can
therefore never produce two result sets or duplicated trades.
"""

from __future__ import annotations

import json
from datetime import date

from sqlalchemy import insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from quantlab.models import Experiment, ExperimentResult, Trade
from quantlab.storage import Storage


def artifact_key(experiment_id: int) -> str:
    return f"artifacts/experiments/{experiment_id}/result.json"


def write_artifact(storage: Storage, experiment: Experiment, result: dict) -> str:
    """Upload the full result JSON. Content is deterministic, so rewriting the
    same key on retry is safe."""
    key = artifact_key(experiment.id)
    payload = {
        "experiment_id": experiment.id,
        "dataset_sha256": experiment.dataset_sha256,
        "engine_version": result["engine_version"],
        "seed": experiment.seed,
        **result,
    }
    storage.put_bytes(key, json.dumps(payload, allow_nan=False).encode(), "application/json")
    return key


def save_result(session: Session, experiment_id: int, result: dict, artifact: str | None) -> bool:
    """Insert the result once. Returns True if this call stored it."""
    stmt = (
        pg_insert(ExperimentResult)
        .values(
            experiment_id=experiment_id,
            eval_start=date.fromisoformat(result["eval_start"]),
            eval_end=date.fromisoformat(result["eval_end"]),
            n_days=result["n_days"],
            strategy_metrics=result["strategy_metrics"],
            benchmark_metrics=result["benchmark_metrics"],
            confidence_intervals=result["confidence_intervals"],
            equity_curve=result["equity_curve"],
            notes=result["notes"],
            artifact_key=artifact,
        )
        .on_conflict_do_nothing(index_elements=["experiment_id"])
        .returning(ExperimentResult.experiment_id)
    )
    created = session.execute(stmt).scalar_one_or_none() is not None
    if created and result["trades"]:
        session.execute(
            insert(Trade),
            [
                {
                    "experiment_id": experiment_id,
                    "seq": t["seq"],
                    "signal_date": date.fromisoformat(t["signal_date"]),
                    "trade_date": date.fromisoformat(t["trade_date"]),
                    "side": t["side"],
                    "open_price": t["open_price"],
                    "exec_price": t["exec_price"],
                    "shares": t["shares"],
                    "notional": t["notional"],
                    "fee": t["fee"],
                    "slippage_cost": t["slippage_cost"],
                    "cash_after": t["cash_after"],
                }
                for t in result["trades"]
            ],
        )
    return created


def has_result(session: Session, experiment_id: int) -> bool:
    return (
        session.scalar(
            select(ExperimentResult.experiment_id).where(
                ExperimentResult.experiment_id == experiment_id
            )
        )
        is not None
    )
