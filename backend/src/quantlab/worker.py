"""Background worker: `python -m quantlab.worker`.

One process handles one job at a time. Run more processes (or ECS tasks) to
scale. Every state change is written to PostgreSQL, so killing a worker at any
point loses at most the in-flight computation; the lease then expires and the
job is retried by another worker (bounded by max_attempts).
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import socket
import sys
import threading
import time
import traceback
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import text

from quantlab import jobs
from quantlab.config import get_settings
from quantlab.db import get_engine, transaction
from quantlab.engine.backtest import BacktestInputError

log = logging.getLogger("quantlab.worker")


class NonRetryableError(Exception):
    """Raised by handlers for failures that another attempt cannot fix."""


def _non_retryable_types() -> tuple[type[BaseException], ...]:
    from quantlab.datasets import DatasetImportError
    from quantlab.services import InvalidRequest, NotFound

    return (NonRetryableError, BacktestInputError, InvalidRequest, NotFound, DatasetImportError)


def _handlers() -> dict[str, Callable[[jobs.ClaimedJob], None]]:
    from quantlab.sentiment.service import execute_sentiment_job
    from quantlab.services import execute_backtest_job
    from quantlab.workflow.runner import execute_workflow_job

    return {
        "backtest": execute_backtest_job,
        "workflow": execute_workflow_job,
        "sentiment": execute_sentiment_job,
    }


class Heartbeat:
    """Extends the job lease every lease/3 seconds from a background thread."""

    def __init__(self, job: jobs.ClaimedJob, lease_seconds: int):
        self.job = job
        self.lease = lease_seconds
        self.stop = threading.Event()
        self.lost = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True, name=f"hb-{job.id}")

    def _run(self) -> None:
        interval = max(self.lease / 3, 0.5)
        while not self.stop.wait(interval):
            try:
                with transaction() as s:
                    if not jobs.heartbeat(s, self.job, self.lease):
                        self.lost.set()
                        log.warning("lost lease on job %s", self.job.id)
                        return
            except Exception:  # transient DB issue: keep trying until the lease runs out
                log.exception("heartbeat failed for job %s", self.job.id)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.stop.set()
        self.thread.join(timeout=5)


class Worker:
    def __init__(self, worker_id: str | None = None, handlers=None):
        settings = get_settings()
        self.settings = settings
        self.id = (
            worker_id or settings.worker_id or f"{socket.gethostname()}-{uuid.uuid4().hex[:6]}"
        )
        self.handlers = handlers or _handlers()
        self.started_at = datetime.now(UTC)
        self.stopping = False
        self.current_job: int | None = None

    def model_status(self) -> str:
        from quantlab.sentiment.model import model_status

        return model_status()

    def report_alive(self) -> None:
        with transaction() as s:
            jobs.upsert_worker(
                s,
                self.id,
                socket.gethostname(),
                os.getpid(),
                self.started_at,
                self.current_job,
                self.model_status(),
            )

    def run_once(self) -> int | None:
        """Recover expired leases, claim one job, and process it."""
        with transaction() as s:
            recovered = jobs.recover_expired(s)
        if recovered:
            log.warning("recovered expired jobs %s", recovered)
        with transaction() as s:
            job = jobs.claim(s, self.id, self.settings.job_lease_seconds, tuple(self.handlers))
        if job is None:
            return None
        self.current_job = job.id
        log.info(
            "claimed job %s (%s #%s) attempt %s/%s",
            job.id,
            job.kind,
            job.target_id,
            job.attempts,
            job.max_attempts,
        )
        try:
            self.report_alive()
            with Heartbeat(job, self.settings.job_lease_seconds):
                self.handlers[job.kind](job)
            log.info("completed job %s", job.id)
        except jobs.LeaseLost as exc:
            log.warning("discarding result: %s", exc)
        except Exception as exc:
            retryable = not isinstance(exc, _non_retryable_types())
            message = f"{type(exc).__name__}: {exc}"
            log.error(
                "job %s failed (retryable=%s): %s\n%s",
                job.id,
                retryable,
                message,
                traceback.format_exc(),
            )
            try:
                with transaction() as s:
                    status = jobs.mark_failed(s, job, message, retryable)
                log.info("job %s is now %s", job.id, status)
            except jobs.LeaseLost as lost:
                log.warning("could not record failure: %s", lost)
        finally:
            self.current_job = None
        return job.id

    def run_forever(self) -> None:
        log.info("worker %s starting", self.id)
        last_alive = 0.0
        while not self.stopping:
            try:
                if time.monotonic() - last_alive > 10:
                    self.report_alive()
                    last_alive = time.monotonic()
                processed = self.run_once()
            except Exception:
                log.exception("worker loop error; backing off")
                processed = None
                time.sleep(5)
            if processed is None:
                time.sleep(self.settings.worker_poll_seconds)
        log.info("worker %s stopped", self.id)


def healthcheck(max_age_seconds: int = 60) -> int:
    """Exit 0 if this container's worker reported in recently (Docker/ECS health)."""
    worker_id = get_settings().worker_id
    with get_engine().connect() as conn:
        age = conn.execute(
            text(
                "SELECT extract(epoch FROM now() - max(last_seen_at)) FROM workers "
                + ("WHERE id = :id" if worker_id else "")
            ),
            {"id": worker_id},
        ).scalar()
    return 0 if age is not None and age < max_age_seconds else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="QuantLab background worker")
    parser.add_argument("--healthcheck", action="store_true")
    parser.add_argument("--once", action="store_true", help="process at most one job and exit")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if args.healthcheck:
        sys.exit(healthcheck())
    worker = Worker()

    def _stop(signum, _frame):
        log.info("signal %s received; finishing current job then exiting", signum)
        worker.stopping = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    if args.once:
        worker.run_once()
        return
    worker.run_forever()


if __name__ == "__main__":
    main()
