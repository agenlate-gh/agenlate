"""Per-user limits on starting runs.

The concern is availability, not cost: a run needs the caller's own key, so
abuse spends their credit. What it does not spend is the single instance's
capacity, which everyone shares.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from agenlate.api.limits import RunLimiter


class TestConcurrency:
    async def test_runs_within_the_limit_are_allowed(self) -> None:
        limiter = RunLimiter(max_concurrent=2)

        async with limiter.hold("alice"):
            async with limiter.hold("alice"):
                assert limiter.active_for("alice") == 2

    async def test_one_run_too_many_is_refused(self) -> None:
        limiter = RunLimiter(max_concurrent=2)

        async with limiter.hold("alice"):
            async with limiter.hold("alice"):
                with pytest.raises(HTTPException) as exc_info:
                    limiter.check("alice")

        assert exc_info.value.status_code == 429

    async def test_the_refusal_says_what_to_do(self) -> None:
        limiter = RunLimiter(max_concurrent=1)

        async with limiter.hold("alice"):
            with pytest.raises(HTTPException) as exc_info:
                limiter.check("alice")

        assert "finish" in str(exc_info.value.detail).lower()

    async def test_a_slot_is_released_when_a_run_ends(self) -> None:
        limiter = RunLimiter(max_concurrent=1)

        async with limiter.hold("alice"):
            pass

        limiter.check("alice")  # does not raise
        assert limiter.active_for("alice") == 0

    async def test_a_slot_is_released_when_a_run_fails(self) -> None:
        """The usual ending is a client disconnecting, not the work finishing.
        A slot that leaked on disconnect would lock a user out of their own
        account after three abandoned tabs."""
        limiter = RunLimiter(max_concurrent=1)

        with pytest.raises(RuntimeError):
            async with limiter.hold("alice"):
                raise RuntimeError("client went away")

        assert limiter.active_for("alice") == 0
        limiter.check("alice")

    async def test_users_do_not_share_a_budget(self) -> None:
        limiter = RunLimiter(max_concurrent=1)

        async with limiter.hold("alice"):
            limiter.check("bob")  # bob is unaffected


class TestRate:
    async def test_starting_many_runs_over_time_is_eventually_refused(self) -> None:
        limiter = RunLimiter(max_concurrent=10, max_per_window=3)

        for _ in range(3):
            async with limiter.hold("alice"):
                pass

        with pytest.raises(HTTPException) as exc_info:
            limiter.check("alice")

        assert exc_info.value.status_code == 429

    async def test_the_window_expires(self) -> None:
        limiter = RunLimiter(max_concurrent=10, max_per_window=2, window_seconds=0)

        for _ in range(5):
            async with limiter.hold("alice"):
                pass

        limiter.check("alice")  # the window has already rolled past

    async def test_completed_runs_still_count_toward_the_rate(self) -> None:
        """Otherwise a user could start and abandon runs indefinitely."""
        limiter = RunLimiter(max_concurrent=10, max_per_window=2)

        async with limiter.hold("alice"):
            pass
        async with limiter.hold("alice"):
            pass

        with pytest.raises(HTTPException):
            limiter.check("alice")


class TestDefaults:
    def test_concurrency_fits_the_single_instance(self) -> None:
        """One small instance handles a handful of simultaneous runs, so no
        single user should be able to take most of them."""
        limiter = RunLimiter()

        assert limiter.max_concurrent <= 5

    def test_the_hourly_allowance_is_generous(self) -> None:
        """This is a guard against runaway clients, not a usage quota. A real
        user should never meet it."""
        limiter = RunLimiter()

        assert limiter.max_per_window >= 20
