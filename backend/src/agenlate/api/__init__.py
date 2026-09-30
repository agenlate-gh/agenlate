"""The HTTP API."""

from fastapi import FastAPI

from . import agents, builder, keys, objective, rooms, runs, signup, usage, waitlist
from ..observability import configure_logging
from .errors import install_error_handlers
from .middleware import RequestContextMiddleware


def install(app: FastAPI) -> None:
    """Attach every router and the shared error handling."""
    # Before anything can log: formatting, request correlation and redaction
    # all have to be in place ahead of the first request, not attached once
    # something has already gone wrong.
    configure_logging()
    app.add_middleware(RequestContextMiddleware)
    install_error_handlers(app)
    app.include_router(agents.router)
    app.include_router(rooms.router)
    app.include_router(runs.router)
    app.include_router(keys.router)
    app.include_router(usage.router)
    app.include_router(builder.router)
    app.include_router(objective.router)
    app.include_router(signup.router)
    app.include_router(waitlist.router)


__all__ = ["install"]
