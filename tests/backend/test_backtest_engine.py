from datetime import date

import numpy as np
import pytest
from helpers import make_bars, random_walk_bars

from quantlab.engine.backtest import (
    BacktestInputError,
    StrategyParams,
    crossover_signal,
    moving_average,
    run_backtest,
)

# Hand-calculated series with windows short=1 / long=2, so
# signal[t] = close[t] > (close[t-1] + close[t]) / 2, i.e. "close above yesterday's close".
#  idx:      0   1   2   3   4   5   6   7
OPENS = [10, 10, 12, 12, 10, 9, 10, 13]
CLOSES = [10, 11, 12, 11, 10, 9, 12, 13]
# signal:    0   1   1   0   0   0   1   1


def hand_bars():
    return make_bars(OPENS, CLOSES)


def params(**kw):
    base = dict(short_window=1, long_window=2, initial_capital=1000.0)
    base.update(kw)
    return StrategyParams(**base)


def run(bars, p, start_idx=2, end_idx=7):
    return run_backtest(bars, p, bars.date_at(start_idx), bars.date_at(end_idx), min_days=2)


def test_moving_average_and_signal():
    np.testing.assert_allclose(moving_average(np.array([1.0, 2, 3, 4]), 2)[1:], [1.5, 2.5, 3.5])
    assert np.isnan(moving_average(np.array([1.0, 2, 3]), 2)[0])
    sig, _, _ = crossover_signal(np.array(CLOSES, dtype=float), 1, 2)
    assert sig.tolist() == [0, 1, 1, 0, 0, 0, 1, 1]


def test_hand_calculated_ledger_without_costs():
    out = run(hand_bars(), params())
    s = out.strategy
    # k=0 (idx2): signal[1]=1 -> buy at open 12 with $1000 -> 83.333 shares, marked at close 12.
    # k=1 (idx3): hold, close 11      -> 916.667
    # k=2 (idx4): signal[3]=0 -> sell at open 10 -> cash 833.333
    # k=3 (idx5): cash                -> 833.333
    # k=4 (idx6): cash (signal[5]=0)  -> 833.333
    # k=5 (idx7): signal[6]=1 -> buy at open 13 with 833.333 -> 64.103 shares, close 13 -> 833.333
    sh1 = 1000 / 12
    expected = [sh1 * 12, sh1 * 11, sh1 * 10, sh1 * 10, sh1 * 10, sh1 * 10]
    np.testing.assert_allclose(s.equity, expected)
    assert [t.side for t in s.trades] == ["buy", "sell", "buy"]
    assert s.trades[0].shares == pytest.approx(sh1)
    assert s.trades[2].shares == pytest.approx(sh1 * 10 / 13)
    # Buy-and-hold: 83.333 shares at the first open (12), never sold.
    np.testing.assert_allclose(out.benchmark.equity, [sh1 * c for c in CLOSES[2:]])
    assert out.dates[0] == str(hand_bars().date_at(2))


def test_fees_and_slippage_hand_calculated():
    out = run(hand_bars(), params(fee_bps=10, slippage_bps=20))
    buy, sell = out.strategy.trades[0], out.strategy.trades[1]
    exec_buy = 12 * 1.002
    shares = 1000 / (exec_buy * 1.001)
    assert buy.exec_price == pytest.approx(exec_buy)
    assert buy.shares == pytest.approx(shares)
    assert buy.fee == pytest.approx(shares * exec_buy * 0.001)
    assert buy.slippage_cost == pytest.approx(shares * 12 * 0.002)
    assert buy.cash_after == pytest.approx(0.0, abs=1e-9)

    exec_sell = 10 * 0.998
    proceeds = shares * exec_sell
    assert sell.exec_price == pytest.approx(exec_sell)
    assert sell.cash_after == pytest.approx(proceeds - proceeds * 0.001)
    # Day-0 equity already reflects the entry costs.
    assert out.strategy.equity[0] == pytest.approx(shares * 12)
    assert out.strategy.equity[0] < 1000
    # Benchmark pays the same entry costs on the same day.
    assert out.benchmark.equity[0] == pytest.approx(shares * 12)
    assert out.strategy.total_fees == pytest.approx(sum(t.fee for t in out.strategy.trades))


def test_whole_shares_leave_cash_residue():
    out = run(hand_bars(), params(allow_fractional=False))
    buy = out.strategy.trades[0]
    assert buy.shares == 83
    assert buy.cash_after == pytest.approx(1000 - 83 * 12)
    assert out.strategy.equity[0] == pytest.approx(1000)


