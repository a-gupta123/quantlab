"""Run queued jobs inside API requests (JOB_EXECUTION=inline).

Serverless hosts have no always-on process to poll the queue, so the API drains
it itself: right after a request enqueues work, and whenever a client polls an
unfinished run (which also picks up retries and jobs whose lease expired). The
same queue, leases, fencing, and retries apply as with the worker process;
`FOR UPDATE SKIP LOCKED` keeps concurrent requests from running the same job.
"""

from __future__ import annotations

import logging
import time
import uuid

from sqlalchemy import text

from quantlab.config import get_settings
from quantlab.db import get_engine

log = logging.getLogger("quantlab.inline")

MAX_JOBS_PER_REQUEST = 4
TIME_BUDGET_SECONDS = 200  # stay well inside the host's function timeout

_RUNNABLE = text(
    """
    SELECT EXISTS (
        SELECT 1 FROM jobs
        WHERE (status = 'queued' AND run_after <= now() AND attempts < max_attempts)
           OR (status = 'running' AND lease_expires_at < now())
    )
    """
)


def enabled() -> bool:
    return get_settings().job_execution == "inline"


def drain() -> int:
    """Process runnable jobs until none remain or the budget is spent. Returns count."""
    if not enabled():
        return 0
    with get_engine().connect() as conn:
        if not conn.execute(_RUNNABLE).scalar():
            return 0
    from quantlab.worker import Worker

    worker = Worker(f"inline-{uuid.uuid4().hex[:8]}", register=False)
    start, done = time.monotonic(), 0
    while done < MAX_JOBS_PER_REQUEST and time.monotonic() - start < TIME_BUDGET_SECONDS:
        if worker.run_once() is None:
            break
        done += 1
    log.info("inline worker %s processed %s job(s)", worker.id, done)
    return done
