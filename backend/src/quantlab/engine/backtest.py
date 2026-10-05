"""Strategy backtests (MA crossover or chatbot-built rules) and buy-and-hold.

Timing convention (see docs/architecture.md, "Backtest conventions"):

* The decision after the close of day t uses bars up to and including day t.
  MA crossover: target = long if SMA_short > SMA_long, else cash.
  Rules: entry/exit conditions plus stop-loss / take-profit / holding limits,
  all evaluated at the close (no intraday stops).
* The target decided at close t executes at the OPEN of day t+1. The price
  that produced the decision (close[t]) is never the execution price.
* The portfolio is marked to market at every close: equity = cash + shares*close
  (shares are negative while short).
* Buys and short covers pay exec = open * (1 + slippage); sells and short
  entries get exec = open * (1 - slippage); every trade pays fee_rate * notional.
* Positions are all-in: long spends all cash, short sells shares worth the
  current equity (1x). Shorts ignore borrow fees, margin interest and margin
  calls; if equity reaches zero the run fails rather than report nonsense.
* Evaluation window [start, end]: the first evaluated day d0 executes the
  decision from the bar before d0, so every indicator must be warmed up using
  bars strictly before `start`. Bars after `end` are never read.
* Buy-and-hold buys at the open of d0 with the same costs and share rule and is
  never sold. Both strategies start with the same cash at the open of d0.
* An open position at the end is marked at the final close; no exit trade or
  exit cost is simulated for either strategy.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from quantlab.engine.data import Bars, to_iso
from quantlab.engine.rules import RuleSpec, Series, evaluate_condition

MIN_EVAL_DAYS = 20
MAX_WINDOW = 400


class BacktestInputError(ValueError):
    """Invalid configuration or data. Retrying will not help."""


@dataclass(frozen=True)
class StrategyParams:
    short_window: int | None
    long_window: int | None
    initial_capital: float
    fee_bps: float = 0.0
    slippage_bps: float = 0.0
    allow_fractional: bool = True
    rules: RuleSpec | None = None  # set for chatbot-built strategies

    def warmup_bars(self) -> int:
        return self.rules.warmup_bars() if self.rules else self.long_window

    def validate(self) -> None:
        if self.rules is None and not (
            self.short_window is not None
            and self.long_window is not None
            and 1 <= self.short_window < self.long_window <= MAX_WINDOW
        ):
            raise BacktestInputError(
                f"Windows must satisfy 1 <= short < long <= {MAX_WINDOW}; "
                f"got short={self.short_window}, long={self.long_window}."
            )
        if not (math.isfinite(self.initial_capital) and self.initial_capital > 0):
            raise BacktestInputError("Initial capital must be a positive number.")
        for name in ("fee_bps", "slippage_bps"):
            v = getattr(self, name)
            if not (math.isfinite(v) and 0 <= v <= 500):
                raise BacktestInputError(f"{name} must be between 0 and 500 basis points.")


@dataclass
class TradeRecord:
    seq: int
    signal_date: str
    trade_date: str
    side: str
    open_price: float
    exec_price: float
    shares: float
    notional: float
    fee: float
    slippage_cost: float
    cash_after: float


@dataclass
class LedgerResult:
    equity: np.ndarray  # value at each evaluated close
    position: np.ndarray  # shares held at each evaluated close
    trades: list[TradeRecord] = field(default_factory=list)
    total_fees: float = 0.0
    total_slippage: float = 0.0


@dataclass
class BacktestOutput:
    dates: list[str]
    strategy: LedgerResult
    benchmark: LedgerResult
    signal: np.ndarray  # target (-1/0/1) decided at each evaluated close
    short_ma: np.ndarray | None
    long_ma: np.ndarray | None
    notes: list[str]


@dataclass(frozen=True)
class Window:
    start_idx: int
    end_idx: int


def resolve_window(
    bars: Bars,
    start: date,
    end: date,
    long_window: int,
    min_days: int = MIN_EVAL_DAYS,
    what: str | None = None,
) -> Window:
    """Map calendar dates to bar indexes and check warm-up and length.

    `long_window` is the number of bars required strictly before `start`.
    """
    if start >= end:
        raise BacktestInputError("Start date must be before end date.")
    s = int(np.searchsorted(bars.dates, np.datetime64(start, "D"), side="left"))
    e = int(np.searchsorted(bars.dates, np.datetime64(end, "D"), side="right")) - 1
    if s >= len(bars) or e < 0 or e < s:
        raise BacktestInputError("No trading days in the selected date range.")
    n = e - s + 1
    if n < min_days:
        raise BacktestInputError(
            f"Only {n} trading days between {start} and {end}; need at least {min_days}."
        )
    # Signal for the bar before d0 needs `long_window` closes ending at index s-1.
    if s < long_window:
        earliest = bars.date_at(long_window) if long_window < len(bars) else None
        hint = f" Earliest valid start is {earliest}." if earliest else ""
        what = what or f"a {long_window}-day moving average"
        raise BacktestInputError(
            f"Not enough history before {bars.date_at(s)} to warm up {what} "
            f"({s} prior bars available, {long_window} needed).{hint}"
        )
    return Window(s, e)


def earliest_start(bars: Bars, long_window: int) -> date | None:
    return bars.date_at(long_window) if long_window < len(bars) else None


def moving_average(values: np.ndarray, window: int) -> np.ndarray:
    """Trailing simple moving average; NaN until `window` values exist."""
    out = np.full(len(values), np.nan)
    if len(values) >= window:
        out[window - 1 :] = sliding_window_view(values, window).mean(axis=1)
    return out


def crossover_signal(close: np.ndarray, short_window: int, long_window: int):
    short_ma = moving_average(close, short_window)
    long_ma = moving_average(close, long_window)
    valid = ~np.isnan(long_ma)
    signal = np.zeros(len(close), dtype=np.int8)
    signal[valid] = (short_ma[valid] > long_ma[valid]).astype(np.int8)
    return signal, short_ma, long_ma


class _Ledger:
    def __init__(self, cash: float, fee_rate: float, slip_rate: float, fractional: bool):
        self.cash = cash
        self.shares = 0.0
        self.fee_rate = fee_rate
        self.slip_rate = slip_rate
        self.fractional = fractional
        self.trades: list[TradeRecord] = []
        self.total_fees = 0.0
        self.total_slippage = 0.0

    def buy_all(self, open_price: float, trade_date: str, signal_date: str) -> bool:
        exec_price = open_price * (1.0 + self.slip_rate)
        cost_per_share = exec_price * (1.0 + self.fee_rate)
        shares = self.cash / cost_per_share
        if not self.fractional:
            shares = math.floor(shares + 1e-9)
        if shares <= 0:
            return False
        notional = shares * exec_price
        fee = notional * self.fee_rate
        # Clamp tiny negative residue from floating point when spending all cash.
        self.cash = max(self.cash - notional - fee, 0.0)
        self.shares = shares
        self._record("buy", open_price, exec_price, shares, notional, fee, trade_date, signal_date)
        return True

    def sell_all(self, open_price: float, trade_date: str, signal_date: str) -> None:
        exec_price = open_price * (1.0 - self.slip_rate)
        shares = self.shares
        notional = shares * exec_price
        fee = notional * self.fee_rate
        self.cash += notional - fee
        self.shares = 0.0
        self._record("sell", open_price, exec_price, shares, notional, fee, trade_date, signal_date)

    def short_all(self, open_price: float, trade_date: str, signal_date: str) -> bool:
        """Sell borrowed shares worth the current cash (1x short exposure)."""
        exec_price = open_price * (1.0 - self.slip_rate)
        shares = self.cash / exec_price
        if not self.fractional:
            shares = math.floor(shares + 1e-9)
        if shares <= 0:
            return False
        notional = shares * exec_price
        fee = notional * self.fee_rate
        self.cash += notional - fee
        self.shares = -shares
        self._record(
            "short", open_price, exec_price, shares, notional, fee, trade_date, signal_date
        )
        return True

    def cover_all(self, open_price: float, trade_date: str, signal_date: str) -> None:
        exec_price = open_price * (1.0 + self.slip_rate)
        shares = -self.shares
        notional = shares * exec_price
        fee = notional * self.fee_rate
        self.cash -= notional + fee
        self.shares = 0.0
        self._record(
            "cover", open_price, exec_price, shares, notional, fee, trade_date, signal_date
        )

    def _record(self, side, open_price, exec_price, shares, notional, fee, trade_date, signal_date):
        slippage = abs(exec_price - open_price) * shares
        self.total_fees += fee
        self.total_slippage += slippage
        self.trades.append(
            TradeRecord(
                seq=len(self.trades) + 1,
                signal_date=signal_date,
                trade_date=trade_date,
                side=side,
                open_price=open_price,
                exec_price=exec_price,
                shares=shares,
                notional=notional,
                fee=fee,
                slippage_cost=slippage,
                cash_after=self.cash,
            )
        )


class _RuleDecider:
    """Turns a RuleSpec into a per-close target position (-1, 0, +1)."""

    def __init__(self, spec: RuleSpec, series: Series):
        self.spec = spec
        self.longs = spec.direction in ("long_only", "long_short")
        self.shorts = spec.direction in ("short_only", "long_short")
        self.long_entry = evaluate_condition(series, spec.long_entry)
        self.long_exit = evaluate_condition(series, spec.long_exit)
        self.short_entry = evaluate_condition(series, spec.short_entry)
        self.short_exit = evaluate_condition(series, spec.short_exit)
        self.close = series.data["close"]
        self.exit_reasons: dict[str, int] = {}

    def _exit_hit(self, t: int, side: int, entry_price: float, held: int) -> bool:
        spec, c = self.spec, self.close[t]
        move = (c / entry_price - 1.0) * 100.0 * side  # % gain in the position's favour
        reason = None
        if (self.long_exit if side == 1 else self.short_exit)[t]:
            reason = "exit rule"
        elif spec.stop_loss_pct is not None and move <= -spec.stop_loss_pct:
            reason = "stop-loss"
        elif spec.take_profit_pct is not None and move >= spec.take_profit_pct:
            reason = "take-profit"
        elif spec.max_holding_days is not None and held >= spec.max_holding_days:
            reason = "max holding period"
        if reason:
            self.exit_reasons[reason] = self.exit_reasons.get(reason, 0) + 1
        return reason is not None

    def decide(self, t: int, side: int, entry_price: float, held: int) -> int:
        enter_long = self.longs and self.long_entry[t]
        enter_short = self.shorts and self.short_entry[t]
        if side == 0:
            return 1 if enter_long else -1 if enter_short else 0
        opposite = enter_short if side == 1 else enter_long
        if self._exit_hit(t, side, entry_price, held) or opposite:
            return -side if opposite else 0
        return side


def run_backtest(
    bars: Bars, params: StrategyParams, start: date, end: date, min_days: int = MIN_EVAL_DAYS
) -> BacktestOutput:
    params.validate()
    warmup = params.warmup_bars()
    what = "every indicator in this strategy" if params.rules else None
    win = resolve_window(bars, start, end, warmup, min_days, what)
    s, e = win.start_idx, win.end_idx

    # Only bars up to `end` are visible to decisions: no future data can leak in.
    short_ma = long_ma = None
    if params.rules:
        series = Series(
            bars.open[: e + 1],
            bars.high[: e + 1],
            bars.low[: e + 1],
            bars.close[: e + 1],
            bars.volume[: e + 1],
        )
        rules = _RuleDecider(params.rules, series)
    else:
        rules = None
        signal, short_ma, long_ma = crossover_signal(
            bars.close[: e + 1], params.short_window, params.long_window
        )

    fee_rate = params.fee_bps / 10_000.0
    slip_rate = params.slippage_bps / 10_000.0
    strat = _Ledger(params.initial_capital, fee_rate, slip_rate, params.allow_fractional)
    bench = _Ledger(params.initial_capital, fee_rate, slip_rate, params.allow_fractional)
    notes: list[str] = []

    n = e - s + 1
    strat_equity = np.empty(n)
    strat_pos = np.empty(n)
    bench_equity = np.empty(n)
    bench_pos = np.empty(n)
    decisions = np.zeros(n, dtype=np.int8)
    dates = [to_iso(bars.dates[i]) for i in range(s, e + 1)]
    unaffordable = 0
    entry_price, entry_t = 0.0, 0

    def decide(t: int) -> int:
        if rules is None:
            return int(signal[t])
        side = int(np.sign(strat.shares))
        return rules.decide(t, side, entry_price, t - entry_t + 1)

    target = decide(s - 1)  # flat before d0, so state does not matter yet
    for k, t in enumerate(range(s, e + 1)):
        today = dates[k]
        signal_day = to_iso(bars.dates[t - 1])
        open_t = float(bars.open[t])

        if k == 0 and not bench.buy_all(open_t, today, signal_day):
            raise BacktestInputError(
                "Initial capital cannot buy one whole share at the first open; "
                "increase capital or allow fractional shares."
            )

        side = int(np.sign(strat.shares))
        if target != side:
            if side == 1:
                strat.sell_all(open_t, today, signal_day)
            elif side == -1:
                strat.cover_all(open_t, today, signal_day)
            opened = True
            if target == 1:
                opened = strat.buy_all(open_t, today, signal_day)
            elif target == -1:
                opened = strat.short_all(open_t, today, signal_day)
            if not opened:
                unaffordable += 1
            elif target != 0:
                entry_price, entry_t = strat.trades[-1].exec_price, t

        close_t = float(bars.close[t])
        strat_equity[k] = strat.cash + strat.shares * close_t
        strat_pos[k] = strat.shares
        bench_equity[k] = bench.cash + bench.shares * close_t
        bench_pos[k] = bench.shares
        if strat_equity[k] <= 0:
            raise BacktestInputError(
                f"The short position lost all capital by {today}. Real brokers would have "
                "issued a margin call; add a stop-loss or reduce the short exposure."
            )
        target = decide(t)
        decisions[k] = target

    if unaffordable:
        notes.append(
            f"{unaffordable} entry signal(s) skipped because cash could not trade one whole share."
        )
    if strat.shares != 0:
        notes.append(
            "Strategy ends with an open position; it is marked at the last close "
            "without simulated exit costs."
        )
    if any(tr.side == "short" for tr in strat.trades):
        notes.append(
            "Short positions ignore borrow fees, margin interest and margin calls, "
            "so short results are optimistic."
        )
    if rules and rules.exit_reasons:
        reasons = ", ".join(f"{v} by {k}" for k, v in sorted(rules.exit_reasons.items()))
        notes.append(f"Exits (evaluated at the close, filled next open): {reasons}.")
    notes.append("Buy-and-hold is marked at the last close without simulated exit costs.")

    return BacktestOutput(
        dates=dates,
        strategy=LedgerResult(
            strat_equity, strat_pos, strat.trades, strat.total_fees, strat.total_slippage
        ),
        benchmark=LedgerResult(
            bench_equity, bench_pos, bench.trades, bench.total_fees, bench.total_slippage
        ),
        signal=decisions,
        short_ma=None if short_ma is None else short_ma[s : e + 1].copy(),
        long_ma=None if long_ma is None else long_ma[s : e + 1].copy(),
        notes=notes,
    )
