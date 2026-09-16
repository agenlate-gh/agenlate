"""Checking a user's OpenRouter key before a run depends on it.

Without this, an invalid key surfaces as a failed run: the user has already
built agents, opened a room and pressed go, and the first thing they learn is
that none of it could work. Checking at the point the key is entered turns a
confusing failure into a form error.

The check costs nothing. OpenRouter's key endpoint reports whether a key is
valid and what limits it carries without running any inference, so validating
is free where a test completion would not be.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field, SecretStr, field_validator

from ..auth import CurrentUser, current_user
from ..security import looks_like_openrouter_key

router = APIRouter(prefix="/api/keys", tags=["keys"])

KEY_ENDPOINT = "https://openrouter.ai/api/v1/auth/key"


class KeyCheckRequest(BaseModel):
    api_key: SecretStr

    @field_validator("api_key")
    @classmethod
    def _shape(cls, value: SecretStr) -> SecretStr:
        if not looks_like_openrouter_key(value.get_secret_value()):
            # The message describes the expected shape and never quotes what
            # was sent: a validation error that echoes its input would put the
            # key into the response body.
            raise ValueError("does not look like an OpenRouter key (expected sk-or-v1-...)")
        return value


class KeyCheckResponse(BaseModel):
    valid: bool
    message: str
    is_free_tier: bool | None = None
    limit_remaining: float | None = Field(
        default=None, description="Credit left on this key, when the key carries a limit."
    )


@router.post("/validate", response_model=KeyCheckResponse)
async def validate_key(
    body: KeyCheckRequest, user: CurrentUser = Depends(current_user)
) -> KeyCheckResponse:
    """Ask OpenRouter whether this key works. Runs no inference."""
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                KEY_ENDPOINT,
                headers={"Authorization": f"Bearer {body.api_key.get_secret_value()}"},
            )
    except httpx.HTTPError:
        # `from None`: a chained httpx error carries its own request
        # representation, and the request carries the key.
        return KeyCheckResponse(
            valid=False, message="Could not reach OpenRouter. Try again in a moment."
        )

    if response.status_code == status.HTTP_401_UNAUTHORIZED:
        return KeyCheckResponse(
            valid=False, message="OpenRouter rejected this key. Check it and try again."
        )
    if response.status_code != status.HTTP_200_OK:
        return KeyCheckResponse(
            valid=False, message="OpenRouter could not confirm this key right now."
        )

    data = (response.json() or {}).get("data") or {}
    remaining = data.get("limit_remaining")

    return KeyCheckResponse(
        valid=True,
        message="This key works.",
        is_free_tier=data.get("is_free_tier"),
        limit_remaining=float(remaining) if isinstance(remaining, (int, float)) else None,
    )
