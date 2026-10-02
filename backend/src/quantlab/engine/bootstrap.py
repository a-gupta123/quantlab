"""Block-bootstrap confidence interval for the mean daily return.

Daily returns are autocorrelated (volatility clusters), so resampling single
days would understate uncertainty. We cut the series into non-overlapping blocks
of `block_length` consecutive days and resample whole blocks with replacement.
That keeps dependence *within* a block and assumes blocks are approximately
independent of each other. Longer blocks make that assumption more plausible but
leave fewer blocks to resample.

Because all blocks have equal length, the mean of a resample of blocks equals the
mean of those blocks' means. So we hand SciPy the block means and use np.mean as
the statistic; SciPy resamples along axis 0, i.e. it resamples blocks.

If n is not a multiple of block_length, the oldest n % block_length days are
dropped so that every block is complete.

This is a confidence interval for the historical mean daily return under these
assumptions. It is not a prediction interval and not evidence of future profit.
"""

from __future__ import annotations

import numpy as np
from scipy import stats

MIN_BLOCKS = 10
METHOD = "percentile"


def block_bootstrap_mean_ci(
    returns: np.ndarray,
    block_length: int,
    n_resamples: int,
    confidence_level: float,
    seed: int,
) -> dict:
    r = np.asarray(returns, dtype=float)
    n = len(r)
    base = {
        "metric": "mean_daily_return",
        "method": f"non-overlapping block bootstrap ({METHOD})",
        "block_length": block_length,
        "n_resamples": n_resamples,
        "confidence_level": confidence_level,
        "seed": seed,
        "n_returns": n,
        "point_estimate": float(r.mean()) if n else None,
        "low": None,
        "high": None,
        "annualized_low": None,
        "annualized_high": None,
    }
    if block_length < 1:
        return {**base, "status": "invalid", "detail": "block_length must be at least 1."}
    n_blocks = n // block_length
    base["n_blocks"] = n_blocks
    base["dropped_oldest_days"] = n - n_blocks * block_length
    if n_blocks < MIN_BLOCKS:
        return {
            **base,
            "status": "insufficient_data",
            "detail": (
                f"Only {n_blocks} complete block(s) of {block_length} days; "
                f"need at least {MIN_BLOCKS}. Use a longer period or shorter blocks."
            ),
        }
    trimmed = r[n - n_blocks * block_length :]
    block_means = trimmed.reshape(n_blocks, block_length).mean(axis=1)
    point = float(trimmed.mean())
    base["point_estimate"] = point
    if float(np.ptp(block_means)) == 0.0:
        return {
            **base,
            "status": "degenerate",
            "detail": "Every block has the same mean (e.g. always in cash), so the "
            "bootstrap distribution has zero width.",
        }

    res = stats.bootstrap(
        (block_means,),
        np.mean,
        n_resamples=n_resamples,
        confidence_level=confidence_level,
        method=METHOD,
        rng=np.random.default_rng(seed),
    )
    low = float(res.confidence_interval.low)
    high = float(res.confidence_interval.high)
    return {
        **base,
        "status": "ok",
        "low": low,
        "high": high,
        "annualized_low": low * 252,
        "annualized_high": high * 252,
        "standard_error": float(res.standard_error),
        "detail": "Assumes blocks are approximately independent; not a prediction interval.",
    }
