import math

import numpy as np
import pytest
from helpers import random_walk_bars

from quantlab.engine.backtest import StrategyParams
from quantlab.engine.bootstrap import block_bootstrap_mean_ci
from quantlab.engine.metrics import TRADING_DAYS, compute_metrics, daily_returns, drawdown_series
from quantlab.engine.runner import ExperimentSpec, evaluate


def test_returns_include_initial_capital():
    r = daily_returns(np.array([1100.0, 1210.0]), 1000.0)
    np.testing.assert_allclose(r, [0.1, 0.1])


def test_hand_calculated_metrics():
    eq = np.array([1010.0, 1000.0, 1030.0, 1020.0])
    m = compute_metrics(eq, 1000.0)
    r = np.array([0.01, 1000 / 1010 - 1, 0.03, 1020 / 1030 - 1])
    assert m["total_return"] == pytest.approx(0.02)
    assert m["cagr"] == pytest.approx(1.02 ** (TRADING_DAYS / 4) - 1)
    assert m["annualized_volatility"] == pytest.approx(np.std(r, ddof=1) * math.sqrt(252))
    assert m["sharpe_ratio"] == pytest.approx(r.mean() / np.std(r, ddof=1) * math.sqrt(252))
    assert m["max_drawdown"] == pytest.approx(1000 / 1010 - 1)


def test_drawdown_uses_initial_capital_as_first_peak():
    np.testing.assert_allclose(drawdown_series(np.array([900.0]), 1000.0), [-0.1])
    dd = drawdown_series(np.array([1000.0, 1200.0, 900.0, 1300.0]), 1000.0)
    assert dd.min() == pytest.approx(-0.25)


def test_zero_variance_sharpe_is_undefined_not_zero():
    m = compute_metrics(np.full(30, 1000.0), 1000.0)
    assert m["sharpe_ratio"] is None
    assert "zero variance" in m["undefined"]["sharpe_ratio"]
    assert m["annualized_volatility"] == 0.0
    assert m["total_return"] == 0.0


def test_single_day_metrics_undefined():
    m = compute_metrics(np.array([1001.0]), 1000.0)
    assert m["annualized_volatility"] is None and m["sharpe_ratio"] is None


def test_total_loss_cagr():
    m = compute_metrics(np.array([500.0, 0.0]), 1000.0)
    assert m["cagr"] == -1.0


def test_risk_free_rate_reduces_sharpe():
    rng = np.random.default_rng(0)
    eq = 1000 * np.cumprod(1 + rng.normal(0.0005, 0.01, 300))
    a = compute_metrics(eq, 1000.0, 0.0)["sharpe_ratio"]
    b = compute_metrics(eq, 1000.0, 0.05)["sharpe_ratio"]
    assert b < a


def test_bootstrap_is_reproducible_and_brackets_mean():
    rng = np.random.default_rng(3)
    r = rng.normal(0.0004, 0.01, 600)
    a = block_bootstrap_mean_ci(r, 20, 1000, 0.95, seed=11)
    b = block_bootstrap_mean_ci(r, 20, 1000, 0.95, seed=11)
    c = block_bootstrap_mean_ci(r, 20, 1000, 0.95, seed=12)
    assert a == b
    assert a["status"] == "ok" and a["low"] < a["point_estimate"] < a["high"]
    assert (a["low"], a["high"]) != (c["low"], c["high"])
    assert a["block_length"] == 20 and a["n_blocks"] == 30 and a["dropped_oldest_days"] == 0
    assert a["metric"] == "mean_daily_return" and a["seed"] == 11


def test_bootstrap_drops_oldest_remainder():
    r = np.arange(205, dtype=float) / 1e4
    res = block_bootstrap_mean_ci(r, 20, 200, 0.9, seed=1)
    assert res["dropped_oldest_days"] == 5
    assert res["point_estimate"] == pytest.approx(r[5:].mean())


def test_bootstrap_short_series_reports_insufficient():
    res = block_bootstrap_mean_ci(np.full(50, 0.001) + np.arange(50) * 1e-5, 20, 500, 0.95, 1)
    assert res["status"] == "insufficient_data" and res["low"] is None


def test_bootstrap_degenerate_series():
    res = block_bootstrap_mean_ci(np.zeros(400), 20, 500, 0.95, 1)
    assert res["status"] == "degenerate" and res["low"] is None
    assert res["point_estimate"] == 0.0


def test_evaluate_is_deterministic_and_json_safe():
    import json

    bars = random_walk_bars(700)
    spec = ExperimentSpec(
        params=StrategyParams(
            short_window=20, long_window=100, initial_capital=10_000, fee_bps=5, slippage_bps=5
        ),
        start=bars.date_at(150),
        end=bars.date_at(699),
        seed=42,
    )
    a, b = evaluate(bars, spec), evaluate(bars, spec)
    assert json.dumps(a, allow_nan=False) == json.dumps(b, allow_nan=False)
    assert a["eval_start"] == str(bars.date_at(150))
    assert len(a["equity_curve"]["dates"]) == a["n_days"] == 550
    assert a["benchmark_metrics"]["n_trades"] == 1
    assert a["strategy_metrics"]["n_trades"] == len(a["trades"])
