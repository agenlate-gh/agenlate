"""Structured logging and request correlation.

The failure this exists for: a user says "my room stopped and I don't know
why", and the only way to answer is to find every line the server wrote while
handling their request. Without a shared identifier those lines are
interleaved with everyone else's and effectively unsearchable.

So every record carries a request id, and the same id goes back to the client
in a response header. A user can quote it, and one search finds the whole
story.

Records are JSON because Render's log viewer is a text box. Structure is what
makes "show me every failed run today" a query rather than an afternoon.
"""

from __future__ import annotations

import json
import logging
import sys
import uuid
from contextvars import ContextVar
from typing import Any

from .security import SecretRedactingFilter

REQUEST_ID_HEADER = "X-Request-ID"

# A context variable rather than a parameter, because the alternative is
# threading an id through every function that might one day log.
_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)

# Attributes the logging module puts on every record. Anything outside this set
# was added by a caller and belongs in the structured output.
_STANDARD = frozenset(
    logging.LogRecord("", 0, "", 0, "", None, None).__dict__.keys()
) | {"asctime", "message", "taskName"}


def current_request_id() -> str | None:
    return _request_id.get()


def set_request_id(value: str | None = None) -> str:
    request_id = value or uuid.uuid4().hex[:16]
    _request_id.set(request_id)
    return request_id


class RequestIdFilter(logging.Filter):
    """Stamps the active request id onto every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
        }

        # Anything passed as extra= lands here, so a caller can attach a room
        # id or a termination reason without inventing a message format.
        for key, value in record.__dict__.items():
            if key not in _STANDARD and key not in payload:
                payload[key] = value

        if record.exc_info or record.exc_text:
            # Rendered and redacted by the secret filter before reaching here.
            payload["exception"] = record.exc_text or self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def _ensure_filter(target: Any, filter_type: type[logging.Filter]) -> None:
    """Attach a filter once.

    Configuration runs whenever an application is built, which in tests is many
    times per process. Without this, filters accumulate and every log line is
    processed once per application ever created.
    """
    if not any(isinstance(existing, filter_type) for existing in target.filters):
        target.addFilter(filter_type())


def configure_logging(level: str = "INFO", json_output: bool = True) -> None:
    """Install handlers, formatting and both filters.

    Order matters: redaction must be attached to the handler as well as the
    logger, because records arriving from child loggers bypass a logger's own
    filters entirely.
    """
    root = logging.getLogger()
    root.setLevel(level)

    for existing in list(root.handlers):
        root.removeHandler(existing)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonFormatter()
        if json_output
        else logging.Formatter("%(levelname)s %(name)s [%(request_id)s] %(message)s")
    )
    _ensure_filter(handler, RequestIdFilter)
    _ensure_filter(handler, SecretRedactingFilter)
    root.addHandler(handler)
    _ensure_filter(root, RequestIdFilter)
    _ensure_filter(root, SecretRedactingFilter)

    # These log every request at INFO and would double every line we write.
    for noisy in ("uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
