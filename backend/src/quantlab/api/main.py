"""FastAPI application: `uvicorn quantlab.api.main:app`."""

import logging

from fastapi import Depends, FastAPI

from quantlab import ENGINE_VERSION
from quantlab.api.deps import require_service_token
from quantlab.api.routes import datasets, experiments, health, sentiment, strategies, workflows

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def create_app() -> FastAPI:
    app = FastAPI(
        title="QuantLab API",
        version=ENGINE_VERSION,
        description="Internal API. Called only by the Next.js server with a service token.",
    )
    app.include_router(health.router)
    protected = [Depends(require_service_token)]
    for r in (
        datasets.router,
        experiments.router,
        workflows.router,
        sentiment.router,
        strategies.router,
    ):
        app.include_router(r, dependencies=protected)
    return app


app = create_app()
