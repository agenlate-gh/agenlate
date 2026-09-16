"""The HTTP API."""

from fastapi import FastAPI

from . import agents, keys, rooms, runs
from ..security import install_redaction
from .errors import install_error_handlers


def install(app: FastAPI) -> None:
    """Attach every router and the shared error handling."""
    # Before anything can log: the filter must be in place ahead of the first
    # request, not attached once something has already gone wrong.
    install_redaction()
    install_error_handlers(app)
    app.include_router(agents.router)
    app.include_router(rooms.router)
    app.include_router(runs.router)
    app.include_router(keys.router)


__all__ = ["install"]
