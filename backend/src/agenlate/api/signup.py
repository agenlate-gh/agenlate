"""Signing up with an invite code.

The only way into the Beta. Public signup is switched off in Supabase, so the
browser cannot create an account on its own: it sends the code here, this
checks and spends it, and creates the account through the admin API.

Doing it here rather than in the browser is what makes the code a real gate.
A check that runs only in the page can be skipped by anyone who calls
Supabase directly with the public key.

Accounts are created already confirmed, so no confirmation email is sent. The
code is the proof that this person was invited, and it sidesteps the built-in
mailer's limit of a couple of emails an hour, which would otherwise stall the
third signup of any given hour.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from supabase_auth.errors import AuthApiError

from .. import invites
from ..db import create_service_client
from ..repository import invites as invites_repo
from .deps import settings_for

router = APIRouter(prefix="/api", tags=["signup"])
log = logging.getLogger("agenlate.signup")

PASSWORD_MIN = 8
PASSWORD_MAX = 72  # bcrypt ignores everything past 72 bytes

INVALID_CODE = "This invite code is not valid, or it has already been used."


class SignupRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=PASSWORD_MIN, max_length=PASSWORD_MAX)
    invite_code: str = Field(min_length=1, max_length=40)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        # Shape only. Supabase validates properly; this just turns an obvious
        # typo into a form error instead of spending a code on it first.
        value = value.strip().lower()
        local, _, domain = value.partition("@")
        if not local or "." not in domain or " " in value:
            raise ValueError("is not a valid email address")
        return value


class SignupResponse(BaseModel):
    email: str
    message: str = "Account created. Sign in with your email and password."


@router.post("/signup", response_model=SignupResponse, status_code=status.HTTP_201_CREATED)
async def signup(body: SignupRequest, request: Request) -> SignupResponse:
    """Create an account, spending one invite code."""
    code = invites.normalize(body.invite_code)
    if code is None:
        # The same answer as a code that does not exist or is spent, so the
        # response does not tell a guesser which of those it was.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, INVALID_CODE)

    # Service role, because the invite table is closed to every browser role
    # and creating an account is an admin operation. Both are the reason this
    # endpoint exists; nothing else here needs the elevated client.
    client = await create_service_client(settings_for(request))
    try:
        if not await invites_repo.claim(client, code):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, INVALID_CODE)

        try:
            created = await client.auth.admin.create_user(
                {
                    "email": body.email,
                    "password": body.password,
                    "email_confirm": True,
                    # app_metadata, not user_metadata: only the service role
                    # can write it, so it is a trustworthy record of how the
                    # account came to exist.
                    "app_metadata": {"invite_code": code},
                }
            )
        except AuthApiError as exc:
            await invites_repo.release(client, code)
            if exc.code == "email_exists" or "already" in (exc.message or "").lower():
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    "An account with this email already exists. Sign in instead.",
                ) from None
            if exc.code == "weak_password":
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    "That password is too weak. Choose a longer one.",
                ) from None
            log.warning("signup failed", extra={"error_code": exc.code})
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                "The account could not be created. Your invite code was not used; try again.",
            ) from None
        except Exception:
            await invites_repo.release(client, code)
            raise

        try:
            await invites_repo.bind(client, code, created.user.id)
        except Exception:
            # The account exists and the code is claimed, so the cap holds;
            # only the record of which account it made is missing. Not worth
            # failing a signup that otherwise succeeded.
            log.exception("could not record which account an invite code created")

        return SignupResponse(email=body.email)
    finally:
        await client.postgrest.aclose()
