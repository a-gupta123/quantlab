import numpy as np
import pytest
from helpers import make_bars, random_walk_bars
from pydantic import ValidationError

from quantlab.engine.backtest import BacktestInputError, StrategyParams, run_backtest
from quantlab.engine.rules import RuleSpec, Series, describe, ema, rsi


def ind(name, **kw):
    return {"kind": "indicator", "indicator": name, **kw}


def val(v):
    return {"kind": "value", "value": v}


def spec(**kw) -> RuleSpec:
    return RuleSpec.model_validate(kw)


def run(bars, rules, s, e, **kw):
    p = StrategyParams(None, None, kw.pop("capital", 1000.0), rules=rules, **kw)
    return run_backtest(bars, p, bars.date_at(s), bars.date_at(e), min_days=2)


# ------------------------------------------------------------- indicators


def test_indicators_are_trailing_and_hand_checkable():
    up = np.arange(1.0, 31.0)
    r = rsi(up, 14)
    assert np.isnan(r[13]) and r[14] == 100.0  # no losses -> RSI 100
    e = ema(np.array([1.0, 2, 3, 4, 5]), 3)
    assert np.isnan(e[1]) and e[2] == pytest.approx(2.0)  # seeded with SMA(1,2,3)
    assert e[3] == pytest.approx(0.5 * 4 + 0.5 * 2.0)

    bars = make_bars([10, 11, 12, 13, 14], [10, 11, 12, 13, 14])
    s = Series(bars.open, bars.high, bars.low, bars.close, bars.volume)
    hh = s.operand(
        RuleSpec.model_validate(
            {
                "direction": "long_only",
                "long_entry": {
                    "mode": "all",
                    "rules": [
                        {"left": ind("close"), "op": ">", "right": ind("highest_high", period=2)}
                    ],
                },
            }
        )
        .long_entry.rules[0]
        .right
    )
    # Highest high of the two bars *before* t, so today's bar never counts.
    assert np.isnan(hh[1]) and hh[2] == pytest.approx(max(bars.high[0], bars.high[1]))


# -------------------------------------------------------------- accounting

# idx:     0   1   2   3   4   5   6   7
OPENS = [10, 10, 12, 12, 10, 9, 10, 13]
CLOSES = [10, 11, 12, 11, 10, 9, 12, 13]
DOWN_DAY = {
    "mode": "all",
    "rules": [{"left": ind("close"), "op": "<", "right": ind("close", offset=1)}],
}
UP_DAY = {
    "mode": "all",
    "rules": [{"left": ind("close"), "op": ">", "right": ind("close", offset=1)}],
}


def test_short_trade_hand_calculated():
    # Down close on day 3 -> short at day 4 open (10); up close day 6 -> cover day 7 open (13).
    out = run(
        make_bars(OPENS, CLOSES),
        spec(direction="short_only", short_entry=DOWN_DAY, short_exit=UP_DAY),
        2,
        7,
    )
    t = out.strategy.trades
    assert [(x.side, x.trade_date, x.exec_price, x.shares) for x in t] == [
        ("short", out.dates[2], 10.0, 100.0),
        ("cover", out.dates[5], 13.0, 100.0),
    ]
    assert all(x.signal_date < x.trade_date for x in t)
    # equity = cash + shares*close: 2000 - 100*close while short, then 2000 - 1300.
    np.testing.assert_allclose(out.strategy.equity, [1000, 1000, 1000, 1100, 800, 700])
    assert list(out.signal) == [0, -1, -1, -1, 0, 0]
    assert any("borrow fees" in n for n in out.notes)


def test_short_costs():
    out = run(
        make_bars(OPENS, CLOSES),
        spec(direction="short_only", short_entry=DOWN_DAY, short_exit=UP_DAY),
        2,
        7,
        fee_bps=100,
    )
    # short: +1000 proceeds -10 fee; cover: -1300 -13 fee.
    assert out.strategy.equity[-1] == pytest.approx(1000 + 1000 - 10 - 1300 - 13)
    assert out.strategy.total_fees == pytest.approx(23)


def test_stop_loss_checked_at_close_filled_next_open():
    opens = [100, 100, 100, 96, 97, 97, 97]
    closes = [100, 100, 94, 96, 97, 97, 97]
    always = {"mode": "all", "rules": [{"left": ind("close"), "op": ">", "right": val(0)}]}
    out = run(
        make_bars(opens, closes),
        spec(direction="long_only", long_entry=always, stop_loss_pct=5),
        1,
        6,
    )
    sides = [(x.side, x.trade_date, x.exec_price) for x in out.strategy.trades]
    # Close of day 2 is 6% below the 100 entry -> sell at day 3 open (96), re-enter day 4.
    assert sides[:2] == [("buy", out.dates[0], 100.0), ("sell", out.dates[2], 96.0)]
    assert sides[2][0] == "buy" and sides[2][1] == out.dates[3]
    assert any("stop-loss" in n for n in out.notes)


