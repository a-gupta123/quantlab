from datetime import date, timedelta

import numpy as np

from quantlab.engine.data import Bars


def business_days(start: date, n: int) -> list[date]:
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def make_bars(opens, closes, start: date = date(2024, 1, 1)) -> Bars:
    opens = np.asarray(opens, dtype=float)
    closes = np.asarray(closes, dtype=float)
    days = business_days(start, len(opens))
    return Bars(
        dates=np.array(days, dtype="datetime64[D]"),
        open=opens,
        high=np.maximum(opens, closes) * 1.01,
        low=np.minimum(opens, closes) * 0.99,
        close=closes,
    )


def random_walk_bars(n: int, seed: int = 7, start: date = date(2015, 1, 1)) -> Bars:
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, n)))
    gap = rng.normal(0, 0.003, n)
    opens = np.concatenate(([100.0], close[:-1])) * np.exp(gap)
    return make_bars(opens, close, start)


def csv_bytes(rows, header="date,open,high,low,close,volume") -> bytes:
    return ("\n".join([header, *rows]) + "\n").encode()
