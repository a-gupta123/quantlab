from functools import lru_cache
from typing import Literal
from urllib.parse import quote

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration comes from environment variables."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    # SQLAlchemy URL, e.g. postgresql+psycopg://user:pass@host:5432/quantlab
    database_url: str = "postgresql+psycopg://quantlab:quantlab@localhost:5432/quantlab"
    # Alternative to DATABASE_URL for platforms that inject the password on its
    # own (AWS RDS-managed secrets on ECS). Used only when DB_HOST is set.
    db_host: str = ""
    db_port: int = 5432
    db_name: str = "quantlab"
    db_user: str = "quantlab"
    db_password: SecretStr = SecretStr("")
    db_sslmode: str = "require"

    # Shared secret the Next.js server sends as a Bearer token. The browser never sees it.
    api_internal_token: SecretStr = SecretStr("")

    # "db" keeps objects in PostgreSQL, for hosts without a persistent disk (Vercel).
    storage_backend: Literal["local", "s3", "db"] = "local"
    local_storage_dir: str = "./var/storage"
    s3_bucket: str = ""
    s3_prefix: str = "quantlab/"
    aws_region: str = "us-east-1"
    # Only used for local testing against S3-compatible endpoints.
    s3_endpoint_url: str | None = None

    # Worker / queue. "inline" runs queued jobs inside API requests instead of a
    # separate worker process, for serverless hosts with no always-on process.
    job_execution: Literal["worker", "inline"] = "worker"
    worker_id: str = ""
    worker_poll_seconds: float = 1.0
    job_lease_seconds: int = 60
    job_max_attempts: int = 3

    # Sentiment model
    sentiment_model_name: str = "ProsusAI/finbert"
    sentiment_model_revision: str = "4556d13015211d73dccd3fdd39d39232506f3e43"
    sentiment_batch_size: int = Field(default=16, ge=1, le=64)
    # When true the worker never downloads; the model must already be in HF_HOME.
    sentiment_local_files_only: bool = False
    # "hf_api" calls the same model on Hugging Face's hosted inference instead of
    # loading PyTorch locally (too large for serverless functions).
    sentiment_backend: Literal["local", "hf_api"] = "local"
    hf_token: SecretStr = SecretStr("")
    hf_inference_url: str = "https://router.huggingface.co/hf-inference/models"

    # Cap on strategy-chatbot messages per rolling 24 hours (OpenAI spend guard).
    strategy_chat_daily_limit: int = Field(default=200, ge=0)

    # Optional LLM explanation for workflow summaries (off by default).
    llm_explanations_enabled: bool = False
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"

    @model_validator(mode="after")
    def _url_from_parts(self):
        # Hosted Postgres (Neon, Heroku-style) hands out postgres:// URLs; use psycopg 3.
        for prefix in ("postgres://", "postgresql://"):
            if self.database_url.startswith(prefix):
                self.database_url = "postgresql+psycopg://" + self.database_url[len(prefix) :]
        if self.db_host:
            pw = quote(self.db_password.get_secret_value(), safe="")
            self.database_url = (
                f"postgresql+psycopg://{quote(self.db_user, safe='')}:{pw}@{self.db_host}:"
                f"{self.db_port}/{self.db_name}?sslmode={self.db_sslmode}"
            )
        return self

    @property
    def psycopg_url(self) -> str:
        """Plain libpq URL for psycopg (LangGraph checkpointer)."""
        return self.database_url.replace("postgresql+psycopg://", "postgresql://", 1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
