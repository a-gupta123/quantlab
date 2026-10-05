"""Rule-based strategies described as data (built by the strategy chatbot).

A RuleSpec is a small, closed language: indicators, comparisons, AND/OR groups,
and exits (stop-loss, take-profit, maximum holding period). The chatbot only
ever produces a RuleSpec; it never produces code. Everything here is validated
before a backtest runs.

No look-ahead: every indicator value at bar t is computed from bars <= t only
(trailing windows), and `highest_high` / `lowest_low` use the n bars *before*
t so "close breaks the 20-day high" is expressible. Decisions are made after
the close of bar t and executed at the open of t+1 by the backtest loop.
"""

from __future__ import annotations

import math
from typing import Literal

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_PERIOD = 400
MAX_OFFSET = 50

Indicator = Literal[
    "close",
    "open",
    "high",
    "low",
    "volume",
    "sma",
    "ema",
    "rsi",
    "macd",
    "macd_signal",
    "macd_hist",
    "bb_upper",
    "bb_middle",
    "bb_lower",
    "highest_high",
    "lowest_low",
    "return_pct",
    "volatility_pct",
]
Source = Literal["close", "open", "high", "low", "volume"]
Op = Literal[">", "<", ">=", "<=", "crosses_above", "crosses_below"]

PRICE_FIELDS = {"close", "open", "high", "low", "volume"}
NEEDS_PERIOD = {
    "sma",
    "ema",
    "rsi",
    "bb_upper",
    "bb_middle",
    "bb_lower",
    "highest_high",
    "lowest_low",
    "return_pct",
    "volatility_pct",
}
MACD_FAMILY = {"macd", "macd_signal", "macd_hist"}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Operand(_Strict):
    kind: Literal["indicator", "value"]
    indicator: Indicator | None = None
    period: int | None = Field(default=None, ge=1, le=MAX_PERIOD)
    source: Source | None = None  # input series for sma/ema (default close)
    std_mult: float | None = Field(default=None, gt=0, le=10)  # Bollinger width
    fast: int | None = Field(default=None, ge=1, le=MAX_PERIOD)  # MACD
    slow: int | None = Field(default=None, ge=2, le=MAX_PERIOD)
    signal_period: int | None = Field(default=None, ge=1, le=MAX_PERIOD)
    offset: int = Field(default=0, ge=0, le=MAX_OFFSET)  # bars ago
    scale: float = Field(default=1.0, gt=0, le=100)  # e.g. 1.02 * SMA
    value: float | None = None

    @model_validator(mode="after")
    def _check(self):
        if self.kind == "value":
            if self.value is None or not math.isfinite(self.value):
                raise ValueError("A constant operand needs a finite 'value'.")
            return self
        if self.indicator is None:
            raise ValueError("An indicator operand needs 'indicator'.")
        if self.indicator in NEEDS_PERIOD and self.period is None:
            raise ValueError(f"'{self.indicator}' needs a 'period'.")
        if self.indicator == "rsi" and self.period is not None and self.period < 2:
            raise ValueError("RSI period must be at least 2.")
        if self.indicator in MACD_FAMILY:
            fast, slow = self.fast or 12, self.slow or 26
            if fast >= slow:
                raise ValueError("MACD fast period must be shorter than the slow period.")
        return self

    def label(self) -> str:
        if self.kind == "value":
            return f"{self.value:g}"
        ind = self.indicator
        if ind in PRICE_FIELDS:
            base = ind
        elif ind in MACD_FAMILY:
            base = f"{ind}({self.fast or 12},{self.slow or 26},{self.signal_period or 9})"
        elif ind and ind.startswith("bb_"):
            base = f"{ind}({self.period},{self.std_mult or 2:g})"
        elif ind in ("sma", "ema") and self.source and self.source != "close":
            base = f"{ind}({self.source},{self.period})"
        else:
            base = f"{ind}({self.period})"
        if self.scale != 1.0:
            base = f"{self.scale:g}×{base}"
        if self.offset:
            base = f"{base}[{self.offset} bars ago]"
        return base


