import threading

import pytest
from factories import make_dataset, make_experiment
from sqlalchemy import func, select, text

from quantlab import jobs
from quantlab.db import transaction
from quantlab.models import Experiment, ExperimentResult, Job, Trade
from quantlab.results import save_result
from quantlab.services import compute_experiment
from quantlab.worker import Worker

pytestmark = pytest.mark.db


def claim_one(worker="w1", lease=30):
    with transaction() as s:
        return jobs.claim(s, worker, lease)


def expire(job_id):
    with transaction() as s:
        s.execute(
            text("UPDATE jobs SET lease_expires_at = now() - interval '1 second' WHERE id = :id"),
            {"id": job_id},
        )


def job_row(job_id) -> Job:
    with transaction() as s:
        return s.get(Job, job_id)


def exp_row(exp_id) -> Experiment:
    with transaction() as s:
        return s.get(Experiment, exp_id)


def test_create_enqueues_job_atomically(db_env):
    ds = make_dataset()
    exp_id = make_experiment(ds)
    with transaction() as s:
        job = s.scalars(select(Job).where(Job.experiment_id == exp_id)).one()
    assert job.status == "queued" and job.attempts == 0
    assert exp_row(exp_id).status == "queued"


def test_concurrent_claims_never_duplicate(db_env):
    ds = make_dataset()
    for i in range(12):
        make_experiment(ds, name=f"e{i}")
    claimed: list[int] = []
    lock = threading.Lock()
    barrier = threading.Barrier(6)

    def run(name):
        barrier.wait()
        while (job := claim_one(name)) is not None:
            with lock:
                claimed.append(job.id)

    threads = [threading.Thread(target=run, args=(f"w{i}",)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(claimed) == 12 and len(set(claimed)) == 12


def test_claim_marks_running_with_lease(db_env):
    ds = make_dataset()
    exp_id = make_experiment(ds)
    job = claim_one("worker-a")
    row = job_row(job.id)
    assert row.status == "running" and row.lease_owner == "worker-a" and row.attempts == 1
    assert row.lease_expires_at is not None
    assert exp_row(exp_id).status == "running"
    assert claim_one("worker-b") is None


def test_expired_lease_is_recovered_and_retried(db_env):
    ds = make_dataset()
    exp_id = make_experiment(ds)
    first = claim_one("dead-worker")
    expire(first.id)
    with transaction() as s:
        assert jobs.recover_expired(s) == [first.id]
    row = job_row(first.id)
    assert row.status == "queued" and "dead-worker" in row.last_error
    assert exp_row(exp_id).status == "queued"
    second = claim_one("live-worker")
    assert second.id == first.id and second.attempts == 2


def test_recovery_stops_after_max_attempts(db_env):
    ds = make_dataset()
    exp_id = make_experiment(ds)
    for _ in range(3):  # default JOB_MAX_ATTEMPTS = 3
        job = claim_one()
        expire(job.id)
        with transaction() as s:
            jobs.recover_expired(s)
    row = job_row(job.id)
    assert row.status == "failed" and row.attempts == 3
    exp = exp_row(exp_id)
    assert exp.status == "failed" and "Lease expired" in exp.error
    assert claim_one() is None


def test_heartbeat_extends_lease_and_detects_loss(db_env):
    ds = make_dataset()
    make_experiment(ds)
    job = claim_one("w1")
    before = job_row(job.id).lease_expires_at
    with transaction() as s:
        assert jobs.heartbeat(s, job, 120)
    assert job_row(job.id).lease_expires_at > before
    expire(job.id)
    with transaction() as s:
        jobs.recover_expired(s)
    with transaction() as s:
        assert not jobs.heartbeat(s, job, 120)


def test_stale_worker_cannot_write_result(db_env):
    """A worker whose lease was taken over must not store results (fencing)."""
    ds = make_dataset()
    exp_id = make_experiment(ds)
    stale = claim_one("stale")
    expire(stale.id)
    with transaction() as s:
        jobs.recover_expired(s)
    fresh = claim_one("fresh")
    from quantlab.services import execute_backtest_job

    with pytest.raises(jobs.LeaseLost):
        execute_backtest_job(stale)
    with transaction() as s:
        assert s.get(ExperimentResult, exp_id) is None
    execute_backtest_job(fresh)
    assert exp_row(exp_id).status == "completed"


def test_result_storage_is_idempotent(db_env):
    ds = make_dataset()
    exp_id = make_experiment(ds)
    _, result = compute_experiment(exp_id)
    assert result["trades"], "fixture should produce trades"
    with transaction() as s:
        assert save_result(s, exp_id, result, None) is True
    with transaction() as s:
        assert save_result(s, exp_id, result, None) is False
    with transaction() as s:
        n_results = s.scalar(select(func.count()).select_from(ExperimentResult))
        n_trades = s.scalar(select(func.count()).where(Trade.experiment_id == exp_id))
    assert n_results == 1 and n_trades == len(result["trades"])


def test_worker_processes_backtest_end_to_end(db_env):
    ds = make_dataset()
    exp_id = make_experiment(ds)
    worker = Worker("test-worker")
    assert worker.run_once() is not None
    exp = exp_row(exp_id)
    assert exp.status == "completed" and exp.completed_at is not None
    with transaction() as s:
        res = s.get(ExperimentResult, exp_id)
        assert res.artifact_key.endswith("result.json")
        assert res.n_days == len(res.equity_curve["dates"])
    assert worker.run_once() is None


def test_non_retryable_failure_is_final(db_env, monkeypatch):
    ds = make_dataset()
    exp_id = make_experiment(ds)
    from quantlab.engine.backtest import BacktestInputError

    def boom(job):
        raise BacktestInputError("bad window")

    Worker("w", handlers={"backtest": boom}).run_once()
    row = job_row(1)
    assert row.status == "failed" and row.attempts == 1
    assert "bad window" in exp_row(exp_id).error


def test_transient_failure_retries_then_fails(db_env):
    ds = make_dataset()
    exp_id = make_experiment(ds)
    calls = []

    def flaky(job):
        calls.append(job.attempts)
        raise RuntimeError("database hiccup")

    w = Worker("w", handlers={"backtest": flaky})
    for _ in range(3):
        with transaction() as s:  # skip the retry backoff delay
            s.execute(text("UPDATE jobs SET run_after = now()"))
        w.run_once()
    assert calls == [1, 2, 3]
    assert job_row(1).status == "failed"
    assert exp_row(exp_id).status == "failed"
