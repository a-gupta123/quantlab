import pytest
from conftest import TEST_TOKEN
from factories import bars_csv, dataset_dates, make_dataset, make_experiment
from fastapi.testclient import TestClient

from quantlab.worker import Worker

pytestmark = pytest.mark.db
AUTH = {"Authorization": f"Bearer {TEST_TOKEN}"}


@pytest.fixture
def client(db_env):
    from quantlab.api.main import create_app
    from quantlab.storage import get_storage

    get_storage.cache_clear()
    with TestClient(create_app()) as c:
        yield c


def experiment_body(ds_id, **kw):
    dates = dataset_dates(ds_id)
    body = dict(
        name="API test",
        dataset_id=ds_id,
        start_date=str(dates[150]),
        end_date=str(dates[-1]),
        initial_capital=10000,
        short_window=20,
        long_window=100,
        fee_bps=5,
        slippage_bps=5,
    )
    body.update(kw)
    return body


def test_health_is_public_but_api_requires_token(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/api/experiments").status_code == 401
    bad = client.get("/api/experiments", headers={"Authorization": "Bearer wrong"})
    assert bad.status_code == 401
    assert client.get("/api/experiments", headers=AUTH).status_code == 200


def test_ready_reports_unmigrated_checkpoints_then_ready(client):
    from quantlab.workflow.runner import setup_checkpointer

    setup_checkpointer()
    r = client.get("/ready")
    assert r.status_code == 200 and r.json()["status"] == "ready"


def test_no_cors_headers(client):
    r = client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in r.headers


def test_dataset_upload_validation_and_duplicate(client):
    files = {"file": ("demo.csv", bars_csv(300), "text/csv")}
    form = dict(
        name="UPLOAD-DEMO",
        symbol="DEMO",
        source="unit test",
        adjustment="synthetic",
        is_synthetic="true",
    )
    r = client.post("/api/datasets", headers=AUTH, files=files, data=form)
    assert r.status_code == 201, r.text
    ds = r.json()["dataset"]
    assert ds["row_count"] == 300 and ds["version"] == 1 and len(ds["content_sha256"]) == 64

    dup = client.post("/api/datasets", headers=AUTH, files=files, data=form)
    assert dup.status_code == 409 and dup.json()["existing_dataset_id"] == ds["id"]

    bad_csv = b"date,open,high,low,close\n2024-01-02,10,9,8,10\n2024-01-02,10,11,9,10\n"
    bad = client.post(
        "/api/datasets", headers=AUTH, files={"file": ("x.csv", bad_csv, "text/csv")}, data=form
    )
    assert bad.status_code == 422
    msgs = [e["message"] for e in bad.json()["errors"]]
    assert any("OHLC inconsistent" in m for m in msgs) and any("Duplicate date" in m for m in msgs)

    lie = client.post("/api/datasets", headers=AUTH, files=files, data={**form, "name": "SPY"})
    assert lie.status_code == 422 and "DEMO" in lie.json()["detail"]

    listing = client.get("/api/datasets", headers=AUTH).json()
    assert listing["total"] == 1


def test_create_list_get_delete_experiment(client):
    ds = make_dataset()
    r = client.post("/api/experiments", headers=AUTH, json=experiment_body(ds))
    assert r.status_code == 201, r.text
    exp = r.json()
    assert exp["status"] == "queued" and exp["job"]["status"] == "queued"
    assert exp["engine_version"] and exp["seed"] == 42 and len(exp["dataset_sha256"]) == 64

    Worker("api-test").run_once()
    detail = client.get(f"/api/experiments/{exp['id']}", headers=AUTH).json()
    assert detail["status"] == "completed"
    assert detail["result"]["strategy_metrics"]["n_trades"] == len(detail["trades"])
    ci = detail["result"]["confidence_intervals"]["strategy"]
    assert ci["block_length"] == 20 and ci["seed"] == 42

    page = client.get("/api/experiments?q=api&status=completed&limit=5", headers=AUTH).json()
    assert page["total"] == 1 and page["items"][0]["sharpe_ratio"] is not None
    assert client.get("/api/experiments?q=nomatch", headers=AUTH).json()["total"] == 0
    assert client.get("/api/experiments?limit=500", headers=AUTH).status_code == 422

    stats = client.get("/api/experiments/stats", headers=AUTH).json()
    assert stats["by_status"]["completed"] == 1 and stats["best_sharpe"]["id"] == exp["id"]

    art = client.get(f"/api/experiments/{exp['id']}/artifact", headers=AUTH)
    assert art.status_code == 200 and art.json()["experiment_id"] == exp["id"]

    assert client.delete(f"/api/experiments/{exp['id']}", headers=AUTH).status_code == 204
    assert client.get(f"/api/experiments/{exp['id']}", headers=AUTH).status_code == 404
    assert client.delete(f"/api/experiments/{exp['id']}", headers=AUTH).status_code == 404


@pytest.mark.parametrize(
    "override, status, fragment",
    [
        (dict(short_window=100, long_window=50), 422, "smaller than long_window"),
        (dict(fee_bps=-1), 422, "greater than or equal"),
        (dict(name="   "), 422, "blank"),
        (dict(dataset_id=999), 404, "not found"),
        (dict(unknown_field=1), 422, "Extra inputs"),
    ],
)
def test_create_validation(client, override, status, fragment):
    ds = make_dataset()
    r = client.post("/api/experiments", headers=AUTH, json=experiment_body(ds, **override))
    assert r.status_code == status
    assert fragment in r.text


def test_warmup_and_range_errors_are_helpful(client):
    ds = make_dataset()
    dates = dataset_dates(ds)
    r = client.post(
        "/api/experiments", headers=AUTH, json=experiment_body(ds, start_date=str(dates[10]))
    )
    assert r.status_code == 422 and f"Earliest valid start is {dates[100]}" in r.text
    w = client.get(f"/api/datasets/{ds}/warmup?long_window=100", headers=AUTH).json()
    assert w["earliest_start"] == str(dates[100])
    r = client.post(
        "/api/experiments", headers=AUTH, json=experiment_body(ds, end_date="2099-01-01")
    )
    assert r.status_code == 422 and "within the dataset range" in r.text


def test_compare_requires_same_period(client):
    ds = make_dataset()
    dates = dataset_dates(ds)
    a = make_experiment(ds, "a")
    b = make_experiment(ds, "b", short_window=10, long_window=50)
    c = make_experiment(ds, "c", start_date=dates[200])
    w = Worker("cmp")
    while w.run_once():
        pass
    ok = client.get(f"/api/experiments/compare?ids={a},{b}", headers=AUTH)
    assert ok.status_code == 200 and len(ok.json()["experiments"]) == 2
    mismatch = client.get(f"/api/experiments/compare?ids={a},{c}", headers=AUTH)
    assert mismatch.status_code == 422 and "same evaluation period" in mismatch.text
    assert client.get(f"/api/experiments/compare?ids={a}", headers=AUTH).status_code == 422
    too_many = client.get(f"/api/experiments/compare?ids={a},{b},{c},99", headers=AUTH)
    assert too_many.status_code == 422


def test_rerun_creates_new_recorded_experiment(client):
    ds = make_dataset()
    a = make_experiment(ds, "original")
    r = client.post(f"/api/experiments/{a}/rerun", headers=AUTH)
    assert r.status_code == 201
    body = r.json()
    assert body["id"] != a and body["rerun_of_id"] == a and body["status"] == "queued"


def test_delete_running_experiment_conflicts(client):
    ds = make_dataset()
    a = make_experiment(ds)
    from quantlab import jobs
    from quantlab.db import transaction

    with transaction() as s:
        jobs.claim(s, "w", 30)
    assert client.delete(f"/api/experiments/{a}", headers=AUTH).status_code == 409


def test_sentiment_batch_lifecycle_with_fake_model(client):
    from quantlab.sentiment import model

    class Fake:
        model_name = "fake/finbert"
        revision = "test"

        def classify(self, texts):
            return [{"positive": 0.7, "negative": 0.2, "neutral": 0.1} for _ in texts]

    model.reset_for_tests(Fake())
    try:
        r = client.post(
            "/api/sentiment/batches",
            headers=AUTH,
            json={"headlines": ["  Shares   rise  "], "include_samples": True},
        )
        assert r.status_code == 201
        batch = r.json()
        assert batch["headlines"][0]["text"] == "Shares rise"
        assert {h["source"] for h in batch["headlines"]} == {"user", "sample"}
        Worker("sent").run_once()
        done = client.get(f"/api/sentiment/batches/{batch['id']}", headers=AUTH).json()
        assert done["status"] == "completed"
        res = done["headlines"][0]["result"]
        assert res["label"] == "positive" and res["model_revision"] == "test"
    finally:
        model.reset_for_tests(None)


def test_sentiment_model_unavailable_is_visible(client, monkeypatch):
    from quantlab.sentiment import model

    def unavailable():
        raise model.ModelUnavailable("no weights in cache")

    monkeypatch.setattr(model, "get_classifier", unavailable)
    batch = client.post("/api/sentiment/batches", headers=AUTH, json={"headlines": ["x"]}).json()
    Worker("sent").run_once()
    done = client.get(f"/api/sentiment/batches/{batch['id']}", headers=AUTH).json()
    assert done["status"] == "failed" and "unavailable" in done["error"]
    assert done["headlines"][0]["result"] is None


def test_sentiment_validation(client):
    assert client.post("/api/sentiment/batches", headers=AUTH, json={}).status_code == 422
    long = {"headlines": ["x" * 301]}
    assert client.post("/api/sentiment/batches", headers=AUTH, json=long).status_code == 422
    many = {"headlines": ["h"] * 33}
    assert client.post("/api/sentiment/batches", headers=AUTH, json=many).status_code == 422
