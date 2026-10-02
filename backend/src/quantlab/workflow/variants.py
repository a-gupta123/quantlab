"""Predefined, bounded parameter variants for the research workflow.

The workflow never searches a grid or accepts arbitrary code: it evaluates at
most MAX_VARIANTS entries from this fixed library.
"""

MAX_VARIANTS = 3

VARIANT_LIBRARY: dict[str, dict] = {
    "fast_10_50": {"label": "Fast (10/50)", "short_window": 10, "long_window": 50},
    "medium_20_100": {"label": "Medium (20/100)", "short_window": 20, "long_window": 100},
    "classic_50_200": {"label": "Classic (50/200)", "short_window": 50, "long_window": 200},
}

SELECTION_CRITERION = (
    "Highest development-period Sharpe ratio (risk-free rate 0). Ties break on higher "
    "development total return, then on the shorter long window. Variants with an "
    "undefined Sharpe ratio are not eligible. The held-out period is never consulted."
)


def resolve_variants(keys: list[str]) -> list[dict]:
    unique = list(dict.fromkeys(keys))
    if not unique:
        raise ValueError("Select at least one variant.")
    if len(unique) > MAX_VARIANTS:
        raise ValueError(f"At most {MAX_VARIANTS} variants may be evaluated.")
    unknown = [k for k in unique if k not in VARIANT_LIBRARY]
    if unknown:
        raise ValueError(f"Unknown variant(s): {', '.join(unknown)}.")
    return [{"key": k, **VARIANT_LIBRARY[k]} for k in unique]


def select_best(dev_results: list[dict]) -> dict | None:
    """Deterministic selection using only development metrics."""
    eligible = [r for r in dev_results if r["sharpe_ratio"] is not None]
    if not eligible:
        return None
    return sorted(
        eligible,
        key=lambda r: (-r["sharpe_ratio"], -r["total_return"], r["long_window"]),
    )[0]
