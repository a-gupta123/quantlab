# syntax=docker/dockerfile:1.7
# Two targets from one file:
#   api    – FastAPI + migrations (no ML libraries)
#   worker – job runner with Transformers/PyTorch (CPU) for FinBERT

FROM ghcr.io/astral-sh/uv:0.12.9 AS uv

FROM python:3.12.13-slim-trixie AS base
COPY --from=uv /uv /usr/local/bin/uv
ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH
RUN useradd --create-home --uid 10001 app
WORKDIR /app

# ---------------------------------------------------------------- api
FROM base AS api
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project
COPY alembic.ini ./
COPY alembic ./alembic
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev
RUN mkdir -p /data/storage && chown app /data/storage
USER app
ENV LOCAL_STORAGE_DIR=/data/storage
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=4).status == 200 else 1)"]
CMD ["uvicorn", "quantlab.api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]

# ---------------------------------------------------------------- worker
FROM base AS worker
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --extra ml --no-install-project
COPY alembic.ini ./
COPY alembic ./alembic
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --extra ml
# Model files live in HF_HOME. Locally that is a named volume (downloaded on
# first use); set BAKE_MODEL=true to download the pinned revision at build time
# so production containers start without internet access to Hugging Face.
ARG BAKE_MODEL=false
ENV HF_HOME=/models
RUN mkdir -p /models /data/storage && chown app /models /data/storage
USER app
RUN if [ "$BAKE_MODEL" = "true" ]; then python -m quantlab.sentiment.smoke; fi
ENV LOCAL_STORAGE_DIR=/data/storage
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
  CMD ["python", "-m", "quantlab.worker", "--healthcheck"]
STOPSIGNAL SIGTERM
CMD ["python", "-m", "quantlab.worker"]
