from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import select, text

from quantlab.api.deps import SessionDep, require_service_token
from quantlab.models import Job, Worker

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    """Liveness: the process is up. Does not touch the database."""
    return {"status": "ok"}


@router.get("/ready")
def ready(session: SessionDep):
    """Readiness: database reachable and migrated (used by load balancers/compose)."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    from quantlab.cli import ALEMBIC_INI

    head = ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).get_current_head()
    try:
        with session.begin():
            current = session.scalar(text("SELECT version_num FROM alembic_version"))
            checkpoints = session.scalar(text("SELECT to_regclass('public.checkpoints')"))
    except Exception as exc:
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "detail": f"database: {type(exc).__name__}"},
        )
    problems = []
    if current != head:
        problems.append(f"schema at {current}, expected {head}; run migrations")
    if checkpoints is None:
        problems.append("LangGraph checkpoint tables missing; run migrations")
    if problems:
        return JSONResponse(
            status_code=503, content={"status": "unavailable", "detail": "; ".join(problems)}
        )
    return {"status": "ready", "schema": current}


@router.get("/api/system", dependencies=[Depends(require_service_token)])
def system(session: SessionDep):
    with session.begin():
        workers = session.execute(
            select(
                Worker.id,
                Worker.last_seen_at,
                Worker.current_job_id,
                Worker.sentiment_model_status,
                (Worker.last_seen_at > text("now() - interval '60 seconds'")).label("online"),
            )
            .order_by(Worker.last_seen_at.desc())
            .limit(10)
        ).all()
        queue = dict(
            session.execute(select(Job.status, text("count(*)")).group_by(Job.status)).all()
        )
    return {
        "workers": [dict(w._mapping) for w in workers],
        "queue": {s: queue.get(s, 0) for s in ("queued", "running", "completed", "failed")},
    }
