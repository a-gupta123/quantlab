"""Serverless mode (Vercel): inline job execution, PostgreSQL object storage,
hosted FinBERT inference, and the chatbot spend cap."""

import json

import httpx
import pytest
from conftest import TEST_TOKEN
from factories import dataset_dates, make_dataset
from fastapi.testclient import TestClient
from sqlalchemy import text

from quantlab.config import Settings, get_settings
from quantlab.sentiment import model
from quantlab.storage import DbStorage, StorageError

AUTH = {"Authorization": f"Bearer {TEST_TOKEN}"}


def test_hosted_postgres_urls_use_psycopg():
    s = Settings(database_url="postgres://u:p@ep-x-pooler.neon.tech/db?sslmode=require")
    assert s.database_url == "postgresql+psycopg://u:p@ep-x-pooler.neon.tech/db?sslmode=require"
    assert Settings(database_url="postgresql://u@h/db").database_url.startswith(
        "postgresql+psycopg://"
    )


# ---------------------------------------------------------------- HF inference


def hf(handler):
    return model.HfApiClassifier(
        "ProsusAI/finbert", "https://hf.test/models", "hf_x", httpx.MockTransport(handler)
    )


def scores(pos, neg, neu):
    return [
        {"label": "positive", "score": pos},
        {"label": "negative", "score": neg},
        {"label": "neutral", "score": neu},
    ]


def test_hf_classifier_parses_scores_and_sends_token():
    seen = {}

    def handler(req):
        seen["url"], seen["auth"] = str(req.url), req.headers["authorization"]
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json=[scores(0.8, 0.1, 0.1), scores(0.1, 0.7, 0.2)])

    out = hf(handler).classify(["up", "down"])
    assert seen["url"] == "https://hf.test/models/ProsusAI/finbert"
    assert seen["auth"] == "Bearer hf_x" and seen["body"]["parameters"]["top_k"] == 3
    assert out[0]["positive"] == 0.8 and max(out[1], key=out[1].get) == "negative"


def test_hf_classifier_single_input_and_errors():
    assert (
        hf(lambda r: httpx.Response(200, json=scores(0.2, 0.2, 0.6))).classify(["x"])[0]["neutral"]
        == 0.6
    )
    with pytest.raises(model.ModelBusy):
        hf(lambda r: httpx.Response(503, json={"error": "loading"})).classify(["x"])
    with pytest.raises(model.ModelUnavailable, match="HTTP 401"):
        hf(lambda r: httpx.Response(401, json={})).classify(["x"])
    with pytest.raises(model.ModelUnavailable, match="labels"):
        hf(lambda r: httpx.Response(200, json=[[{"label": "LABEL_0", "score": 1}]])).classify(["x"])
    with pytest.raises(model.ModelUnavailable, match="HF_TOKEN"):
        model.HfApiClassifier("m", "https://hf.test", "")


# --------------------------------------------------------- db-backed, inline


@pytest.fixture
def serverless(db_env, monkeypatch):
    from quantlab.storage import get_storage
    from quantlab.workflow.runner import setup_checkpointer

    monkeypatch.setenv("STORAGE_BACKEND", "db")
    monkeypatch.setenv("JOB_EXECUTION", "inline")
    get_settings.cache_clear()
    get_storage.cache_clear()
    setup_checkpointer()
    from quantlab.db import transaction

    with transaction() as s:
        s.execute(text("TRUNCATE checkpoints, checkpoint_blobs, checkpoint_writes"))
    from quantlab.api.main import create_app

    with TestClient(create_app()) as c:
        yield c
    get_storage.cache_clear()


@pytest.mark.db
def test_db_storage_roundtrip(serverless):
    st = DbStorage()
    assert not st.exists("a/b.json")
    st.put_bytes("a/b.json", b"one", "application/json")
    st.put_bytes("a/b.json", b"two", "application/json")
    assert st.exists("a/b.json") and st.get_bytes("a/b.json") == b"two"
    with pytest.raises(StorageError, match="not found"):
        st.get_bytes("missing")
    with pytest.raises(StorageError, match="Invalid"):
        st.put_bytes("../etc", b"", "x")


