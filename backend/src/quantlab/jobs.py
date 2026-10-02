"""PostgreSQL job queue.

Lifecycle: queued -> running -> completed | failed  (running -> queued on retry).

* enqueue: insert a `queued` row in the same transaction as the domain row, so a
  request either creates both or neither.
* claim: `SELECT ... FOR UPDATE SKIP LOCKED` picks one queued job; concurrent
  workers skip rows another transaction already locked, so two workers never
  claim the same job. The claim sets a lease (owner + expiry).
* heartbeat: the running worker extends the lease periodically.
* recover: running jobs whose lease expired (worker crashed or hung) are put back
  to `queued` until `max_attempts` is reached, then marked `failed`.
* finish: completion/failure only succeeds if this worker still owns the lease
  ("fencing"), so a worker that lost its lease cannot overwrite a newer attempt.

The domain row (experiment, workflow run, sentiment batch) carries the
user-visible status and is updated in the same transaction as the job row.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text, update
from sqlalchemy.orm import Session

from quantlab.models import Experiment, Job, SentimentBatch, WorkflowRun

DOMAIN_TABLES = {
    "backtest": ("experiments", "experiment_id", Experiment),
    "workflow": ("workflow_runs", "workflow_run_id", WorkflowRun),
    "sentiment": ("sentiment_batches", "sentiment_batch_id", SentimentBatch),
}


@dataclass(frozen=True)
class ClaimedJob:
    id: int
    kind: str
    target_id: int
    attempts: int
    max_attempts: int
    lease_owner: str


class LeaseLost(RuntimeError):
    """This worker no longer owns the job; its results must be discarded."""


def enqueue(session: Session, kind: str, target_id: int, max_attempts: int) -> Job:
    _, column, _ = DOMAIN_TABLES[kind]
    job = Job(kind=kind, status="queued", max_attempts=max_attempts, **{column: target_id})
    session.add(job)
    session.flush()
    return job


def _set_domain_status(
    session: Session, kind: str, target_id: int, status: str, error: str | None = None
) -> None:
    table, _, _ = DOMAIN_TABLES[kind]
    extra = ""
    if status == "running" and table == "experiments":
        extra = ", started_at = COALESCE(started_at, now())"
    if status == "completed":
        extra = ", completed_at = now()"
    session.execute(
        text(f"UPDATE {table} SET status = :status, error = :error{extra} WHERE id = :id"),
        {"status": status, "error": error, "id": target_id},
    )


def recover_expired(session: Session) -> list[int]:
    """Requeue or fail jobs whose lease expired. Returns affected job ids."""
    rows = session.execute(
        text(
            """
            WITH expired AS (
                SELECT id FROM jobs
                WHERE status = 'running' AND lease_expires_at < now()
                FOR UPDATE SKIP LOCKED
            )
            UPDATE jobs j SET
                status = CASE WHEN j.attempts >= j.max_attempts THEN 'failed' ELSE 'queued' END,
                last_error = 'Lease expired: worker ' || coalesce(j.lease_owner, '?')
                             || ' stopped heartbeating (attempt ' || j.attempts || ').',
                lease_owner = NULL,
                lease_expires_at = NULL,
                run_after = now(),
                finished_at = CASE WHEN j.attempts >= j.max_attempts THEN now() END
            FROM expired WHERE j.id = expired.id
            RETURNING j.id, j.kind, j.status, j.last_error,
                      coalesce(j.experiment_id, j.workflow_run_id, j.sentiment_batch_id) AS target
            """
        )
    ).all()
    for r in rows:
        _set_domain_status(
            session, r.kind, r.target, r.status, r.last_error if r.status == "failed" else None
        )
    return [r.id for r in rows]


def claim(
    session: Session,
    worker_id: str,
    lease_seconds: int,
    kinds: tuple[str, ...] = ("backtest", "workflow", "sentiment"),
) -> ClaimedJob | None:
    row = session.execute(
        text(
            """
            WITH next AS (
                SELECT id FROM jobs
                WHERE status = 'queued' AND run_after <= now()
                  AND attempts < max_attempts AND kind = ANY(:kinds)
                ORDER BY run_after, id
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            UPDATE jobs j SET
                status = 'running',
                attempts = j.attempts + 1,
                lease_owner = :worker,
                lease_expires_at = now() + make_interval(secs => :lease),
                heartbeat_at = now(),
                started_at = coalesce(j.started_at, now())
            FROM next WHERE j.id = next.id
            RETURNING j.id, j.kind, j.attempts, j.max_attempts,
                      coalesce(j.experiment_id, j.workflow_run_id, j.sentiment_batch_id) AS target
            """
        ),
        {"worker": worker_id, "lease": lease_seconds, "kinds": list(kinds)},
    ).one_or_none()
    if row is None:
        return None
    _set_domain_status(session, row.kind, row.target, "running")
    return ClaimedJob(row.id, row.kind, row.target, row.attempts, row.max_attempts, worker_id)


def heartbeat(session: Session, job: ClaimedJob, lease_seconds: int) -> bool:
    result = session.execute(
        text(
            """
            UPDATE jobs SET heartbeat_at = now(),
                            lease_expires_at = now() + make_interval(secs => :lease)
            WHERE id = :id AND status = 'running' AND lease_owner = :worker
            """
        ),
        {"id": job.id, "worker": job.lease_owner, "lease": lease_seconds},
    )
    return result.rowcount == 1


def lock_owned(session: Session, job: ClaimedJob) -> None:
    """Row-lock the job and verify we still own it, or raise LeaseLost.

    Call this at the start of the transaction that writes results, so the
    ownership check and the writes commit (or roll back) together.
    """
    row = session.execute(
        text("SELECT status, lease_owner FROM jobs WHERE id = :id FOR UPDATE"),
        {"id": job.id},
    ).one_or_none()
    if row is None or row.status != "running" or row.lease_owner != job.lease_owner:
        raise LeaseLost(f"Job {job.id} is no longer leased by {job.lease_owner}.")


def mark_completed(session: Session, job: ClaimedJob) -> None:
    lock_owned(session, job)
    session.execute(
        update(Job)
        .where(Job.id == job.id)
        .values(
            status="completed",
            lease_owner=None,
            lease_expires_at=None,
            finished_at=text("now()"),
            last_error=None,
        )
    )
    _set_domain_status(session, job.kind, job.target_id, "completed")


def mark_failed(
    session: Session, job: ClaimedJob, error: str, retryable: bool, backoff_seconds: int = 5
) -> str:
    """Record a failure. Returns the resulting job status ('queued' or 'failed')."""
    lock_owned(session, job)
    final = (not retryable) or job.attempts >= job.max_attempts
    status = "failed" if final else "queued"
    session.execute(
        text(
            """
            UPDATE jobs SET status = :status, last_error = :error, lease_owner = NULL,
                lease_expires_at = NULL,
                run_after = now() + make_interval(secs => :backoff),
                finished_at = CASE WHEN :final THEN now() END
            WHERE id = :id
            """
        ),
        {
            "status": status,
            "error": error[:4000],
            "backoff": backoff_seconds * job.attempts,
            "final": final,
            "id": job.id,
        },
    )
    _set_domain_status(session, job.kind, job.target_id, status, error[:4000] if final else None)
    return status


def upsert_worker(
    session: Session,
    worker_id: str,
    hostname: str,
    pid: int,
    started_at: datetime,
    current_job_id: int | None,
    model_status: str,
) -> None:
    session.execute(
        text(
            """
            INSERT INTO workers (id, hostname, pid, started_at, last_seen_at, current_job_id,
                                 sentiment_model_status)
            VALUES (:id, :host, :pid, :started, now(), :job, :model)
            ON CONFLICT (id) DO UPDATE SET last_seen_at = now(),
                current_job_id = EXCLUDED.current_job_id,
                sentiment_model_status = EXCLUDED.sentiment_model_status
            """
        ),
        {
            "id": worker_id,
            "host": hostname,
            "pid": pid,
            "started": started_at,
            "job": current_job_id,
            "model": model_status,
        },
    )
