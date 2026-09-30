"""Room endpoints, including the roster and the transcript."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field, field_validator
from supabase import AsyncClient

from ..auth import CurrentUser, current_user
from ..db import NotFoundError
from ..models import USER_EMITTER_NAME, Emitter, MessageCreate, RoomCreate, RoomUpdate
from ..repository import messages as messages_repo
from ..repository import rooms as repo
from .deps import user_db
from .schemas import MessageOut, MessagePage, RoomDetailOut, RoomIn, RoomOut, RoomPatch

router = APIRouter(prefix="/api/rooms", tags=["rooms"])

MESSAGE_PAGE_MAX = 200


@router.get("", response_model=list[RoomDetailOut])
async def list_rooms(
    user: CurrentUser = Depends(current_user), db: AsyncClient = Depends(user_db)
) -> list[RoomDetailOut]:
    """Every room this user owns, newest first, each with its roster.

    The roster comes along because the lobby draws the agents on every card.
    Returning bare rooms would make the first screen a user sees issue one
    request per room to fill itself in.
    """
    return [
        RoomDetailOut.of_detail(detail)
        for detail in await repo.list_rooms_with_agents_for_user(db, user.id)
    ]


@router.post("", response_model=RoomDetailOut, status_code=status.HTTP_201_CREATED)
async def create_room(
    body: RoomIn,
    user: CurrentUser = Depends(current_user),
    db: AsyncClient = Depends(user_db),
) -> RoomDetailOut:
    room = await repo.create_room(
        db, user.id, RoomCreate(name=body.name, objective=body.objective)
    )
    for agent_id in body.agent_ids:
        # Attaching an agent the caller does not own is refused by the
        # database policy, not by a check here.
        await repo.add_agent_to_room(db, room.id, agent_id)

    detail = await repo.get_room_with_agents(db, room.id)
    if detail is None:
        raise NotFoundError(room.id)
    return RoomDetailOut.of_detail(detail)


@router.get("/{room_id}", response_model=RoomDetailOut)
async def get_room(
    room_id: str,
    user: CurrentUser = Depends(current_user),
    db: AsyncClient = Depends(user_db),
) -> RoomDetailOut:
    detail = await repo.get_room_with_agents(db, room_id)
    if detail is None:
        raise NotFoundError(room_id)
    return RoomDetailOut.of_detail(detail)


@router.patch("/{room_id}", response_model=RoomOut)
async def update_room(
    room_id: str,
    body: RoomPatch,
    user: CurrentUser = Depends(current_user),
    db: AsyncClient = Depends(user_db),
) -> RoomOut:
    room = await repo.update_room(
        db,
        room_id,
        RoomUpdate(name=body.name, objective=body.objective, status=body.status),
    )
    if room is None:
        raise NotFoundError(room_id)
    return RoomOut.of(room)


@router.delete("/{room_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_room(
    room_id: str,
    user: CurrentUser = Depends(current_user),
    db: AsyncClient = Depends(user_db),
) -> None:
    if not await repo.delete_room(db, room_id):
        raise NotFoundError(room_id)


# -- roster -----------------------------------------------------------------


@router.put("/{room_id}/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def add_agent(
    room_id: str,
    agent_id: str,
    user: CurrentUser = Depends(current_user),
    db: AsyncClient = Depends(user_db),
) -> None:
    """Seat an agent at this roundtable.

    PUT rather than POST: seating an agent twice is the same as seating it
    once, and a client retrying a dropped request should not be punished.
    """
    if await repo.get_room(db, room_id) is None:
        raise NotFoundError(room_id)
    await repo.add_agent_to_room(db, room_id, agent_id)


@router.delete("/{room_id}/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_agent(
    room_id: str,
    agent_id: str,
    user: CurrentUser = Depends(current_user),
    db: AsyncClient = Depends(user_db),
) -> None:
    if not await repo.remove_agent_from_room(db, room_id, agent_id):
        raise NotFoundError(agent_id)


# -- transcript -------------------------------------------------------------


USER_MESSAGE_MAX = 4000


class UserMessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=USER_MESSAGE_MAX)

    @field_validator("content")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value.strip()


@router.post(
    "/{room_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_message(
    room_id: str,
    body: UserMessageIn,
    user: CurrentUser = Depends(current_user),
    db: AsyncClient = Depends(user_db),
) -> MessageOut:
    """Add the user's own words to the transcript.

    How a user answers the Supervisor when it stops to ask something, or
    redirects the team between runs. It does not start a run: the client does
    that next, so a message can also be left for later without spending
    anything.

    The emitter is fixed here rather than taken from the request. A client
    that could choose it could write lines attributed to the Supervisor or an
    agent into the record of what happened.
    """
    if await repo.get_room(db, room_id) is None:
        raise NotFoundError(room_id)

    message = await messages_repo.append_message(
        db,
        MessageCreate(
            room_id=room_id,
            emitter=Emitter.USER,
            emitter_name=USER_EMITTER_NAME,
            content=body.content,
        ),
    )
    return MessageOut.of(message)


@router.get("/{room_id}/messages", response_model=MessagePage)
async def list_messages(
    room_id: str,
    after_seq: int | None = Query(default=None, ge=0),
    limit: int = Query(default=50, ge=1, le=MESSAGE_PAGE_MAX),
    user: CurrentUser = Depends(current_user),
    db: AsyncClient = Depends(user_db),
) -> MessagePage:
    """A page of the transcript, in order.

    An empty page for a room that does not exist would be indistinguishable
    from an empty room, so the room is checked first.
    """
    if await repo.get_room(db, room_id) is None:
        raise NotFoundError(room_id)

    # Fetch one extra to learn whether another page exists, without a count.
    found = await messages_repo.list_messages(
        db, room_id, after_seq=after_seq, limit=limit + 1
    )
    has_more = len(found) > limit
    page = found[:limit]

    return MessagePage(
        items=[MessageOut.of(m) for m in page],
        next_after_seq=page[-1].seq if (has_more and page) else None,
    )
