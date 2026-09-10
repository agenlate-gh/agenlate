"""Token verification.

Tokens are signed with a locally generated EC key and served through a fake
JWKS endpoint, so the real cases — expiry, wrong signer, wrong project — can be
constructed exactly rather than approximated.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
import pytest
import respx
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from jose import jwt
from jose.utils import base64url_encode

from agenlate.auth import (
    ALGORITHM,
    AUDIENCE,
    AuthError,
    CurrentUser,
    JWKSCache,
    current_user,
    verify_token,
)
from agenlate.config import Settings

ISSUER_BASE = "https://test.supabase.co"
JWKS_URL = f"{ISSUER_BASE}/auth/v1/.well-known/jwks.json"
KID = "test-key-1"


def make_settings() -> Settings:
    return Settings(
        supabase_url=ISSUER_BASE,
        supabase_anon_key="anon",
        supabase_service_role_key="service",
    )


class Signer:
    """An EC P-256 keypair, and the JWKS document describing its public half."""

    def __init__(self, kid: str = KID) -> None:
        self.kid = kid
        self._private = ec.generate_private_key(ec.SECP256R1())

    def jwk(self) -> dict[str, Any]:
        numbers = self._private.public_key().public_numbers()
        to_b64 = lambda v: base64url_encode(v.to_bytes(32, "big")).decode()
        return {
            "kty": "EC",
            "crv": "P-256",
            "alg": ALGORITHM,
            "kid": self.kid,
            "use": "sig",
            "x": to_b64(numbers.x),
            "y": to_b64(numbers.y),
        }

    def pem(self) -> str:
        from cryptography.hazmat.primitives import serialization

        return self._private.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()

    def token(self, **overrides: Any) -> str:
        now = int(time.time())
        claims: dict[str, Any] = {
            "iss": f"{ISSUER_BASE}/auth/v1",
            "sub": "user-uuid-1",
            "aud": AUDIENCE,
            "email": "alice@agenlate.dev",
            "role": "authenticated",
            "iat": now,
            "exp": now + 3600,
            "is_anonymous": False,
        }
        claims.update(overrides)
        for key, value in list(claims.items()):
            if value is None:
                del claims[key]
        return jwt.encode(
            claims, self.pem(), algorithm=ALGORITHM, headers={"kid": self.kid}
        )


@pytest.fixture
def signer() -> Signer:
    return Signer()


@pytest.fixture
def cache(signer: Signer) -> JWKSCache:
    """A cache pre-warmed from the signer, so no network is involved."""
    instance = JWKSCache(JWKS_URL)
    instance._keys = {signer.kid: signer.jwk()}
    instance._fetched_at = time.time()
    return instance


async def verify(token: str, cache: JWKSCache) -> CurrentUser:
    return await verify_token(token, make_settings(), cache)


class TestValidTokens:
    async def test_a_valid_token_identifies_the_user(self, signer, cache) -> None:
        user = await verify(signer.token(), cache)

        assert user.id == "user-uuid-1"
        assert user.email == "alice@agenlate.dev"
        assert user.is_anonymous is False

    async def test_an_anonymous_session_is_flagged(self, signer, cache) -> None:
        """Surfaced rather than rejected here: whether anonymous users are
        allowed is a product decision, not a signature one."""
        user = await verify(signer.token(is_anonymous=True), cache)

        assert user.is_anonymous is True

    async def test_a_token_without_an_email_still_verifies(self, signer, cache) -> None:
        user = await verify(signer.token(email=None), cache)

        assert user.id == "user-uuid-1"
        assert user.email == ""


class TestRejectedTokens:
    async def test_an_expired_token_is_refused(self, signer, cache) -> None:
        past = int(time.time()) - 10
        with pytest.raises(AuthError):
            await verify(signer.token(exp=past, iat=past - 3600), cache)

    async def test_a_token_with_no_expiry_is_refused(self, signer, cache) -> None:
        """A token that never expires is a permanent credential."""
        with pytest.raises(AuthError):
            await verify(signer.token(exp=None), cache)

    async def test_a_malformed_token_is_refused(self, signer, cache) -> None:
        with pytest.raises(AuthError):
            await verify("not-a-token", cache)

    async def test_an_empty_token_is_refused(self, signer, cache) -> None:
        with pytest.raises(AuthError):
            await verify("", cache)

    async def test_a_token_with_no_subject_is_refused(self, signer, cache) -> None:
        with pytest.raises(AuthError):
            await verify(signer.token(sub=None), cache)

    async def test_a_token_signed_by_someone_else_is_refused(self, cache) -> None:
        """Same key id, different key: the signature must be what decides."""
        impostor = Signer(kid=KID)

        with pytest.raises(AuthError):
            await verify(impostor.token(), cache)

    async def test_an_unknown_key_id_is_refused(self, signer, cache) -> None:
        stranger = Signer(kid="some-other-key")

        with pytest.raises(AuthError):
            await verify(stranger.token(), cache)

    async def test_a_token_with_no_key_id_is_refused(self, signer, cache) -> None:
        now = int(time.time())
        token = jwt.encode(
            {"iss": f"{ISSUER_BASE}/auth/v1", "sub": "u", "aud": AUDIENCE, "exp": now + 60},
            signer.pem(),
            algorithm=ALGORITHM,
        )

        with pytest.raises(AuthError):
            await verify(token, cache)


class TestCrossProjectAndAlgorithm:
    """The two ways a technically valid token can still be the wrong token."""

    async def test_a_token_from_another_supabase_project_is_refused(
        self, signer, cache
    ) -> None:
        """Anyone can create a Supabase project in a minute. Without an issuer
        check, a token from theirs would authenticate against ours."""
        with pytest.raises(AuthError):
            await verify(
                signer.token(iss="https://someone-else.supabase.co/auth/v1"), cache
            )

    async def test_a_token_for_a_different_audience_is_refused(
        self, signer, cache
    ) -> None:
        with pytest.raises(AuthError):
            await verify(signer.token(aud="some-other-service"), cache)

    async def test_an_unsigned_token_is_refused(self, signer, cache) -> None:
        """The classic attack: nominate 'none' and supply no signature."""
        import base64
        import json

        encode = lambda obj: base64.urlsafe_b64encode(
            json.dumps(obj).encode()
        ).rstrip(b"=").decode()
        header = encode({"alg": "none", "typ": "JWT", "kid": KID})
        payload = encode(
            {"iss": f"{ISSUER_BASE}/auth/v1", "sub": "attacker", "aud": AUDIENCE,
             "exp": int(time.time()) + 3600}
        )

        with pytest.raises(AuthError):
            await verify(f"{header}.{payload}.", cache)

    async def test_a_symmetric_downgrade_is_refused(self, signer, cache) -> None:
        """Signing with HS256 using the public key as the shared secret. Only
        works if the algorithm is read from the token rather than fixed."""
        import json

        public_jwk = json.dumps(signer.jwk())
        forged = jwt.encode(
            {"iss": f"{ISSUER_BASE}/auth/v1", "sub": "attacker", "aud": AUDIENCE,
             "exp": int(time.time()) + 3600},
            public_jwk,
            algorithm="HS256",
            headers={"kid": KID},
        )

        with pytest.raises(AuthError):
            await verify(forged, cache)


class TestJWKSCache:
    @respx.mock
    async def test_keys_are_fetched_on_first_use(self, signer) -> None:
        route = respx.get(JWKS_URL).mock(
            return_value=httpx.Response(200, json={"keys": [signer.jwk()]})
        )
        cache = JWKSCache(JWKS_URL)

        assert await cache.key_for(signer.kid) is not None
        assert route.call_count == 1

    @respx.mock
    async def test_keys_are_reused_rather_than_refetched(self, signer) -> None:
        route = respx.get(JWKS_URL).mock(
            return_value=httpx.Response(200, json={"keys": [signer.jwk()]})
        )
        cache = JWKSCache(JWKS_URL)

        for _ in range(5):
            await cache.key_for(signer.kid)

        assert route.call_count == 1

    @respx.mock
    async def test_unknown_key_ids_do_not_hammer_the_endpoint(self, signer) -> None:
        """Otherwise a token with a random key id is a free way to make this
        server flood the auth endpoint on demand."""
        route = respx.get(JWKS_URL).mock(
            return_value=httpx.Response(200, json={"keys": [signer.jwk()]})
        )
        cache = JWKSCache(JWKS_URL)
        await cache.key_for(signer.kid)

        for _ in range(50):
            await cache.key_for("a-key-that-does-not-exist")

        assert route.call_count == 1

    @respx.mock
    async def test_an_outage_does_not_invalidate_known_keys(self, signer) -> None:
        """A momentary failure at the auth endpoint should not sign everyone
        out."""
        cache = JWKSCache(JWKS_URL, ttl=0)
        cache._keys = {signer.kid: signer.jwk()}
        cache._fetched_at = 0
        respx.get(JWKS_URL).mock(return_value=httpx.Response(503))

        assert await cache.key_for(signer.kid) is not None

    @respx.mock
    async def test_a_malformed_key_document_is_ignored(self, signer) -> None:
        respx.get(JWKS_URL).mock(return_value=httpx.Response(200, json={"nope": []}))
        cache = JWKSCache(JWKS_URL)

        assert await cache.key_for(signer.kid) is None


class TestDependency:
    """The dependency as an endpoint actually uses it."""

    @staticmethod
    def build_app(signer: Signer) -> FastAPI:
        from agenlate import auth as auth_module

        app = FastAPI()
        app.state.settings = make_settings()

        cache = JWKSCache(JWKS_URL)
        cache._keys = {signer.kid: signer.jwk()}
        cache._fetched_at = time.time()
        auth_module._cache = cache

        @app.get("/open")
        async def open_route() -> dict:
            return {"ok": True}

        @app.get("/protected")
        async def protected(user: CurrentUser = Depends(current_user)) -> dict:
            return {"id": user.id, "email": user.email}

        return app

    async def client(self, app: FastAPI) -> AsyncClient:
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    async def test_an_open_route_needs_nothing(self, signer) -> None:
        async with await self.client(self.build_app(signer)) as http:
            assert (await http.get("/open")).status_code == 200

    async def test_a_protected_route_refuses_an_anonymous_caller(self, signer) -> None:
        async with await self.client(self.build_app(signer)) as http:
            response = await http.get("/protected")

        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"

    async def test_a_protected_route_accepts_a_valid_token(self, signer) -> None:
        async with await self.client(self.build_app(signer)) as http:
            response = await http.get(
                "/protected", headers={"Authorization": f"Bearer {signer.token()}"}
            )

        assert response.status_code == 200
        assert response.json()["id"] == "user-uuid-1"

    async def test_a_protected_route_refuses_a_bad_token(self, signer) -> None:
        async with await self.client(self.build_app(signer)) as http:
            response = await http.get(
                "/protected", headers={"Authorization": "Bearer garbage"}
            )

        assert response.status_code == 401

    async def test_a_non_bearer_scheme_is_refused(self, signer) -> None:
        async with await self.client(self.build_app(signer)) as http:
            response = await http.get(
                "/protected", headers={"Authorization": "Basic dXNlcjpwYXNz"}
            )

        assert response.status_code == 401

    async def test_the_failure_reveals_nothing_useful(self, signer) -> None:
        """Distinguishing expired from wrong-signature helps someone probing
        the system and helps a legitimate client not at all."""
        past = int(time.time()) - 10
        app = self.build_app(signer)

        async with await self.client(app) as http:
            expired = await http.get(
                "/protected",
                headers={"Authorization": f"Bearer {signer.token(exp=past, iat=past - 60)}"},
            )
            forged = await http.get(
                "/protected", headers={"Authorization": f"Bearer {Signer(kid=KID).token()}"}
            )

        assert expired.json() == forged.json()
