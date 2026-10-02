"""Performance metrics. Formulas are documented in docs/architecture.md.

Conventions:
* 252 trading days per year.
* Daily returns r_0 = V_0 / C - 1 and r_t = V_t / V_{t-1} - 1, where C is initial
  capital and V_t the close-marked equity. So n evaluated days give n returns,
  and the first return includes entry costs.
* Risk-free rate: an annual rate rf converted to a daily rate
  (1 + rf) ** (1/252) - 1. The default is 0.
* Undefined values are returned as None with a reason in `undefined`, never as
  NaN/inf (which JSON cannot carry) and never silently as 0.
"""

from __future__ import annotations

import math

import numpy as np

TRADING_DAYS = 252
ZERO_VARIANCE_TOL = 1e-12


def daily_returns(equity: np.ndarray, initial_capital: float) -> np.ndarray:
    prev = np.concatenate(([initial_capital], equity[:-1]))
    return equity / prev - 1.0


def drawdown_series(equity: np.ndarray, initial_capital: float) -> np.ndarray:
    """Fractional drop from the running peak; the initial capital is the first peak."""
    peaks = np.maximum.accumulate(np.concatenate(([initial_capital], equity)))[1:]
    return equity / peaks - 1.0


def compute_metrics(
    equity: np.ndarray,
    initial_capital: float,
    risk_free_rate: float = 0.0,
    position: np.ndarray | None = None,
    n_trades: int = 0,
    total_fees: float = 0.0,
    total_slippage: float = 0.0,
) -> dict:
    n = len(equity)
    undefined: dict[str, str] = {}
    r = daily_returns(equity, initial_capital)
    final = float(equity[-1])
    growth = final / initial_capital
    total_return = growth - 1.0

    years = n / TRADING_DAYS
    if growth <= 0:
        cagr = -1.0
    else:
        cagr = growth ** (1.0 / years) - 1.0

    vol = sharpe = None
    if n < 2:
        undefined["annualized_volatility"] = "needs at least 2 daily returns"
        undefined["sharpe_ratio"] = "needs at least 2 daily returns"
    else:
        sd = float(np.std(r, ddof=1))
        vol = sd * math.sqrt(TRADING_DAYS)
        rf_daily = (1.0 + risk_free_rate) ** (1.0 / TRADING_DAYS) - 1.0
        excess = r - rf_daily
        sd_excess = float(np.std(excess, ddof=1))
        if sd_excess < ZERO_VARIANCE_TOL:
            undefined["sharpe_ratio"] = (
                "daily returns have zero variance (e.g. the strategy stayed in cash)"
            )
        else:
            sharpe = float(np.mean(excess) / sd_excess * math.sqrt(TRADING_DAYS))

    dd = drawdown_series(equity, initial_capital)
    exposure = None
    if position is not None:
        exposure = float(np.mean(position > 0))

    return {
        "final_equity": final,
        "total_return": float(total_return),
        "cagr": float(cagr),
        "annualized_volatility": vol,
        "sharpe_ratio": sharpe,
        "max_drawdown": float(dd.min()),
        "mean_daily_return": float(np.mean(r)),
        "n_days": n,
        "years": years,
        "exposure": exposure,
        "n_trades": n_trades,
        "total_fees": float(total_fees),
        "total_slippage": float(total_slippage),
        "risk_free_rate": risk_free_rate,
        "undefined": undefined,
    }
