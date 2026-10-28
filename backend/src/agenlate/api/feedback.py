"""Feedback from inside the product.

The Beta exists to learn what people want Agenlate to do, so two questions
are asked of everyone who opens the feedback form — what they would automate,
and which tools they would connect — with space for anything else. Each answer
is stored as its own row under its question, so the answers to one question
can be read and counted together.

Written as the user, so row-level security decides whose answer it is: the
database refuses a row that claims to come from someone else, whatever this
code sends.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from postgrest.types import ReturnMethod
from pydantic import BaseModel, Field
from supabase import AsyncClient

from ..auth import CurrentUser, current_user
from ..repository._common import execute
from .deps import user_db
from .limits import WindowLimiter

router = APIRouter(prefix="/api", tags=["feedback"])

ANSWER_MAX = 2000
SUBMISSIONS_PER_HOUR = 10

# Per account, not per address: everyone here is signed in, and the limit is
# only there to stop a stuck button or a script, not a person.
_limiter = WindowLimiter(SUBMISSIONS_PER_HOUR, 3600)


class FeedbackRequest(BaseModel):
    automate: str | None = Field(
        default=None, max_length=ANSWER_MAX, description="What would you like to automate?"
    )
    connect: str | None = Field(
        default=None,
        max_length=ANSWER_MAX,
        description="Which tools would you like your agents to connect to?",
    )
    general: str | None = Field(
        default=None, max_length=ANSWER_MAX, description="Anything else: ideas, problems, praise."
    )
    page: str | None = Field(default=None, max_length=200)


class FeedbackResponse(BaseModel):
    saved: int = Field(description="How many answers were stored.")


@router.post("/feedback", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
async def send_feedback(
    body: FeedbackRequest,
    user: CurrentUser = Depends(current_user),
    db: AsyncClient = Depends(user_db),
) -> FeedbackResponse:
    """Store the answers the user gave. Empty ones are skipped."""
    rows = [
        {"user_id": user.id, "question": question, "answer": text.strip(), "page": body.page}
        for question, text in (
            ("automate", body.automate),
            ("connect", body.connect),
            ("general", body.general),
        )
        if text and text.strip()
    ]
    if not rows:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Write an answer to at least one question.")

    if not _limiter.allow(user.id):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Thanks — you have sent a lot already. Try again in a little while.",
        )

    # Minimal return: users may add answers but not read them back, so asking
    # for the inserted rows would be refused.
    await execute(
        db.table("feedback").insert(rows, returning=ReturnMethod.minimal),
        context="insert_feedback",
    )
    return FeedbackResponse(saved=len(rows))
