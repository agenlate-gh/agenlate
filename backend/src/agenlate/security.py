"""Keeping the user's API key out of places it must never reach.

Under BYOK the key belongs to the user. It arrives per run, is held in memory
for the length of that run, and is never written to the database, to disk, or
to a log. The design guarantees most of that — there is no column for it and no
cache — but logs are different: a key reaches a log by accident rather than by
design, through an exception whose string form happens to contain a request, a
header dict, or an echoed body.

So there is a filter, and it sits on the root logger rather than on ours. The
leak we are guarding against is most likely to come from a library's logger,
not from a line anyone here wrote.
"""

from __future__ import annotations

import logging
import re

# OpenRouter keys look like sk-or-v1- followed by a long hex string. The
# broader sk- pattern is included because a user pasting the wrong key — an
# OpenAI one, say — should not have that leak either just because it was the
# wrong kind of secret.
KEY_PATTERNS = (
    re.compile(r"sk-or-v1-[A-Za-z0-9._-]{16,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
)

REDACTED = "[redacted]"

# Long enough that a truncated or obviously wrong value is rejected before a
# request is made, short enough not to guess at a format OpenRouter may change.
MIN_KEY_LENGTH = 24
KEY_PREFIX = "sk-or-v1-"


def redact(text: str) -> str:
    """Replace anything key-shaped in a string."""
    for pattern in KEY_PATTERNS:
        text = pattern.sub(REDACTED, text)
    return text


class SecretRedactingFilter(logging.Filter):
    """Strips key-shaped strings from every log record.

    Defence in depth, deliberately blunt: it rewrites the formatted message and
    the arguments rather than trying to understand them. A filter that guessed
    which fields were sensitive would miss the one that mattered.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)

        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    key: redact(value) if isinstance(value, str) else value
                    for key, value in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    redact(value) if isinstance(value, str) else value
                    for value in record.args
                )

        # Exception text is the likeliest carrier of all: a traceback that
        # stringifies a request takes its headers along with it.
        #
        # It is also the one a naive filter misses. At this point exc_text is
        # still empty — the formatter renders the traceback after filters run,
        # so there is nothing here to redact yet. Rendering it now and caching
        # the redacted result means the formatter uses ours instead of building
        # its own from the untouched exception.
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = redact(record.exc_text)

        return True


def install_redaction() -> None:
    """Attach the filter to the root logger and to every existing handler.

    Filters on a logger do not apply to records that reach it from a child
    logger, so the handlers are covered too. Without that, a library logging
    through its own logger would bypass the filter entirely.
    """
    root = logging.getLogger()
    if not any(isinstance(f, SecretRedactingFilter) for f in root.filters):
        root.addFilter(SecretRedactingFilter())

    for handler in root.handlers:
        if not any(isinstance(f, SecretRedactingFilter) for f in handler.filters):
            handler.addFilter(SecretRedactingFilter())


def looks_like_openrouter_key(value: str) -> bool:
    """Whether a value is plausibly an OpenRouter key.

    Shape only. A well-formed key can still be revoked or out of credit, which
    is why there is an endpoint that asks OpenRouter rather than guessing.
    """
    value = value.strip()
    return value.startswith(KEY_PREFIX) and len(value) >= MIN_KEY_LENGTH
