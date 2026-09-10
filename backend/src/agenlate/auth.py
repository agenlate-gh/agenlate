"""Authenticating requests against Supabase Auth.

This project signs access tokens with ES256 and publishes the public half at a
JWKS endpoint, rather than using the legacy shared HS256 secret. That is the
better arrangement and worth being deliberate about: with asymmetric signing
the backend can *verify* a token but has no key capable of *minting* one, so a
compromised backend cannot forge a session for an arbitrary user.

Three checks matter more than the signature itself, because each one is a way a
technically valid token can still be the wrong token:

* the algorithm is fixed here rather than read from the token, so a caller
  cannot nominate ``none`` or downgrade to a symmetric algorithm and have their
  own signature accepted;
* the issuer is checked, so a token minted by some other Supabase project —
  which anyone can create in a minute — is not accepted here;
* the audience is checked, so a token issued for a different purpose does not
  pass as a user session.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt
from jose.exceptions import JWTError

from .config import Settings, get_settings

ALGORITHM = "ES256"
AUDIENCE = "authenticated"

# How long a fetched key set is trusted before being refreshed.
JWKS_TTL_SECONDS = 3600

# Minimum gap between refreshes triggered by an unrecognised key id. Without
# it, tokens carrying random key ids would be a free way to make this server
# hammer the auth endpoint.
JWKS_REFRESH_COOLDOWN_SECONDS = 60


@dataclass(frozen=True)
class CurrentUser:
    """The authenticated caller."""

    id: str
    email: str
    is_anonymous: bool = False

    @property
    def claims_ok(self) -> bool:
        return bool(self.id)


class AuthError(HTTPException):
    """A 401 that never explains more than it should.

    The detail is deliberately coarse. "Expired" and "wrong signature" are
    useful to an attacker probing what a system will accept and useless to a
    legitimate client, which simply needs to refresh and retry.
    """

    def __init__(self, detail: str = "Not authenticated") -> None:
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


class JWKSCache:
    """Fetches and caches the project's public signing keys."""

    def __init__(
        self,
        jwks_url: str,
        *,
        http_client: httpx.AsyncClient | None = None,
        ttl: int = JWKS_TTL_SECONDS,
    ) -> None:
        self._url = jwks_url
        self._http = http_client
        self._ttl = ttl
        self._keys: dict[str, dict[str, Any]] = {}
        self._fetched_at = 0.0
        self._last_refresh_attempt = 0.0

    async def key_for(self, kid: str) -> dict[str, Any] | None:
        if self._expired() or kid not in self._keys:
            await self._refresh()
        return self._keys.get(kid)

    def _expired(self) -> bool:
        return not self._keys or (time.time() - self._fetched_at) > self._ttl

    async def _refresh(self) -> None:
        now = time.time()
        # Keys rotate rarely; unknown key ids arrive constantly if someone is
        # probing. Refuse to refetch more often than the cooldown allows.
        if self._keys and (now - self._last_refresh_attempt) < JWKS_REFRESH_COOLDOWN_SECONDS:
            return
        self._last_refresh_attempt = now

        client = self._http or httpx.AsyncClient(timeout=10)
        try:
            response = await client.get(self._url)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            # Keep serving the keys we already have. A momentary outage at the
            # auth endpoint should not sign every user out.
            return
        finally:
            if self._http is None:
                await client.aclose()

        keys = payload.get("keys") if isinstance(payload, dict) else None
        if not isinstance(keys, list):
            return

        self._keys = {k["kid"]: k for k in keys if isinstance(k, dict) and k.get("kid")}
        self._fetched_at = now


_cache: JWKSCache | None = None


def jwks_cache(settings: Settings | None = None) -> JWKSCache:
    global _cache
    if _cache is None:
        settings = settings or get_settings()
        _cache = JWKSCache(f"{settings.supabase_url}/auth/v1/.well-known/jwks.json")
    return _cache


def reset_jwks_cache() -> None:
    """Drop the cached keys. For tests and key rotation."""
    global _cache
    _cache = None


async def verify_token(token: str, settings: Settings, cache: JWKSCache) -> CurrentUser:
    """Verify an access token and return who it belongs to."""
    try:
        header = jwt.get_unverified_header(token)
    except JWTError:
        raise AuthError() from None

    # The algorithm is decided here, never taken from the token. Honouring the
    # header would let a caller pick one whose signature they can produce.
    if header.get("alg") != ALGORITHM:
        raise AuthError()

    kid = header.get("kid")
    if not kid:
        raise AuthError()

    key = await cache.key_for(kid)
    if key is None:
        raise AuthError()

    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=[ALGORITHM],
            audience=AUDIENCE,
            issuer=f"{settings.supabase_url}/auth/v1",
            options={"require_exp": True, "verify_aud": True, "verify_iss": True},
        )
    except JWTError:
        raise AuthError() from None

    subject = claims.get("sub")
    if not subject:
        raise AuthError()

    return CurrentUser(
        id=subject,
        email=claims.get("email") or "",
        is_anonymous=bool(claims.get("is_anonymous")),
    )


_bearer = HTTPBearer(auto_error=False)


async def current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> CurrentUser:
    """FastAPI dependency resolving the authenticated caller.

    The raw token is stashed on the request so handlers can build a Supabase
    client that acts *as this user*, which is what makes row-level security
    apply to their queries rather than being bypassed.
    """
    if credentials is None or not credentials.credentials:
        raise AuthError()

    settings: Settings = getattr(request.app.state, "settings", None) or get_settings()
    user = await verify_token(credentials.credentials, settings, jwks_cache(settings))

    request.state.access_token = credentials.credentials
    request.state.user = user
    return user


def access_token(request: Request) -> str:
    """The caller's raw token, for building a user-scoped database client."""
    token = getattr(request.state, "access_token", None)
    if not token:
        raise AuthError()
    return token
