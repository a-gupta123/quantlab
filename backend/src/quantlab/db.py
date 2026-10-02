"""Database engine and session helpers.

API routes are plain `def` functions, so FastAPI runs them in its threadpool and
the blocking psycopg driver never blocks the async event loop. Each request gets
one Session; routes that write open an explicit `with session.begin():` block so
the transaction boundary is visible in the code.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from quantlab.config import get_settings


@lru_cache
def get_engine() -> Engine:
    return create_engine(
        get_settings().database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
    )


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    # autobegin is disabled so every write must use an explicit session.begin().
    return sessionmaker(bind=get_engine(), expire_on_commit=False, autobegin=False)


def reset_engine_cache() -> None:
    """Used by tests that point the app at a fresh database."""
    if get_engine.cache_info().currsize:
        get_engine().dispose()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed."""
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def transaction() -> Iterator[Session]:
    """Worker/CLI helper: a session whose transaction commits on success."""
    session = get_sessionmaker()()
    try:
        with session.begin():
            yield session
    finally:
        session.close()
