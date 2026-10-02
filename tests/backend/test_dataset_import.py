"""The documented import path: scripts/validate-dataset.mjs -> manifest -> backend."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import func, select

from quantlab.datasets import DatasetImportError, DuplicateDatasetError, import_manifest
from quantlab.db import transaction
from quantlab.models import Dataset, PriceBar
from quantlab.storage import get_storage

pytestmark = pytest.mark.db
ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "scripts" / "validate-dataset.mjs"
DEMO = ROOT / "data" / "demo" / "DEMO-SYNTH.csv"
needs_node = pytest.mark.skipif(
    shutil.which("node") is None or not (ROOT / "scripts" / "node_modules").exists(),
    reason="node + scripts/node_modules required (npm ci in scripts/)",
)


def run_validator(src: Path, out: Path, *extra: str) -> Path:
    args = ["node", str(CLI), str(src), "--out", str(out), *extra]
    subprocess.run(args, check=True, capture_output=True)
    return next(out.glob("*.manifest.json"))


@needs_node
def test_js_manifest_imports_with_identical_hash(db_env, tmp_path):
    get_storage.cache_clear()
    manifest = run_validator(
        DEMO,
        tmp_path,
        "--name",
        "DEMO-SYNTH",
        "--symbol",
        "DEMO",
        "--adjustment",
        "synthetic",
        "--synthetic",
        "--source",
        "synthetic test",
    )
    with transaction() as s:
        ds = import_manifest(s, get_storage(), manifest)
        ds_id, sha = ds.id, ds.content_sha256
    assert sha == json.loads(manifest.read_text())["sha256"]
    assert get_storage().exists(f"datasets/{sha}.csv")
    with transaction() as s:
        assert s.scalar(select(func.count()).where(PriceBar.dataset_id == ds_id)) == 2300
        assert s.get(Dataset, ds_id).is_synthetic
    with pytest.raises(DuplicateDatasetError), transaction() as s:
        import_manifest(s, get_storage(), manifest)


@needs_node
def test_real_style_float_prices_hash_identically(db_env, tmp_path):
    """Long float text like yfinance output must canonicalise the same in JS and Python."""
    src = tmp_path / "spy_like.csv"
    src.write_text(
        "Date,Open,High,Low,Close,Volume\n"
        "2005-01-03,82.02481815114238,82.159774875719,80.90470565155616,81.17461395263672,55748000\n"
        "2005-01-04,81.28254041422286,81.33652308162563,79.91951152476138,80.18267059326172,69167600\n"
    )
    out = tmp_path / "out"
    manifest = run_validator(
        src,
        out,
        "--name",
        "SPY-SAMPLE",
        "--symbol",
        "SPY",
        "--adjustment",
        "adjusted",
        "--source",
        "test",
    )
    get_storage.cache_clear()
    with transaction() as s:
        assert import_manifest(s, get_storage(), manifest).content_sha256


def test_tampered_file_is_rejected(db_env, tmp_path):
    csv = tmp_path / "x.csv"
    csv.write_text("date,open,high,low,close,volume\n2024-01-02,1,1,1,1,\n")
    manifest = tmp_path / "x.manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "file": "x.csv",
                "sha256": "0" * 64,
                "name": "X-DEMO",
                "symbol": "X",
                "source": "t",
                "adjustment": "synthetic",
                "is_synthetic": True,
            }
        )
    )
    with pytest.raises(DatasetImportError, match="does not match"), transaction() as s:
        import_manifest(s, get_storage(), manifest)
