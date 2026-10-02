"""Helpers that create real rows in the test database."""

from helpers import random_walk_bars

from quantlab.datasets import DatasetMeta, import_dataset, normalised_csv
from quantlab.db import transaction
from quantlab.services import ExperimentRequest, create_experiment
from quantlab.storage import get_storage


def bars_csv(n: int = 700, seed: int = 7) -> bytes:
    import pandas as pd

    bars = random_walk_bars(n, seed=seed)
    df = pd.DataFrame(
        {
            "date": [str(bars.date_at(i)) for i in range(n)],
            "open": bars.open,
            "high": bars.high,
            "low": bars.low,
            "close": bars.close,
            "volume": [1000.0] * n,
        }
    )
    return normalised_csv(df)


def make_dataset(n: int = 700, seed: int = 7, name: str = "TEST-DEMO") -> int:
    get_storage.cache_clear()
    with transaction() as s:
        ds, _ = import_dataset(
            s,
            get_storage(),
            bars_csv(n, seed),
            DatasetMeta(name, "DEMO", "unit test random walk", "synthetic", True),
        )
        return ds.id


def dataset_dates(dataset_id: int):
    from sqlalchemy import select

    from quantlab.models import PriceBar

    with transaction() as s:
        return s.scalars(
            select(PriceBar.trade_date)
            .where(PriceBar.dataset_id == dataset_id)
            .order_by(PriceBar.trade_date)
        ).all()


def make_experiment(dataset_id: int, name: str = "exp", **kw) -> int:
    dates = dataset_dates(dataset_id)
    req = dict(
        name=name,
        dataset_id=dataset_id,
        start_date=dates[150],
        end_date=dates[-1],
        initial_capital=10_000.0,
        short_window=20,
        long_window=100,
        fee_bps=5.0,
        slippage_bps=5.0,
    )
    req.update(kw)
    with transaction() as s:
        return create_experiment(s, ExperimentRequest(**req)).id
