"""FastAPI application entry point.

Exposes a factory rather than a module-level ``app``. Building the application
at import time would make importing this module require a fully populated
environment, which breaks tooling and tests for no benefit.

Run with::

    uvicorn agenlate.main:create_app --factory --reload
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import __version__
from .api import install as install_api
from .config import Settings, get_settings


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application.

    Takes settings as an argument so tests can supply their own without
    reaching into the environment or clearing the settings cache.
    """
    settings = settings or get_settings()

    app = FastAPI(
        title="Agenlate",
        version=__version__,
        description="Supervisor agent and roundtable orchestration.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    async def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            version=__version__,
            environment=settings.api_env,
        )

    install_api(app)

    app.state.settings = settings
    return app
