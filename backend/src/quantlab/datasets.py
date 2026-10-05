"""Dataset import: validate, store the normalised file, insert bars atomically."""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from quantlab.engine.data import ValidationReport, bars_from_rows, parse_csv
from quantlab.models import Dataset, PriceBar
from quantlab.storage import Storage

ADJUSTMENTS = ("adjusted", "split_adjusted", "unadjusted", "synthetic")


class DatasetImportError(ValueError):
    def __init__(self, message: str, report: ValidationReport | None = None):
        super().__init__(message)
        self.report = report


class DuplicateDatasetError(ValueError):
    def __init__(self, existing: Dataset):
        super().__init__(f"Identical data already imported as dataset {existing.id}.")
        # Plain values: the ORM object expires when the caller's transaction rolls back.
        self.existing_id = existing.id
        self.existing_label = f"{existing.name} v{existing.version}"


@dataclass
class DatasetMeta:
    name: str
    symbol: str
    source: str
    adjustment: str
    is_synthetic: bool

    def check(self) -> None:
        if self.adjustment not in ADJUSTMENTS:
            raise DatasetImportError(f"adjustment must be one of {', '.join(ADJUSTMENTS)}.")
        if self.is_synthetic != (self.adjustment == "synthetic"):
            raise DatasetImportError(
                "Synthetic datasets must use adjustment='synthetic', and only synthetic "
                "datasets may use it."
            )
        if self.is_synthetic and "DEMO" not in self.name.upper():
            raise DatasetImportError("Synthetic dataset names must contain 'DEMO'.")


CANONICAL_HEADER = "date,open,high,low,close,volume"


def canonical_number(x: float) -> str:
    """Shortest round-trip text, matching JavaScript's String(number) for the
    ranges we accept (integers print without '.0'; no exponents above 1e-4)."""
    if x != x:  # NaN -> empty field (only volume may be missing)
        return ""
    if float(x).is_integer() and abs(x) < 1e16:
        return str(int(x))
    return repr(float(x))


def normalised_csv(df) -> bytes:
    """Canonical bytes shared with scripts/validate-dataset.mjs, so both produce
    the same SHA-256 for the same data."""
    buf = io.StringIO()
    buf.write(CANONICAL_HEADER + "\n")
    for row in df.itertuples(index=False):
        fields = [row.date, *(canonical_number(v) for v in row[1:6])]
        buf.write(",".join(fields) + "\n")
    return buf.getvalue().encode()


def import_dataset(
    session: Session,
    storage: Storage,
    raw: bytes,
    meta: DatasetMeta,
    manifest: dict | None = None,
) -> tuple[Dataset, ValidationReport]:
    """Validate and import. The caller owns the transaction (session.begin())."""
    meta.check()
    df, report = parse_csv(raw)
    if df is None:
        raise DatasetImportError("Dataset failed validation.", report)

    data = normalised_csv(df)
    sha = hashlib.sha256(data).hexdigest()
    existing = session.scalar(select(Dataset).where(Dataset.content_sha256 == sha))
    if existing is not None:
        raise DuplicateDatasetError(existing)

    # Content-addressed key: re-uploading identical bytes is harmless, and a file
    # left behind by a rolled-back transaction is never referenced incorrectly.
    key = f"datasets/{sha}.csv"
    storage.put_bytes(key, data, "text/csv")

    version = (
        session.scalar(select(func.max(Dataset.version)).where(Dataset.name == meta.name)) or 0
    ) + 1
    full_manifest = {
        **(manifest or {}),
        "name": meta.name,
        "symbol": meta.symbol,
        "source": meta.source,
        "adjustment": meta.adjustment,
        "is_synthetic": meta.is_synthetic,
        "sha256": sha,
        "row_count": len(df),
        "start_date": df["date"].iloc[0],
        "end_date": df["date"].iloc[-1],
        "warnings": [w.as_dict() for w in report.warnings],
    }
    ds = Dataset(
        name=meta.name,
        version=version,
        symbol=meta.symbol,
        source=meta.source,
        is_synthetic=meta.is_synthetic,
        adjustment=meta.adjustment,
        content_sha256=sha,
        row_count=len(df),
        start_date=date.fromisoformat(df["date"].iloc[0]),
        end_date=date.fromisoformat(df["date"].iloc[-1]),
        storage_key=key,
        manifest=full_manifest,
    )
    session.add(ds)
    session.flush()
    volume = df["volume"].where(df["volume"].notna(), None)
    session.execute(
        insert(PriceBar),
        [
            {
                "dataset_id": ds.id,
                "trade_date": date.fromisoformat(d),
                "open": o,
                "high": h,
                "low": lo,
                "close": c,
                "volume": v,
            }
            for d, o, h, lo, c, v in zip(
                df["date"], df["open"], df["high"], df["low"], df["close"], volume, strict=True
            )
        ],
    )
    return ds, report


def import_manifest(session: Session, storage: Storage, manifest_path: Path) -> Dataset:
    """Import the normalised file + manifest produced by scripts/validate-dataset.mjs."""
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema_version") != 1:
        raise DatasetImportError("Unsupported manifest schema_version (expected 1).")
    csv_path = (manifest_path.parent / manifest["file"]).resolve()
    raw = csv_path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != manifest["sha256"]:
        raise DatasetImportError(
            f"{csv_path.name} does not match its manifest hash; re-run validate-dataset.mjs."
        )
    meta = DatasetMeta(
        name=manifest["name"],
        symbol=manifest["symbol"],
        source=manifest["source"],
        adjustment=manifest["adjustment"],
        is_synthetic=bool(manifest["is_synthetic"]),
    )
    ds, _ = import_dataset(session, storage, raw, meta, manifest=manifest)
    if ds.content_sha256 != manifest["sha256"]:
        raise DatasetImportError(
            "Backend normalisation produced different bytes than validate-dataset.mjs "
            f"(backend {ds.content_sha256[:12]}, manifest {manifest['sha256'][:12]})."
        )
    return ds


def load_bars(session: Session, dataset_id: int, end: date | None = None):
    q = select(
        PriceBar.trade_date,
        PriceBar.open,
        PriceBar.high,
        PriceBar.low,
        PriceBar.close,
        PriceBar.volume,
    )
    q = q.where(PriceBar.dataset_id == dataset_id)
    if end is not None:
        q = q.where(PriceBar.trade_date <= end)
    rows = session.execute(q.order_by(PriceBar.trade_date)).all()
    return bars_from_rows([tuple(r) for r in rows])


def earliest_valid_start(session: Session, dataset_id: int, long_window: int) -> date | None:
    """The first date with `long_window` bars strictly before it."""
    return session.scalar(
        select(PriceBar.trade_date)
        .where(PriceBar.dataset_id == dataset_id)
        .order_by(PriceBar.trade_date)
        .offset(long_window)
        .limit(1)
    )
