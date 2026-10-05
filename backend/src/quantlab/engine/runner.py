"""Pure, deterministic experiment evaluation: bars + settings -> result dict.

No database or network access happens here, which keeps this easy to test and
lets the worker and the research workflow share exactly one code path.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date

import numpy as np

from quantlab import ENGINE_VERSION
from quantlab.engine.backtest import StrategyParams, run_backtest
from quantlab.engine.bootstrap import block_bootstrap_mean_ci
from quantlab.engine.data import Bars, finite_or_none
from quantlab.engine.metrics import compute_metrics, daily_returns, drawdown_series


@dataclass(frozen=True)
class ExperimentSpec:
    params: StrategyParams
    start: date
    end: date
    seed: int
    risk_free_rate: float = 0.0
    bootstrap_block_length: int = 20
    bootstrap_resamples: int = 2000
    confidence_level: float = 0.95


def _clean(values: np.ndarray, digits: int = 6) -> list[float | None]:
    return [finite_or_none(round(float(v), digits)) for v in values]


def evaluate(bars: Bars, spec: ExperimentSpec) -> dict:
    out = run_backtest(bars, spec.params, spec.start, spec.end)
    cap = spec.params.initial_capital
    s, b = out.strategy, out.benchmark

    strategy_metrics = compute_metrics(
        s.equity,
        cap,
        spec.risk_free_rate,
        s.position,
        len(s.trades),
        s.total_fees,
        s.total_slippage,
    )
    benchmark_metrics = compute_metrics(
        b.equity,
        cap,
        spec.risk_free_rate,
        b.position,
        len(b.trades),
        b.total_fees,
        b.total_slippage,
    )

    ci = {
        name: block_bootstrap_mean_ci(
            daily_returns(ledger.equity, cap),
            spec.bootstrap_block_length,
            spec.bootstrap_resamples,
            spec.confidence_level,
            spec.seed,
        )
        for name, ledger in (("strategy", s), ("benchmark", b))
    }

    return {
        "engine_version": ENGINE_VERSION,
        "eval_start": out.dates[0],
        "eval_end": out.dates[-1],
        "n_days": len(out.dates),
        "strategy_metrics": strategy_metrics,
        "benchmark_metrics": benchmark_metrics,
        "confidence_intervals": ci,
        "equity_curve": {
            "dates": out.dates,
            "strategy": _clean(s.equity, 4),
            "benchmark": _clean(b.equity, 4),
            "strategy_drawdown": _clean(drawdown_series(s.equity, cap)),
            "benchmark_drawdown": _clean(drawdown_series(b.equity, cap)),
            "signal": [int(x) for x in out.signal],
            "short_ma": [] if out.short_ma is None else _clean(out.short_ma, 4),
            "long_ma": [] if out.long_ma is None else _clean(out.long_ma, 4),
        },
        "trades": [asdict(t) for t in s.trades],
        "notes": out.notes,
    }
