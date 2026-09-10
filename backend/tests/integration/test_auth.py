"""Token verification against tokens Supabase actually issued.

The offline suite signs its own tokens, which proves the logic but not the
assumptions: that the issuer really is the project URL plus /auth/v1, that the
audience really is "authenticated", that the published keys really verify a
live token. Those are only settled here.

Run with: pytest -m integration
"""

from __future__ import annotations

import pytest

from agenlate.auth import ALGORITHM, AuthError, JWKSCache, verify_token

pytestmark = pytest.mark.integration


def jwks_for(settings) -> JWKSCache:
    return JWKSCache(f"{settings.supabase_url}/auth/v1/.well-known/jwks.json")


class TestAgainstRealTokens:
    async def test_a_live_token_verifies(self, settings, alice) -> None:
        user = await verify_token(alice.access_token, settings, jwks_for(settings))

        assert user.id == alice.id
        assert user.email == alice.email

    async def test_the_project_publishes_keys_for_the_expected_algorithm(
        self, settings
    ) -> None:
        """If Supabase moved this project back to a shared secret, the whole
        verification path would be wrong and every request would fail. Better
        to learn that here."""
        cache = jwks_for(settings)
        await cache._refresh()

        assert cache._keys, "the project published no signing keys"
        assert all(key.get("alg") == ALGORITHM for key in cache._keys.values())

    async def test_two_users_are_told_apart(self, settings, alice, bob) -> None:
        cache = jwks_for(settings)

        first = await verify_token(alice.access_token, settings, cache)
        second = await verify_token(bob.access_token, settings, cache)

        assert first.id != second.id

    async def test_a_tampered_live_token_is_refused(self, settings, alice) -> None:
        """Flip one character of the signature: everything else about the
        token is genuine."""
        head, payload, signature = alice.access_token.split(".")
        flipped = "A" if signature[0] != "A" else "B"
        tampered = f"{head}.{payload}.{flipped}{signature[1:]}"

        with pytest.raises(AuthError):
            await verify_token(tampered, settings, jwks_for(settings))

    async def test_an_altered_subject_is_refused(self, settings, alice, bob) -> None:
        """The attack that matters: keep a valid signature, swap the user id."""
        import base64
        import json

        head, payload, signature = alice.access_token.split(".")
        pad = payload + "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(pad))
        claims["sub"] = bob.id
        forged_payload = (
            base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
        )

        with pytest.raises(AuthError):
            await verify_token(f"{head}.{forged_payload}.{signature}", settings, jwks_for(settings))
