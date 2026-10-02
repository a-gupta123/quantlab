"""Shared fixtures.

Database tests use a real PostgreSQL server named by TEST_DATABASE_URL (an
SQLAlchemy URL to a database the test role may create databases from, e.g.
postgresql+psycopg://quantlab:quantlab@localhost:5432/postgres). A fresh,
uniquely named database is created per test session, migrated with Alembic,
and dropped at the end; tables are truncated between tests.
"""

import os
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
TEST_TOKEN = "test-internal-token"


def _admin_url() -> str | None:
    return os.environ.get("TEST_DATABASE_URL")


@pytest.fixture(scope="session")
def database_url():
    admin = _admin_url()
    if not admin:
        pytest.skip("TEST_DATABASE_URL not set; skipping PostgreSQL integration tests")
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    name = f"quantlab_test_{uuid.uuid4().hex[:10]}"
    admin_engine = create_engine(admin, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    url = make_url(admin).set(database=name).render_as_string(hide_password=False)

    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.attributes["database_url"] = url
    command.upgrade(cfg, "head")

    yield url

    from quantlab.db import reset_engine_cache

    reset_engine_cache()
    with admin_engine.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    admin_engine.dispose()


@pytest.fixture
def db_env(database_url, monkeypatch, tmp_path):
    """Point settings + engine at the test database and clean all tables."""
    from sqlalchemy import text

    from quantlab.config import get_settings
    from quantlab.db import get_engine, reset_engine_cache

    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("API_INTERNAL_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("LOCAL_STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("JOB_LEASE_SECONDS", "30")
    get_settings.cache_clear()
    reset_engine_cache()
    with get_engine().begin() as conn:
        tables = conn.execute(
            text(
                "SELECT string_agg(quote_ident(tablename), ', ') FROM pg_tables "
                "WHERE schemaname = 'public' "
                "AND tablename NOT IN ('alembic_version', 'checkpoint_migrations')"
            )
        ).scalar_one()
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    yield database_url
    get_settings.cache_clear()
    reset_engine_cache()
