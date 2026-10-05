from sqlalchemy.engine import make_url

from quantlab.config import Settings


def test_database_url_built_from_parts_escapes_password(monkeypatch):
    monkeypatch.setenv("DB_HOST", "db.internal")
    monkeypatch.setenv("DB_USER", "quantlab")
    monkeypatch.setenv("DB_PASSWORD", "p@ss/w:rd#%")
    s = Settings()
    url = make_url(s.database_url)
    assert url.host == "db.internal"
    assert url.password == "p@ss/w:rd#%"
    assert url.query["sslmode"] == "require"
    assert s.psycopg_url.startswith("postgresql://")


def test_explicit_database_url_used_without_db_host(monkeypatch):
    monkeypatch.delenv("DB_HOST", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h:5432/x")
    assert Settings().database_url == "postgresql+psycopg://u:p@h:5432/x"
