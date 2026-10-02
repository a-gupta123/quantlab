import pytest
from conftest import TEST_TOKEN
from factories import dataset_dates, make_dataset
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from quantlab.db import transaction
from quantlab.models import Experiment, Job, WorkflowEvent, WorkflowRun
from quantlab.worker import Worker
from quantlab.workflow.graph import TransientError, build_graph, run_development
from quantlab.workflow.runner import execute_workflow_job, setup_checkpointer, thread_config
from quantlab.workflow.variants import MAX_VARIANTS, resolve_variants, select_best

pytestmark = pytest.mark.db
AUTH = {"Authorization": f"Bearer {TEST_TOKEN}"}
ALL = ["fast_10_50", "medium_20_100", "classic_50_200"]


@pytest.fixture
def wf_env(db_env):
    from quantlab.storage import get_storage

    get_storage.cache_clear()
    setup_checkpointer()
    with transaction() as s:  # setup() created tables after the truncate in db_env
        s.execute(text("TRUNCATE checkpoints, checkpoint_blobs, checkpoint_writes"))
    yield


@pytest.fixture
def client(wf_env):
    from quantlab.api.main import create_app

    with TestClient(create_app()) as c:
        yield c


def workflow_body(ds_id, variants=ALL, dev=(200, 600), hold=(601, -1)):
    d = dataset_dates(ds_id)
    return dict(
        name="wf",
        dataset_id=ds_id,
        dev_start=str(d[dev[0]]),
        dev_end=str(d[dev[1]]),
        holdout_start=str(d[hold[0]]),
        holdout_end=str(d[hold[1]]),
        variant_keys=variants,
    )


def events(run_id):
    with transaction() as s:
        return s.scalars(
            select(WorkflowEvent)
            .where(WorkflowEvent.workflow_run_id == run_id)
            .order_by(WorkflowEvent.id)
        ).all()


def node_handler(**bodies):
    return {"workflow": lambda job: execute_workflow_job(job, lambda: build_graph(bodies))}


def test_variant_bounds():
    assert len(resolve_variants(ALL)) == MAX_VARIANTS
    with pytest.raises(ValueError, match="At most 3"):
        resolve_variants([*ALL, "extra"])
    with pytest.raises(ValueError, match="Unknown"):
        resolve_variants(["grid_search_everything"])
    best = select_best(
        [
            {"sharpe_ratio": None, "total_return": 9, "long_window": 50},
            {"sharpe_ratio": 0.5, "total_return": 0.1, "long_window": 200},
            {"sharpe_ratio": 0.5, "total_return": 0.1, "long_window": 100},
        ]
    )
    assert best["long_window"] == 100
    assert select_best([{"sharpe_ratio": None, "total_return": 1, "long_window": 5}]) is None


def test_full_workflow_dev_then_single_holdout(client):
    ds = make_dataset(n=900)
    r = client.post("/api/workflows", headers=AUTH, json=workflow_body(ds))
    assert r.status_code == 201, r.text
    run_id = r.json()["id"]
    Worker("wf").run_once()

    detail = client.get(f"/api/workflows/{run_id}", headers=AUTH).json()
    assert detail["status"] == "completed", detail
    assert [n["status"] for n in detail["nodes"]] == ["completed"] * 6
    assert len(detail["development"]) == 3
    hold = detail["holdout"]
    assert hold is not None and hold["role"] == "holdout"
    for dev in detail["development"]:
        assert dev["end_date"] < detail["holdout_start"]
        assert dev["start_date"] == detail["dev_start"]
    assert hold["start_date"] == detail["holdout_start"]
    assert detail["deterministic_summary"].startswith("DETERMINISTIC SUMMARY")
    assert detail["llm_explanation"] is None

    dev_rows = [
        {
            "sharpe_ratio": d["sharpe_ratio"],
            "total_return": d["total_return"],
            "long_window": d["long_window"],
            "short_window": d["short_window"],
        }
        for d in detail["development"]
    ]
    best = select_best(dev_rows)
    sel = detail["selected_strategy_config"]
    assert (sel["short_window"], sel["long_window"]) == (best["short_window"], best["long_window"])
    assert (hold["short_window"], hold["long_window"]) == (sel["short_window"], sel["long_window"])
    # Workflow experiments stay off the default dashboard list.
    assert client.get("/api/experiments", headers=AUTH).json()["total"] == 0


def test_selection_ignores_holdout_data(wf_env):
    """Two datasets identical in the development period but different afterwards
    must select the same variant."""
    import numpy as np
    from helpers import random_walk_bars

    from quantlab.datasets import DatasetMeta, import_dataset, normalised_csv
    from quantlab.storage import get_storage

    def import_with_tail(seed_tail):
        import pandas as pd

        bars = random_walk_bars(900, seed=7)
        close = bars.close.copy()
        rng = np.random.default_rng(seed_tail)
        close[601:] = close[600] * np.exp(np.cumsum(rng.normal(0, 0.02, 299)))
        opens = bars.open.copy()
        opens[601:] = close[600:-1]
        df = pd.DataFrame(
            {
                "date": [str(bars.date_at(i)) for i in range(900)],
                "open": opens,
                "high": np.maximum(opens, close) * 1.01,
                "low": np.minimum(opens, close) * 0.99,
                "close": close,
                "volume": 1.0,
            }
        )
        with transaction() as s:
            ds, _ = import_dataset(
                s,
                get_storage(),
                normalised_csv(df),
                DatasetMeta(f"TAIL-DEMO-{seed_tail}", "DEMO", "test", "synthetic", True),
            )
            return ds.id

    from quantlab.workflow.runner import create_workflow

    selections = []
    for seed in (1, 2):
        ds = import_with_tail(seed)
        body = workflow_body(ds)
        body.pop("name")
        with transaction() as s:
            run_id = create_workflow(
                s,
                name=f"tail{seed}",
                **{
                    **body,
                    "initial_capital": 10_000,
                    "fee_bps": 5,
                    "slippage_bps": 5,
                    "allow_fractional": True,
                    "seed": 42,
                },
            )
            run_id = run_id.id
        Worker(f"w{seed}").run_once()
        with transaction() as s:
            run = s.get(WorkflowRun, run_id)
            assert run.status == "completed"
            selections.append(run.selected_strategy_config_id)
            holdout = s.scalars(
                select(Experiment).where(
                    Experiment.workflow_run_id == run_id, Experiment.role == "holdout"
                )
            ).one()
            selections.append(holdout.result.strategy_metrics["total_return"])
    assert selections[0] == selections[2]  # same selected config
    assert selections[1] != selections[3]  # but the held-out outcome differs


