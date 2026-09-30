"""Beta invite codes: their format, and the signup that spends one.

The code is the gate on the Beta, so the properties that matter are that a
valid code works however it is typed, that a code can be spent once, and that
a signup which fails does not spend it.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from supabase_auth.errors import AuthApiError

from agenlate import invites
from agenlate.api import signup as signup_api
from agenlate.main import create_app

# The check constraint on public.invite_codes, verbatim.
DB_SHAPE = re.compile(r"^[A-HJKMNP-Z2-9]{4}-[A-HJKMNP-Z2-9]{4}-[A-HJKMNP-Z2-9]{4}$")


class TestFormat:
    def test_generated_codes_fit_the_database_constraint(self) -> None:
        for _ in range(200):
            assert DB_SHAPE.match(invites.generate())

    def test_the_alphabet_leaves_out_characters_people_misread(self) -> None:
        for ch in "01ILO":
            assert ch not in invites.ALPHABET

    def test_codes_do_not_repeat(self) -> None:
        assert len({invites.generate() for _ in range(500)}) == 500

    @pytest.mark.parametrize(
        "typed",
        ["K7QM-4XRT-WN2P", "k7qm-4xrt-wn2p", "K7QM4XRTWN2P", " k7qm 4xrt wn2p ", "K7QM_4XRT_WN2P"],
    )
    def test_a_valid_code_works_however_it_is_typed(self, typed: str) -> None:
        assert invites.normalize(typed) == "K7QM-4XRT-WN2P"

    @pytest.mark.parametrize(
        "typed",
        ["", "K7QM-4XRT", "K7QM-4XRT-WN2P-AAAA", "K0QM-4XRT-WN2P", "K7QM-4XRT-WN2!"],
    )
    def test_anything_else_is_not_a_code(self, typed: str) -> None:
        assert invites.normalize(typed) is None


# -- the signup endpoint, with the database and auth faked -------------------

VALID = "K7QM-4XRT-WN2P"


class FakeInvites:
    """Stands in for the invite table: codes are free until claimed."""

    def __init__(self, free: set[str]) -> None:
        self.free = set(free)
        self.claimed: set[str] = set()
        self.bound: dict[str, str] = {}
        self.released: list[str] = []

    async def claim(self, _client, code: str) -> bool:
        if code in self.free:
            self.free.remove(code)
            self.claimed.add(code)
            return True
        return False

    async def release(self, _client, code: str) -> None:
        if code in self.claimed and code not in self.bound:
            self.claimed.remove(code)
            self.free.add(code)
            self.released.append(code)

    async def bind(self, _client, code: str, user_id: str) -> None:
        self.bound[code] = user_id


class FakeAdmin:
    def __init__(self, error: AuthApiError | None = None) -> None:
        self.error = error
        self.created: list[dict] = []

    async def create_user(self, attributes: dict):
        if self.error:
            raise self.error
        self.created.append(attributes)
        return SimpleNamespace(user=SimpleNamespace(id="new-user-id"))


@pytest.fixture
def backend(monkeypatch):
    table = FakeInvites({VALID})
    admin = FakeAdmin()

    async def fake_service_client(_settings):
        async def aclose() -> None:
            return None

        return SimpleNamespace(
            auth=SimpleNamespace(admin=admin),
            postgrest=SimpleNamespace(aclose=aclose),
        )

    monkeypatch.setattr(signup_api, "create_service_client", fake_service_client)
    for name in ("claim", "release", "bind"):
        monkeypatch.setattr(signup_api.invites_repo, name, getattr(table, name))
    return SimpleNamespace(table=table, admin=admin)


@pytest.fixture
async def api(settings):
    app = create_app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def body(**overrides) -> dict:
    return {"email": "new@example.com", "password": "a-long-password", "invite_code": VALID, **overrides}


class TestSignup:
    async def test_a_valid_code_creates_a_confirmed_account(self, api, backend) -> None:
        response = await api.post("/api/signup", json=body())

        assert response.status_code == 201
        created = backend.admin.created[0]
        assert created["email"] == "new@example.com"
        # Confirmed at creation, so no email is sent: the code is the proof.
        assert created["email_confirm"] is True
        assert created["app_metadata"] == {"invite_code": VALID}

    async def test_the_code_is_spent_and_recorded(self, api, backend) -> None:
        await api.post("/api/signup", json=body())

        assert VALID not in backend.table.free
        assert backend.table.bound[VALID] == "new-user-id"

    async def test_a_code_works_once(self, api, backend) -> None:
        await api.post("/api/signup", json=body())
        second = await api.post("/api/signup", json=body(email="other@example.com"))

        assert second.status_code == 400
        assert len(backend.admin.created) == 1

    async def test_a_code_typed_loosely_still_works(self, api, backend) -> None:
        response = await api.post("/api/signup", json=body(invite_code="k7qm4xrtwn2p"))

        assert response.status_code == 201

    async def test_unknown_and_malformed_codes_get_the_same_answer(self, api, backend) -> None:
        """Different answers for "no such code" and "not a code" would tell a
        guesser which of their attempts had the right shape."""
        unknown = await api.post("/api/signup", json=body(invite_code="AAAA-BBBB-CCCC"))
        malformed = await api.post("/api/signup", json=body(invite_code="nope"))

        assert unknown.status_code == malformed.status_code == 400
        assert unknown.json()["error"]["message"] == malformed.json()["error"]["message"]

    async def test_an_existing_email_gives_the_code_back(self, api, backend) -> None:
        """Spending a code on a signup that failed would shrink the Beta by
        one for nothing."""
        backend.admin.error = AuthApiError("User already registered", 422, "email_exists")

        response = await api.post("/api/signup", json=body())

        assert response.status_code == 409
        assert "Sign in" in response.json()["error"]["message"]
        assert VALID in backend.table.free

    async def test_any_other_auth_failure_gives_the_code_back_too(self, api, backend) -> None:
        backend.admin.error = AuthApiError("boom", 500, None)

        response = await api.post("/api/signup", json=body())

        assert response.status_code == 502
        assert VALID in backend.table.free

    async def test_a_short_password_is_refused_before_spending_anything(
        self, api, backend
    ) -> None:
        response = await api.post("/api/signup", json=body(password="short"))

        assert response.status_code == 422
        assert VALID in backend.table.free

    async def test_the_password_never_appears_in_an_error(self, api, backend) -> None:
        response = await api.post("/api/signup", json=body(password="short"))

        assert "short" not in response.json()["error"]["message"].replace("too short", "")

    async def test_an_obviously_wrong_email_is_refused(self, api, backend) -> None:
        response = await api.post("/api/signup", json=body(email="not-an-email"))

        assert response.status_code == 422
        assert VALID in backend.table.free

    async def test_no_token_is_needed(self, api, backend) -> None:
        """The whole point: someone without an account yet can reach it."""
        response = await api.post("/api/signup", json=body())

        assert response.status_code != 401