class Comparison(_Strict):
    left: Operand
    op: Op
    right: Operand

    def label(self) -> str:
        return f"{self.left.label()} {self.op.replace('_', ' ')} {self.right.label()}"


class Group(_Strict):
    mode: Literal["all", "any"]
    rules: list[Comparison] = Field(min_length=1, max_length=8)


class Condition(_Strict):
    """`mode` combines the direct rules and the nested groups (one level deep)."""

    mode: Literal["all", "any"]
    rules: list[Comparison] = Field(default_factory=list, max_length=8)
    groups: list[Group] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def _non_empty(self):
        if not self.rules and not self.groups:
            raise ValueError("A condition needs at least one rule or group.")
        return self

    def comparisons(self) -> list[Comparison]:
        return [*self.rules, *(c for g in self.groups for c in g.rules)]


class RuleSpec(_Strict):
    direction: Literal["long_only", "short_only", "long_short"]
    long_entry: Condition | None = None
    long_exit: Condition | None = None
    short_entry: Condition | None = None
    short_exit: Condition | None = None
    stop_loss_pct: float | None = Field(default=None, gt=0, le=90)
    take_profit_pct: float | None = Field(default=None, gt=0, le=1000)
    max_holding_days: int | None = Field(default=None, ge=1, le=2000)

    @model_validator(mode="after")
    def _consistent(self):
        longs = self.direction in ("long_only", "long_short")
        shorts = self.direction in ("short_only", "long_short")
        if longs and self.long_entry is None:
            raise ValueError(f"direction '{self.direction}' needs a long_entry condition.")
        if shorts and self.short_entry is None:
            raise ValueError(f"direction '{self.direction}' needs a short_entry condition.")
        if not longs and (self.long_entry or self.long_exit):
            raise ValueError("A short_only strategy cannot have long rules.")
        if not shorts and (self.short_entry or self.short_exit):
            raise ValueError("A long_only strategy cannot have short rules.")
        return self

    def conditions(self) -> list[Condition]:
        return [
            c for c in (self.long_entry, self.long_exit, self.short_entry, self.short_exit) if c
        ]

    def operands(self) -> list[Operand]:
        return [
            o for c in self.conditions() for cmp in c.comparisons() for o in (cmp.left, cmp.right)
        ]

    def warmup_bars(self) -> int:
        """Bars needed *before* the first decision for every indicator to be defined."""
        need = 0
        for c in self.conditions():
            for cmp in c.comparisons():
                cross = 1 if cmp.op.startswith("crosses") else 0
                for o in (cmp.left, cmp.right):
                    need = max(need, _lookback(o) + o.offset + cross)
        return need + 1


# ------------------------------------------------------------- indicators


def _lookback(o: Operand) -> int:
    """Index of the first defined value (0 = defined from the first bar)."""
    if o.kind == "value" or o.indicator in PRICE_FIELDS:
        return 0
    p = o.period or 0
    if o.indicator in MACD_FAMILY:
        slow, sig = o.slow or 26, o.signal_period or 9
        return slow - 1 + (0 if o.indicator == "macd" else sig - 1)
    if o.indicator in ("rsi", "highest_high", "lowest_low", "return_pct", "volatility_pct"):
        return p
    return p - 1  # sma, ema, bollinger


