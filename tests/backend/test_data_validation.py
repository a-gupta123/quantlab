import pytest
from helpers import csv_bytes

from quantlab.engine.data import parse_csv

GOOD = [
    "2024-01-02,10,11,9,10.5,100",
    "2024-01-03,10.5,11,10,10.8,120",
    "2024-01-04,10.8,11.2,10.6,11,90",
]


def messages(raw):
    df, report = parse_csv(raw)
    return df, [e.message for e in report.errors], report


def test_valid_file_normalises_headers():
    raw = csv_bytes(GOOD, header="Date,Open,High,Low,Close,Volume")
    df, errs, _ = messages(raw)
    assert errs == []
    assert list(df.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert df["date"].tolist() == ["2024-01-02", "2024-01-03", "2024-01-04"]


@pytest.mark.parametrize(
    "rows, header, fragment",
    [
        (GOOD, "date,open,high,close", "Missing required column(s): low"),
        (GOOD + ["2024-01-04,11,12,10,11,1"], None, "Duplicate date 2024-01-04"),
        ([GOOD[1], GOOD[0]], None, "sorted ascending"),
        (["2024-01-02,-1,11,9,10,1"], None, "finite, positive"),
        (["2024-01-02,10,11,9,nan,1"], None, "finite, positive"),
        (["2024-01-02,10,11,9,,1"], None, "finite, positive"),
        (["2024-01-02,10,9,8,10,1"], None, "OHLC inconsistent"),
        (["01/02/2024,10,11,9,10,1"], None, "YYYY-MM-DD"),
        (["2024-01-02,10,11,9,10,-5"], None, "non-negative"),
        ([], None, "no data rows"),
    ],
)
def test_rejections(rows, header, fragment):
    raw = csv_bytes(rows, header=header or "date,open,high,low,close,volume")
    df, errs, _ = messages(raw)
    assert df is None
    assert any(fragment in e for e in errs), errs


def test_adj_close_column_is_rejected():
    raw = csv_bytes(
        ["2024-01-02,10,11,9,10,10,1"], header="Date,Open,High,Low,Close,Adj Close,Volume"
    )
    _, errs, _ = messages(raw)
    assert any("Adj Close" in e for e in errs)


def test_errors_include_row_numbers():
    raw = csv_bytes([GOOD[0], "2024-01-03,10,11,9,-2,1"])
    _, _, report = messages(raw)
    assert report.errors[0].row == 2 and report.errors[0].column == "close"


def test_large_move_is_a_warning_not_error():
    raw = csv_bytes([GOOD[0], "2024-01-03,5,5.5,5,5.2,1"])
    df, errs, report = messages(raw)
    assert errs == [] and df is not None
    assert any("unadjusted split" in w.message for w in report.warnings)


def test_float_noise_in_high_is_clamped_with_warning():
    raw = csv_bytes(["2024-01-02,108.44,108.84165954589842,107.62,108.84165954589844,1"])
    df, errs, report = messages(raw)
    assert errs == []
    assert df["high"].iloc[0] == 108.84165954589844
    assert any("Clamped" in w.message for w in report.warnings)


@pytest.mark.parametrize("text", ["90.09069393923035", "90.24234750726089", "90.50430933501639"])
def test_number_parsing_round_trips_like_javascript(text):
    """Regression: pandas.to_numeric parsed these one ULP off, breaking hash parity."""
    from quantlab.datasets import canonical_number
    from quantlab.engine.data import parse_number

    assert canonical_number(parse_number(text)) == text


@pytest.mark.parametrize("text", ["0x10", "1,000", "inf", "NaN", "", "1e3e3"])
def test_number_grammar_rejects_non_decimal_text(text):
    import math

    from quantlab.engine.data import parse_number

    assert math.isnan(parse_number(text))
