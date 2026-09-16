"""The HTTP API."""

from fastapi import FastAPI

from . import agents, rooms, runs
from .errors import install_error_handlers


def install(app: FastAPI) -> None:
    """Attach every router and the shared error handling."""
    install_error_handlers(app)
    app.include_router(agents.router)
    app.include_router(rooms.router)
    app.include_router(runs.router)


__all__ = ["install"]
