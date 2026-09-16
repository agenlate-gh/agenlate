"""Per-user limits on starting runs.

The risk here is not cost. A run needs both a valid login and the caller's own
OpenRouter key, so someone abusing it spends their own credit rather than ours.
The risk is availability: the Beta runs on a single small instance, a run holds
a connection open for its whole duration, and nothing otherwise stops one
account starting fifty at once and leaving everyone else waiting.

So there are two limits, and the concurrency one matters more. A user with
three rooms open is using three of the instance's slots right now; a user who
started forty runs over an hour and finished them has cost nobody anything.

State is in memory. The Beta runs one instance, so this is accurate; if a
second is ever added it becomes per-instance and needs moving to the database.
That is a deliberate trade rather than an oversight — a database round trip on
every run start, to guard a resource that only exists per instance, would be
the wrong shape.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import HTTPException, status

CONCURRENT_RUNS_PER_USER = 3
RUNS_PER_HOUR_PER_USER = 40
WINDOW_SECONDS = 3600


class RunLimiter:
    """Tracks what each user currently has running, and how often they start."""

    def __init__(
        self,
        max_concurrent: int = CONCURRENT_RUNS_PER_USER,
        max_per_window: int = RUNS_PER_HOUR_PER_USER,
        window_seconds: int = WINDOW_SECONDS,
    ) -> None:
        self.max_concurrent = max_concurrent
        self.max_per_window = max_per_window
        self.window_seconds = window_seconds
        self._active: dict[str, int] = defaultdict(int)
        self._starts: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, user_id: str, now: float) -> None:
        starts = self._starts[user_id]
        # >= rather than >: an entry exactly at the boundary has left the
        # window, and the strict form leaves the edge case undefined.
        while starts and now - starts[0] >= self.window_seconds:
            starts.popleft()

    def check(self, user_id: str) -> None:
        """Raise if this user may not start another run right now."""
        now = time.monotonic()
        self._prune(user_id, now)

        if self._active[user_id] >= self.max_concurrent:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"You already have {self.max_concurrent} rooms running. "
                    "Wait for one to finish, or stop it, before starting another."
                ),
            )

        if len(self._starts[user_id]) >= self.max_per_window:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="You have started a lot of runs recently. Try again in a little while.",
            )

    @asynccontextmanager
    async def hold(self, user_id: str) -> AsyncIterator[None]:
        """Occupy a slot for the length of a run.

        Released in a finally block, because the common ending for a run is a
        client disconnecting rather than the work completing — and a slot that
        leaked on disconnect would lock a user out of their own account after
        three abandoned tabs.
        """
        self.check(user_id)
        self._active[user_id] += 1
        self._starts[user_id].append(time.monotonic())
        try:
            yield
        finally:
            self._active[user_id] = max(0, self._active[user_id] - 1)

    def active_for(self, user_id: str) -> int:
        return self._active[user_id]


_limiter = RunLimiter()


def run_limiter() -> RunLimiter:
    return _limiter


def reset_run_limiter() -> None:
    """For tests. Process-wide state otherwise leaks between them."""
    global _limiter
    _limiter = RunLimiter()
