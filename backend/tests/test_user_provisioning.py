"""The application row every new account needs before its first write.

Supabase Auth creates the login and nothing else. Agents, rooms and usage all
point at ``public.users``, so the row is created on a user's first request —
and only then, since doing it on every request would add a query to each one.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agenlate.api import deps
from agenlate.auth import CurrentUser


class _FakeClient:
    def __init__(self) -> None:
        self.postgrest = SimpleNamespace(aclose=self._aclose)
        self.closed = False

    async def _aclose(self) -> None:
        self.closed = True


@pytest.fixture
def provisioned(monkeypatch, settings):
    """Record every provisioning call, with no database behind it."""
    calls: list[str] = []

    async def fake_client(_settings, _token):
        return _FakeClient()

    async def fake_ensure(_client, user_id, _email):
        calls.append(user_id)

    monkeypatch.setattr(deps, "create_user_client", fake_client)
    monkeypatch.setattr(deps.users_repo, "ensure_user", fake_ensure)
    monkeypatch.setattr(deps, "_provisioned", set())
    return calls


def _request(settings):
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(settings=settings)),
        state=SimpleNamespace(access_token="token"),
    )


async def _use(settings, user: CurrentUser) -> None:
    generator = deps.user_db(_request(settings), user)
    await generator.__anext__()
    await generator.aclose()


async def test_a_new_user_is_provisioned_on_first_request(provisioned, settings) -> None:
    await _use(settings, CurrentUser(id="u1", email="u1@example.com"))

    assert provisioned == ["u1"]


async def test_later_requests_do_not_repeat_it(provisioned, settings) -> None:
    user = CurrentUser(id="u1", email="u1@example.com")
    for _ in range(3):
        await _use(settings, user)

    assert provisioned == ["u1"]


async def test_each_user_is_provisioned_once(provisioned, settings) -> None:
    for user_id in ("u1", "u2", "u1", "u2"):
        await _use(settings, CurrentUser(id=user_id, email=f"{user_id}@example.com"))

    assert provisioned == ["u1", "u2"]


async def test_a_failed_attempt_is_retried_next_time(monkeypatch, settings) -> None:
    """Remembering a user whose row was never written would make every later
    request fail the same foreign key check, with no way to recover short of a
    restart."""
    attempts: list[str] = []

    async def fake_client(_settings, _token):
        return _FakeClient()

    async def flaky_ensure(_client, user_id, _email):
        attempts.append(user_id)
        if len(attempts) == 1:
            raise RuntimeError("database unavailable")

    monkeypatch.setattr(deps, "create_user_client", fake_client)
    monkeypatch.setattr(deps.users_repo, "ensure_user", flaky_ensure)
    monkeypatch.setattr(deps, "_provisioned", set())
    user = CurrentUser(id="u1", email="u1@example.com")

    with pytest.raises(RuntimeError):
        await _use(settings, user)
    await _use(settings, user)

    assert attempts == ["u1", "u1"]
