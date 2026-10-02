from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration comes from environment variables."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    # SQLAlchemy URL, e.g. postgresql+psycopg://user:pass@host:5432/quantlab
    database_url: str = "postgresql+psycopg://quantlab:quantlab@localhost:5432/quantlab"

    # Shared secret the Next.js server sends as a Bearer token. The browser never sees it.
    api_internal_token: SecretStr = SecretStr("")

    storage_backend: Literal["local", "s3"] = "local"
    local_storage_dir: str = "./var/storage"
    s3_bucket: str = ""
    s3_prefix: str = "quantlab/"
    aws_region: str = "us-east-1"
    # Only used for local testing against S3-compatible endpoints.
    s3_endpoint_url: str | None = None

    # Worker / queue
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

    # Optional LLM explanation for workflow summaries (off by default).
    llm_explanations_enabled: bool = False
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"

    @property
    def psycopg_url(self) -> str:
        """Plain libpq URL for psycopg (LangGraph checkpointer)."""
        return self.database_url.replace("postgresql+psycopg://", "postgresql://", 1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