def test_signal_executes_next_open_never_signal_close():
    bars = hand_bars()
    out = run(bars, params())
    for t in out.strategy.trades:
        sig_idx = int(np.searchsorted(bars.dates, np.datetime64(t.signal_date)))
        trade_idx = int(np.searchsorted(bars.dates, np.datetime64(t.trade_date)))
        assert trade_idx == sig_idx + 1
        assert t.open_price == bars.open[trade_idx]


def test_no_lookahead_future_bars_do_not_change_past():
    bars = random_walk_bars(400)
    p = StrategyParams(short_window=10, long_window=50, initial_capital=10_000)
    start, end = bars.date_at(60), bars.date_at(300)
    base = run_backtest(bars, p, start, end)

    # Scramble every bar after index 200: results up to 200 must be identical.
    rng = np.random.default_rng(1)
    shocked_close = bars.close.copy()
    shocked_close[201:] *= np.exp(rng.normal(0, 0.2, len(bars) - 201))
    shocked = type(bars)(bars.dates, bars.open.copy(), bars.high * 2, bars.low / 2, shocked_close)
    alt = run_backtest(shocked, p, start, end)
    cut = 200 - 60  # evaluation index of bar 200
    np.testing.assert_allclose(base.strategy.equity[: cut + 1], alt.strategy.equity[: cut + 1])
    past = [t for t in base.strategy.trades if t.trade_date <= str(bars.date_at(200))]
    alt_past = [t for t in alt.strategy.trades if t.trade_date <= str(bars.date_at(200))]
    assert past == alt_past

    # Data after `end` is never read.
    beyond = bars.close.copy()
    beyond[301:] = 1e6
    far = run_backtest(
        type(bars)(bars.dates, bars.open, bars.high * 1e5, bars.low, beyond), p, start, end
    )
    np.testing.assert_allclose(base.strategy.equity, far.strategy.equity)


def test_close_of_trade_day_does_not_affect_that_days_decision():
    bars = hand_bars()
    # Changing close[2] (the first evaluated day) cannot change the trade at open[2].
    closes = CLOSES.copy()
    closes[2] = 1.0
    alt_bars = make_bars(OPENS, closes)
    a = run(bars, params())
    b = run(alt_bars, params())
    assert a.strategy.trades[0] == b.strategy.trades[0]


def test_warmup_requires_history_before_start():
    bars = random_walk_bars(300)
    p = StrategyParams(short_window=20, long_window=100, initial_capital=1000)
    with pytest.raises(BacktestInputError, match="Earliest valid start is"):
        run_backtest(bars, p, bars.date_at(50), bars.date_at(250))
    out = run_backtest(bars, p, bars.date_at(100), bars.date_at(250))
    assert out.dates[0] == str(bars.date_at(100))


@pytest.mark.parametrize(
    "kw, msg",
    [
        (dict(short_window=50, long_window=50), "short < long"),
        (dict(short_window=60, long_window=50), "short < long"),
        (dict(short_window=0, long_window=50), "short < long"),
        (dict(short_window=5, long_window=401), "short < long"),
        (dict(initial_capital=0), "Initial capital"),
        (dict(initial_capital=float("nan")), "Initial capital"),
        (dict(fee_bps=-1), "fee_bps"),
        (dict(slippage_bps=1000), "slippage_bps"),
    ],
)
def test_invalid_params(kw, msg):
    base = dict(short_window=5, long_window=20, initial_capital=1000.0)
    base.update(kw)
    bars = random_walk_bars(100)
    with pytest.raises(BacktestInputError, match=msg):
        run_backtest(bars, StrategyParams(**base), bars.date_at(30), bars.date_at(90))


def test_insufficient_and_empty_ranges():
    bars = random_walk_bars(100)
    p = StrategyParams(short_window=5, long_window=20, initial_capital=1000)
    with pytest.raises(BacktestInputError, match="need at least 20"):
        run_backtest(bars, p, bars.date_at(30), bars.date_at(35))
    with pytest.raises(BacktestInputError, match="No trading days"):
        run_backtest(bars, p, date(2030, 1, 1), date(2030, 6, 1))
    with pytest.raises(BacktestInputError, match="before end"):
        run_backtest(bars, p, bars.date_at(50), bars.date_at(40))


def test_whole_share_unaffordable_benchmark_raises():
    bars = hand_bars()
    with pytest.raises(BacktestInputError, match="whole share"):
        run(bars, params(initial_capital=5, allow_fractional=False))


def test_strategy_and_benchmark_share_dates():
    bars = random_walk_bars(500)
    p = StrategyParams(short_window=20, long_window=100, initial_capital=5000)
    out = run_backtest(bars, p, bars.date_at(120), bars.date_at(499))
    assert len(out.strategy.equity) == len(out.benchmark.equity) == len(out.dates)
    # Ledger identity: when flat, equity equals the cash after the last sale.
    for t in out.strategy.trades:
        assert t.shares > 0 and t.exec_price > 0