def test_max_holding_days_and_flip():
    bars = random_walk_bars(300, seed=3)
    rules = spec(
        direction="long_short",
        long_entry={
            "mode": "all",
            "rules": [{"left": ind("rsi", period=14), "op": "<", "right": val(40)}],
        },
        short_entry={
            "mode": "all",
            "rules": [{"left": ind("rsi", period=14), "op": ">", "right": val(60)}],
        },
        max_holding_days=5,
    )
    out = run(bars, rules, 30, 299)
    entries = [x for x in out.strategy.trades if x.side in ("buy", "short")]
    assert entries, "expected some trades"
    for a, b in zip(out.strategy.trades, out.strategy.trades[1:], strict=False):
        assert a.trade_date <= b.trade_date


def test_short_wipeout_fails_clearly():
    opens = [10, 10, 10, 30, 60]
    closes = [10, 10, 10, 30, 60]
    always = {"mode": "all", "rules": [{"left": ind("close"), "op": ">", "right": val(0)}]}
    with pytest.raises(BacktestInputError, match="lost all capital"):
        run(make_bars(opens, closes), spec(direction="short_only", short_entry=always), 1, 4)


# ---------------------------------------------------------- correctness


def test_rules_reproduce_the_ma_crossover_engine_exactly():
    bars = random_walk_bars(500, seed=11)
    s, e = 60, 499
    ma = run_backtest(bars, StrategyParams(10, 30, 1000.0, 5, 5), bars.date_at(s), bars.date_at(e))
    cross = {"left": ind("sma", period=10), "right": ind("sma", period=30)}
    rules = spec(
        direction="long_only",
        long_entry={"mode": "all", "rules": [{**cross, "op": ">"}]},
        long_exit={"mode": "all", "rules": [{**cross, "op": "<="}]},
    )
    out = run(bars, rules, s, e, fee_bps=5, slippage_bps=5)
    assert [(t.side, t.trade_date, t.shares) for t in out.strategy.trades] == [
        (t.side, t.trade_date, t.shares) for t in ma.strategy.trades
    ]
    np.testing.assert_allclose(out.strategy.equity, ma.strategy.equity)
    assert rules.warmup_bars() == 30


def test_no_lookahead_future_bars_do_not_change_past_decisions():
    bars = random_walk_bars(400, seed=5)
    rules = spec(
        direction="long_short",
        long_entry={
            "mode": "any",
            "rules": [{"left": ind("macd"), "op": "crosses_above", "right": ind("macd_signal")}],
            "groups": [
                {
                    "mode": "all",
                    "rules": [
                        {"left": ind("close"), "op": "<", "right": ind("bb_lower", period=20)}
                    ],
                }
            ],
        },
        short_entry={
            "mode": "all",
            "rules": [{"left": ind("return_pct", period=5), "op": "<", "right": val(-2)}],
        },
        stop_loss_pct=4,
        take_profit_pct=8,
    )
    short = run(bars, rules, 60, 250)
    full = run(bars, rules, 60, 399)
    n = len(short.dates)
    assert list(short.signal) == list(full.signal[:n])
    np.testing.assert_allclose(short.strategy.equity, full.strategy.equity[:n])


def test_warmup_is_enforced():
    bars = random_walk_bars(100)
    rules = spec(
        direction="long_only",
        long_entry={
            "mode": "all",
            "rules": [{"left": ind("sma", period=50), "op": ">", "right": val(0)}],
        },
    )
    with pytest.raises(BacktestInputError, match="every indicator"):
        run(bars, rules, 20, 99)


# ---------------------------------------------------------- validation


@pytest.mark.parametrize(
    "bad, match",
    [
        ({"direction": "long_only"}, "needs a long_entry"),
        ({"direction": "long_only", "long_entry": UP_DAY, "short_entry": DOWN_DAY}, "long_only"),
        (
            {
                "direction": "long_only",
                "long_entry": {
                    "mode": "all",
                    "rules": [{"left": ind("sma"), "op": ">", "right": val(1)}],
                },
            },
            "needs a 'period'",
        ),
        (
            {
                "direction": "long_only",
                "long_entry": {
                    "mode": "all",
                    "rules": [{"left": ind("macd", fast=30, slow=10), "op": ">", "right": val(0)}],
                },
            },
            "fast",
        ),
        ({"direction": "long_only", "long_entry": {"mode": "all"}}, "at least one"),
        ({"direction": "long_only", "long_entry": UP_DAY, "stop_loss_pct": 0}, "greater than"),
        ({"direction": "long_only", "long_entry": UP_DAY, "evil": "import os"}, "Extra"),
    ],
)
def test_invalid_specs_are_rejected(bad, match):
    with pytest.raises(ValidationError, match=match):
        RuleSpec.model_validate(bad)


def test_describe_is_readable():
    lines = describe(spec(direction="long_only", long_entry=UP_DAY, stop_loss_pct=5))
    assert lines[1] == "Enter long when: close > close[1 bars ago]"
    assert "Stop-loss: 5%" in lines[2]


def test_volume_missing_never_triggers():
    bars = random_walk_bars(60)
    assert np.isnan(bars.volume).all()
    rules = spec(
        direction="long_only",
        long_entry={
            "mode": "all",
            "rules": [
                {"left": ind("volume"), "op": ">", "right": ind("sma", period=5, source="volume")}
            ],
        },
    )
    out = run(bars, rules, 10, 59)
    assert out.strategy.trades == []
