"""OHLC data validation shared by the importer and the engine.

These rules intentionally mirror `scripts/validate-dataset.mjs`. The JavaScript
tool gives fast feedback before import; the backend re-checks everything because
it must never trust a file just because a manifest says it was validated.
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = ("date", "open", "high", "low", "close")
OPTIONAL_COLUMNS = ("volume",)
MAX_ROWS = 20_000
MAX_ISSUES = 50
# A one-day move this large in an adjusted series usually means an unadjusted split.
SUSPICIOUS_MOVE = 0.40


@dataclass
class ValidationIssue:
    row: int | None  # 1-based data row (header excluded), None for file-level issues
    column: str | None
    message: str

    def as_dict(self) -> dict:
        return {"row": self.row, "column": self.column, "message": self.message}


@dataclass
class ValidationReport:
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def error(self, row: int | None, column: str | None, message: str) -> None:
        if len(self.errors) < MAX_ISSUES:
            self.errors.append(ValidationIssue(row, column, message))

    def warn(self, row: int | None, column: str | None, message: str) -> None:
        if len(self.warnings) < MAX_ISSUES:
            self.warnings.append(ValidationIssue(row, column, message))


@dataclass(frozen=True)
class Bars:
    """Validated, date-sorted daily bars as plain NumPy arrays."""

    dates: np.ndarray  # datetime64[D]
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray

    def __len__(self) -> int:
        return len(self.dates)

    def date_at(self, i: int) -> date:
        return pd.Timestamp(self.dates[i]).date()


def _normalise_header(name: str) -> str:
    return name.strip().lower().replace(" ", "_")


def parse_csv(raw: bytes) -> tuple[pd.DataFrame | None, ValidationReport]:
    """Parse and validate an OHLC CSV. Returns a normalised frame or errors."""
    report = ValidationReport()
    try:
        df = pd.read_csv(io.BytesIO(raw), dtype=str, keep_default_na=False)
    except (pd.errors.ParserError, UnicodeDecodeError, ValueError) as exc:
        report.error(None, None, f"File is not a readable CSV: {exc}")
        return None, report

    df.columns = [_normalise_header(c) for c in df.columns]
    if "adj_close" in df.columns:
        report.error(
            None,
            "adj_close",
            "Found an 'Adj Close' column. Provide one consistently adjusted OHLC set "
            "(all of open/high/low/close adjusted the same way) and drop 'Adj Close'.",
        )
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        report.error(None, None, f"Missing required column(s): {', '.join(missing)}")
    if df.columns.duplicated().any():
        report.error(None, None, "Duplicate column names after normalising headers.")
    if not report.ok:
        return None, report
    if len(df) == 0:
        report.error(None, None, "The file has a header but no data rows.")
        return None, report
    if len(df) > MAX_ROWS:
        report.error(None, None, f"Too many rows ({len(df)}); the limit is {MAX_ROWS}.")
        return None, report

    keep = [c for c in (*REQUIRED_COLUMNS, *OPTIONAL_COLUMNS) if c in df.columns]
    df = df[keep].copy()
    return validate_frame(df, report)


def validate_frame(
    df: pd.DataFrame, report: ValidationReport | None = None
) -> tuple[pd.DataFrame | None, ValidationReport]:
    report = report or ValidationReport()
    parsed_dates = pd.to_datetime(
        df["date"].astype(str).str.strip(), format="%Y-%m-%d", errors="coerce"
    )
    for i in np.flatnonzero(parsed_dates.isna().to_numpy()):
        report.error(int(i) + 1, "date", f"'{df['date'].iloc[i]}' is not a YYYY-MM-DD date.")

    numeric: dict[str, pd.Series] = {}
    for col in ("open", "high", "low", "close", *(c for c in OPTIONAL_COLUMNS if c in df)):
        values = pd.to_numeric(df[col].astype(str).str.strip().replace("", "nan"), errors="coerce")
        numeric[col] = values
        arr = values.to_numpy(dtype=float)
        bad = ~np.isfinite(arr)
        if col == "volume":
            bad |= arr < 0
            label = "a finite, non-negative number"
        else:
            bad |= arr <= 0
            label = "a finite, positive number"
        for i in np.flatnonzero(bad):
            report.error(int(i) + 1, col, f"'{df[col].iloc[i]}' must be {label}.")

    if not report.ok:
        return None, report

    o, h, low, c = (numeric[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
    inconsistent = (h < low) | (h < o) | (h < c) | (low > o) | (low > c)
    for i in np.flatnonzero(inconsistent):
        report.error(
            int(i) + 1,
            None,
            f"OHLC inconsistent: open={o[i]}, high={h[i]}, low={low[i]}, close={c[i]} "
            "(need low <= open, close <= high).",
        )

    d = parsed_dates.to_numpy(dtype="datetime64[D]")
    dup = pd.Series(d).duplicated(keep="first").to_numpy()
    for i in np.flatnonzero(dup):
        report.error(int(i) + 1, "date", f"Duplicate date {pd.Timestamp(d[i]).date()}.")
    order = np.diff(d.astype("int64"))
    for i in np.flatnonzero(order < 0):
        report.error(
            int(i) + 2,
            "date",
            f"Dates must be sorted ascending: {pd.Timestamp(d[i + 1]).date()} "
            f"comes after {pd.Timestamp(d[i]).date()}.",
        )
    if not report.ok:
        return None, report

    weekend = pd.DatetimeIndex(d).dayofweek >= 5
    if weekend.any():
        report.warn(None, "date", f"{int(weekend.sum())} row(s) fall on a weekend.")
    gaps = np.diff(d.astype("int64"))
    if len(gaps) and gaps.max() > 7:
        i = int(gaps.argmax())
        report.warn(
            i + 2,
            "date",
            f"Gap of {int(gaps[i])} calendar days between {pd.Timestamp(d[i]).date()} and "
            f"{pd.Timestamp(d[i + 1]).date()}; missing dates are not filled.",
        )
    moves = np.abs(c[1:] / c[:-1] - 1.0)
    for i in np.flatnonzero(moves > SUSPICIOUS_MOVE)[:5]:
        report.warn(
            int(i) + 2,
            "close",
            f"Close moved {moves[i]:.0%} in one day; check for an unadjusted split.",
        )

    out = pd.DataFrame(
        {
            "date": pd.DatetimeIndex(d).strftime("%Y-%m-%d"),
            "open": o,
            "high": h,
            "low": low,
            "close": c,
            "volume": numeric["volume"].to_numpy(dtype=float) if "volume" in numeric else np.nan,
        }
    )
    return out, report


def bars_from_rows(rows: list[tuple]) -> Bars:
    """Build Bars from DB rows of (trade_date, open, high, low, close)."""
    if not rows:
        raise ValueError("Dataset has no price bars.")
    dates = np.array([r[0] for r in rows], dtype="datetime64[D]")
    cols = np.array([[r[1], r[2], r[3], r[4]] for r in rows], dtype=float)
    if np.any(np.diff(dates.astype("int64")) <= 0):
        raise ValueError("Price bars are not strictly increasing by date.")
    if not np.all(np.isfinite(cols)) or np.any(cols <= 0):
        raise ValueError("Price bars contain non-finite or non-positive prices.")
    return Bars(dates, cols[:, 0], cols[:, 1], cols[:, 2], cols[:, 3])


def to_iso(d: np.datetime64) -> str:
    return str(np.datetime_as_string(d, unit="D"))


def finite_or_none(x: float | None) -> float | None:
    if x is None or not math.isfinite(x):
        return None
    return float(x)