def sma(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        out[n - 1 :] = sliding_window_view(x, n).mean(axis=1)
    return out


def ema(x: np.ndarray, n: int) -> np.ndarray:
    """EMA with alpha = 2/(n+1), seeded with the SMA of the first n defined values."""
    out = np.full(len(x), np.nan)
    finite = np.flatnonzero(~np.isnan(x))
    if len(finite) < n:
        return out
    start = finite[0]
    seed_end = start + n - 1
    out[seed_end] = x[start : seed_end + 1].mean()
    alpha = 2.0 / (n + 1)
    for i in range(seed_end + 1, len(x)):
        out[i] = alpha * x[i] + (1 - alpha) * out[i - 1]
    return out


def rsi(close: np.ndarray, n: int) -> np.ndarray:
    """Wilder's RSI: first value at index n, smoothed averages afterwards."""
    out = np.full(len(close), np.nan)
    if len(close) <= n:
        return out
    diff = np.diff(close)
    gain, loss = np.clip(diff, 0, None), np.clip(-diff, 0, None)
    avg_g, avg_l = gain[:n].mean(), loss[:n].mean()
    for i in range(n, len(close)):
        if i > n:
            avg_g = (avg_g * (n - 1) + gain[i - 1]) / n
            avg_l = (avg_l * (n - 1) + loss[i - 1]) / n
        out[i] = 100.0 if avg_l == 0 else 100.0 - 100.0 / (1.0 + avg_g / avg_l)
    return out


def _rolling(x: np.ndarray, n: int, fn) -> np.ndarray:
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        out[n - 1 :] = fn(sliding_window_view(x, n), axis=1)
    return out


def _shift(x: np.ndarray, k: int) -> np.ndarray:
    if k == 0:
        return x
    out = np.full(len(x), np.nan)
    out[k:] = x[:-k]
    return out


class Series:
    """Price arrays truncated at the last evaluated bar, plus an indicator cache."""

    def __init__(self, open_, high, low, close, volume):
        self.data = {"open": open_, "high": high, "low": low, "close": close, "volume": volume}
        self._cache: dict[tuple, np.ndarray] = {}

    def __len__(self) -> int:
        return len(self.data["close"])

    def operand(self, o: Operand) -> np.ndarray:
        if o.kind == "value":
            return np.full(len(self), float(o.value))
        key = (o.indicator, o.period, o.source, o.std_mult, o.fast, o.slow, o.signal_period)
        if key not in self._cache:
            self._cache[key] = self._compute(o)
        return _shift(self._cache[key], o.offset) * o.scale

    def _compute(self, o: Operand) -> np.ndarray:
        d, ind, p = self.data, o.indicator, o.period
        if ind in PRICE_FIELDS:
            return d[ind].astype(float)
        if ind == "sma":
            return sma(d[o.source or "close"], p)
        if ind == "ema":
            return ema(d[o.source or "close"], p)
        if ind == "rsi":
            return rsi(d["close"], p)
        if ind in MACD_FAMILY:
            fast, slow, sig = o.fast or 12, o.slow or 26, o.signal_period or 9
            line = ema(d["close"], fast) - ema(d["close"], slow)
            line[: slow - 1] = np.nan
            if ind == "macd":
                return line
            signal = ema(line, sig)
            return signal if ind == "macd_signal" else line - signal
        if ind in ("bb_upper", "bb_middle", "bb_lower"):
            mid = sma(d["close"], p)
            if ind == "bb_middle":
                return mid
            sd = _rolling(d["close"], p, np.std)
            k = o.std_mult or 2.0
            return mid + k * sd if ind == "bb_upper" else mid - k * sd
        if ind == "highest_high":
            return _shift(_rolling(d["high"], p, np.max), 1)
        if ind == "lowest_low":
            return _shift(_rolling(d["low"], p, np.min), 1)
        if ind == "return_pct":
            c = d["close"]
            return (c / _shift(c, p) - 1.0) * 100.0
        if ind == "volatility_pct":
            c = d["close"]
            r = np.full(len(c), np.nan)
            r[1:] = (c[1:] / c[:-1] - 1.0) * 100.0
            out = np.full(len(c), np.nan)
            if len(c) > p:
                out[p:] = sliding_window_view(r[1:], p).std(axis=1, ddof=1)
            return out
        raise ValueError(f"Unknown indicator {ind}")


def _compare(s: Series, c: Comparison) -> np.ndarray:
    a, b = s.operand(c.left), s.operand(c.right)
    with np.errstate(invalid="ignore"):
        if c.op == ">":
            out = a > b
        elif c.op == "<":
            out = a < b
        elif c.op == ">=":
            out = a >= b
        elif c.op == "<=":
            out = a <= b
        else:
            pa, pb = _shift(a, 1), _shift(b, 1)
            if c.op == "crosses_above":
                out = (a > b) & (pa <= pb)
            else:
                out = (a < b) & (pa >= pb)
    # Any comparison touching an undefined value is False, never True.
    defined = ~np.isnan(a) & ~np.isnan(b)
    if c.op.startswith("crosses"):
        defined &= ~np.isnan(_shift(a, 1)) & ~np.isnan(_shift(b, 1))
    return out & defined


def _combine(mode: str, parts: list[np.ndarray], n: int) -> np.ndarray:
    if mode == "all":
        return np.logical_and.reduce(parts) if parts else np.ones(n, bool)
    return np.logical_or.reduce(parts) if parts else np.zeros(n, bool)


def evaluate_condition(s: Series, cond: Condition | None) -> np.ndarray:
    n = len(s)
    if cond is None:
        return np.zeros(n, bool)
    parts = [_compare(s, r) for r in cond.rules]
    parts += [_combine(g.mode, [_compare(s, r) for r in g.rules], n) for g in cond.groups]
    return _combine(cond.mode, parts, n)


def describe(spec: RuleSpec) -> list[str]:
    """Human-readable rule lines for the UI."""

    def cond_text(c: Condition) -> str:
        joiner = " AND " if c.mode == "all" else " OR "
        parts = [r.label() for r in c.rules]
        for g in c.groups:
            inner = (" AND " if g.mode == "all" else " OR ").join(r.label() for r in g.rules)
            parts.append(f"({inner})")
        return joiner.join(parts)

    lines = [f"Direction: {spec.direction.replace('_', ' ')}"]
    for name, c in (
        ("Enter long when", spec.long_entry),
        ("Exit long when", spec.long_exit),
        ("Enter short when", spec.short_entry),
        ("Exit short when", spec.short_exit),
    ):
        if c:
            lines.append(f"{name}: {cond_text(c)}")
    if spec.stop_loss_pct:
        lines.append(
            f"Stop-loss: {spec.stop_loss_pct:g}% against the entry price (checked at close)"
        )
    if spec.take_profit_pct:
        lines.append(f"Take-profit: {spec.take_profit_pct:g}% in favour (checked at close)")
    if spec.max_holding_days:
        lines.append(f"Maximum holding period: {spec.max_holding_days} trading days")
    return lines


_PRICE_WORDS = {
    "close": "the closing price",
    "open": "the opening price",
    "high": "the day's high",
    "low": "the day's low",
    "volume": "volume",
}
_OP_WORDS = {
    ">": "is above",
    "<": "is below",
    ">=": "is at or above",
    "<=": "is at or below",
    "crosses_above": "crosses above",
    "crosses_below": "crosses below",
}
_PERCENT_INDICATORS = {"return_pct", "volatility_pct"}


def _operand_words(o: Operand, percent: bool = False) -> str:
    if o.kind == "value":
        return f"{o.value:g}%" if percent else f"{o.value:g}"
    ind, p = o.indicator, o.period
    if ind in PRICE_FIELDS:
        base = _PRICE_WORDS[ind]
    elif ind in ("sma", "ema"):
        kind = "average" if ind == "sma" else "exponential average"
        of = "" if (o.source or "close") == "close" else f" of {_PRICE_WORDS[o.source]}"
        base = f"the {p}-day {kind}{of}"
    elif ind == "rsi":
        base = f"the {p}-day RSI"
    elif ind in MACD_FAMILY:
        name = {
            "macd": "the MACD line",
            "macd_signal": "the MACD signal line",
            "macd_hist": "the MACD histogram",
        }[ind]
        fast, slow, sig = o.fast or 12, o.slow or 26, o.signal_period or 9
        base = name if (fast, slow, sig) == (12, 26, 9) else f"{name} ({fast}/{slow}/{sig})"
    elif ind and ind.startswith("bb_"):
        band = {"bb_upper": "upper", "bb_middle": "middle", "bb_lower": "lower"}[ind]
        width = o.std_mult or 2
        base = (
            f"the {band} Bollinger band ({p}-day" + ("" if width == 2 else f", {width:g} std") + ")"
        )
    elif ind == "highest_high":
        base = f"the highest high of the previous {p} days"
    elif ind == "lowest_low":
        base = f"the lowest low of the previous {p} days"
    elif ind == "return_pct":
        base = f"the {p}-day % change"
    else:
        base = f"the {p}-day volatility"
    if o.offset:
        base = f"{base} {o.offset} day{'s' if o.offset > 1 else ''} ago"
    if o.scale != 1.0:
        diff = abs(o.scale - 1) * 100
        if diff < 50:
            base = f"{base} {'+' if o.scale > 1 else '−'} {diff:.4g}%"
        else:
            base = f"{o.scale:g}× {base}"
    return base


def _comparison_words(c: Comparison) -> str:
    def pct(side: Operand, other: Operand) -> bool:
        return side.kind == "value" and other.indicator in _PERCENT_INDICATORS

    left = _operand_words(c.left, pct(c.left, c.right))
    right = _operand_words(c.right, pct(c.right, c.left))
    return f"{left} {_OP_WORDS[c.op]} {right}"


def _condition_words(c: Condition) -> str:
    def join(mode: str, items: list[str]) -> str:
        return (" and " if mode == "all" else " or ").join(items)

    parts = [_comparison_words(r) for r in c.rules]
    for g in c.groups:
        inner = join(g.mode, [_comparison_words(r) for r in g.rules])
        parts.append(f"({inner})" if len(g.rules) > 1 else inner)
    return join(c.mode, parts)


def explain(spec: RuleSpec) -> list[str]:
    """The same rules as `describe`, in plain English for non-programmers."""
    lines = [
        {
            "long_only": "Only buys. When not in a trade, the money sits in cash.",
            "short_only": "Only sells short (bets on a fall). Otherwise it sits in cash.",
            "long_short": "Can buy (bet on a rise) or sell short (bet on a fall).",
        }[spec.direction]
    ]
    for label, c in (
        ("Buy when", spec.long_entry),
        ("Sell when", spec.long_exit),
        ("Sell short when", spec.short_entry),
        ("Buy back the short when", spec.short_exit),
    ):
        if c:
            lines.append(f"{label} {_condition_words(c)}.")
    if spec.stop_loss_pct:
        lines.append(
            f"Stop-loss: exit if a trade is down {spec.stop_loss_pct:g}% (checked at each close)."
        )
    if spec.take_profit_pct:
        lines.append(
            f"Take-profit: exit once a trade is up {spec.take_profit_pct:g}% "
            "(checked at each close)."
        )
    if spec.max_holding_days:
        lines.append(f"Never hold a trade longer than {spec.max_holding_days} trading days.")
    risk_exit = spec.stop_loss_pct or spec.take_profit_pct or spec.max_holding_days
    if not risk_exit:
        if spec.direction == "long_only" and not spec.long_exit:
            lines.append(
                "There is no sell rule, so once it buys it holds until the end of the test."
            )
        if spec.direction == "short_only" and not spec.short_exit:
            lines.append(
                "There is no exit rule, so once it shorts it stays short until the end of the test."
            )
    lines.append("Signals are checked at each day's close; trades happen at the next day's open.")
    return lines
