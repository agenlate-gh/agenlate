"""Beta invite codes: making them, and reading what people type.

A code looks like ``K7QM-4XRT-WN2P``: twelve characters in groups of four from
an alphabet with the easily confused ones removed (0 and O, 1, I and L). The
database enforces the same shape, so anything this module lets through is
something the table can hold.

People do not type codes the way they were printed. They drop the dashes, add
spaces, or type in lower case after reading one off a phone. All of that is
accepted and put back into the canonical form, because a person who has a
valid code and is told it is invalid will assume the product is broken.
"""

from __future__ import annotations

import secrets

ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
GROUP = 4
GROUPS = 3
LENGTH = GROUP * GROUPS


def generate() -> str:
    """A new random code. ``secrets``, not ``random``: codes are credentials."""
    raw = "".join(secrets.choice(ALPHABET) for _ in range(LENGTH))
    return _format(raw)


def normalize(typed: str) -> str | None:
    """The canonical form of what someone typed, or None if it cannot be a code.

    None rather than an exception: an unreadable code is an ordinary thing for
    a person to enter, and the caller answers it the same way as a code that
    does not exist — without saying which, so the response does not help
    anyone guess.
    """
    compact = "".join(ch for ch in typed.upper() if ch not in " -_")
    if len(compact) != LENGTH or any(ch not in ALPHABET for ch in compact):
        return None
    return _format(compact)


def _format(compact: str) -> str:
    return "-".join(compact[i : i + GROUP] for i in range(0, LENGTH, GROUP))