def test_permanent_failure_routes_to_fail_and_is_not_resumable(client):
    ds = make_dataset(n=900)
    body = workflow_body(ds, dev=(100, 600))  # 50/200 cannot warm up from bar 100
    run_id = client.post("/api/workflows", headers=AUTH, json=body).json()["id"]
    Worker("wf").run_once()
    detail = client.get(f"/api/workflows/{run_id}", headers=AUTH).json()
    assert detail["status"] == "failed" and "Earliest valid start" in detail["error"]
    assert detail["nodes"][0]["status"] == "failed"
    assert detail["resumable"] is False
    assert detail["job"]["attempts"] == 1  # permanent errors are not retried
    assert client.post(f"/api/workflows/{run_id}/resume", headers=AUTH).status_code == 409


def test_transient_node_error_retries_inside_graph(client):
    ds = make_dataset(n=900)
    run_id = client.post("/api/workflows", headers=AUTH, json=workflow_body(ds)).json()["id"]
    calls = []

    def flaky(state, ctx):
        calls.append(1)
        if len(calls) == 1:
            raise TransientError("simulated connection reset")
        return run_development(state, ctx)

    Worker("wf", handlers=node_handler(run_development=flaky)).run_once()
    assert len(calls) == 2
    statuses = [(e.node, e.status) for e in events(run_id)]
    assert ("run_development", "retrying") in statuses
    with transaction() as s:
        assert s.get(WorkflowRun, run_id).status == "completed"


def test_interrupted_workflow_resumes_from_checkpoint(client):
    ds = make_dataset(n=900)
    run_id = client.post("/api/workflows", headers=AUTH, json=workflow_body(ds)).json()["id"]

    def always_down(state, ctx):
        raise TransientError("storage unavailable")

    Worker("wf1", handlers=node_handler(run_holdout=always_down)).run_once()
    with transaction() as s:
        job = s.scalars(select(Job).where(Job.workflow_run_id == run_id)).one()
        assert job.status == "queued" and job.attempts == 1  # requeued for retry
        s.execute(text("UPDATE jobs SET run_after = now()"))
    from quantlab.workflow.runner import checkpointer

    with checkpointer() as saver:
        snap = build_graph().compile(checkpointer=saver).get_state(thread_config(run_id))
    assert snap.next == ("run_holdout",)

    Worker("wf2").run_once()  # normal handler: resumes, does not redo development
    evs = events(run_id)
    assert any(e.status == "resumed" for e in evs)
    assert sum(1 for e in evs if e.node == "run_development" and e.status == "started") == 1
    with transaction() as s:
        assert s.get(WorkflowRun, run_id).status == "completed"
        n_hold = s.scalar(
            select(text("count(*)"))
            .select_from(Experiment)
            .where(Experiment.workflow_run_id == run_id, Experiment.role == "holdout")
        )
    assert n_hold == 1


def test_user_resume_after_exhausted_attempts(client, monkeypatch):
    from quantlab.config import get_settings

    monkeypatch.setenv("JOB_MAX_ATTEMPTS", "1")
    get_settings.cache_clear()
    ds = make_dataset(n=900)
    run_id = client.post("/api/workflows", headers=AUTH, json=workflow_body(ds)).json()["id"]

    def always_down(state, ctx):
        raise TransientError("storage unavailable")

    Worker("wf1", handlers=node_handler(run_holdout=always_down)).run_once()
    detail = client.get(f"/api/workflows/{run_id}", headers=AUTH).json()
    assert detail["status"] == "failed" and detail["resumable"] is True

    r = client.post(f"/api/workflows/{run_id}/resume", headers=AUTH)
    assert r.status_code == 202 and r.json()["status"] == "queued"
    Worker("wf2").run_once()
    detail = client.get(f"/api/workflows/{run_id}", headers=AUTH).json()
    assert detail["status"] == "completed"
    assert client.post(f"/api/workflows/{run_id}/resume", headers=AUTH).status_code == 409


def test_workflow_request_validation(client):
    ds = make_dataset(n=900)
    too_many = workflow_body(ds, variants=[*ALL, "fast_10_50x"])
    assert client.post("/api/workflows", headers=AUTH, json=too_many).status_code == 422
    unknown = workflow_body(ds, variants=["nope"])
    r = client.post("/api/workflows", headers=AUTH, json=unknown)
    assert r.status_code == 422 and "Unknown variant" in r.text
    overlap = workflow_body(ds, dev=(200, 650), hold=(601, -1))
    assert client.post("/api/workflows", headers=AUTH, json=overlap).status_code == 422


def test_llm_number_guard():
    from quantlab.llm import unsupported_numbers

    facts = {"sharpe": 0.8123, "ret": 0.15}
    assert unsupported_numbers("Sharpe was 0.81 and return 15.00%", facts) == []
    assert unsupported_numbers("Expect 42% next year", facts) == ["42"]