@pytest.mark.db
def test_inline_mode_runs_everything_without_a_worker(serverless):
    c = serverless
    ds = make_dataset(n=900)
    d = dataset_dates(ds)

    exp = c.post(
        "/api/experiments",
        headers=AUTH,
        json=dict(
            name="inline",
            dataset_id=ds,
            start_date=str(d[250]),
            end_date=str(d[-1]),
            initial_capital=10000,
            short_window=20,
            long_window=100,
            fee_bps=5,
            slippage_bps=5,
        ),
    )
    assert exp.status_code == 201, exp.text
    assert exp.json()["status"] == "completed"  # finished before the response
    art = c.get(f"/api/experiments/{exp.json()['id']}/artifact", headers=AUTH)
    assert art.status_code == 200  # stored in PostgreSQL

    wf = c.post(
        "/api/workflows",
        headers=AUTH,
        json=dict(
            name="wf",
            dataset_id=ds,
            dev_start=str(d[200]),
            dev_end=str(d[600]),
            holdout_start=str(d[601]),
            holdout_end=str(d[-1]),
            variant_keys=["fast_10_50", "medium_20_100"],
        ),
    )
    assert wf.status_code == 201 and wf.json()["status"] == "completed", wf.text
    assert wf.json()["holdout"] is not None

    class Fake:
        model_name, revision = "fake/finbert", "test"

        def classify(self, texts):
            return [{"positive": 0.1, "negative": 0.8, "neutral": 0.1} for _ in texts]

    model.reset_for_tests(Fake())
    try:
        b = c.post("/api/sentiment/batches", headers=AUTH, json={"headlines": ["Shares fall"]})
        assert b.json()["status"] == "completed"
        assert b.json()["headlines"][0]["result"]["label"] == "negative"
    finally:
        model.reset_for_tests(None)

    stats = c.get("/api/experiments/stats", headers=AUTH).json()
    assert stats["execution_mode"] == "inline" and stats["workers_online"] == 0
    assert c.get("/api/system", headers=AUTH).json()["execution_mode"] == "inline"


@pytest.mark.db
def test_inline_retry_is_picked_up_by_polling(serverless, monkeypatch):
    """A transient failure is requeued with backoff; the next poll after the
    backoff runs it again, with no worker process."""
    from quantlab.db import transaction

    calls = {"n": 0}

    class Flaky:
        model_name, revision = "fake/finbert", "test"

        def classify(self, texts):
            calls["n"] += 1
            if calls["n"] == 1:
                raise model.ModelBusy("loading")
            return [{"positive": 0.9, "negative": 0.05, "neutral": 0.05} for _ in texts]

    model.reset_for_tests(Flaky())
    try:
        b = serverless.post("/api/sentiment/batches", headers=AUTH, json={"headlines": ["x"]})
        assert b.json()["status"] == "queued" and calls["n"] == 1
        with transaction() as s:
            s.execute(text("UPDATE jobs SET run_after = now()"))  # skip the backoff wait
        done = serverless.get(f"/api/sentiment/batches/{b.json()['id']}", headers=AUTH).json()
        assert done["status"] == "completed" and calls["n"] == 2
    finally:
        model.reset_for_tests(None)


@pytest.mark.db
def test_chatbot_daily_limit(serverless, monkeypatch):
    from test_strategy_builder import answer

    from quantlab import strategy_builder

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("STRATEGY_CHAT_DAILY_LIMIT", "1")
    get_settings.cache_clear()
    monkeypatch.setattr(strategy_builder, "_post", lambda messages, transport: answer())
    first = serverless.post("/api/strategies", headers=AUTH, json={"message": "RSI 30/70"})
    assert first.status_code == 200
    second = serverless.post("/api/strategies", headers=AUTH, json={"message": "again"})
    assert second.status_code == 429 and "limit of 1" in second.text
