"""Data access.

Focused async functions per table. No ORM, no lazy loading, no implicit
queries — every database round trip is visible at its call site.
"""

from . import agents, messages, rooms, usage, users

__all__ = ["agents", "messages", "rooms", "usage", "users"]
