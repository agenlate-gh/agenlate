"""Room endpoints, including the roster and the transcript."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from supabase import AsyncClient

from ..auth import CurrentUser, current_user
from ..db import NotFoundError
from ..models import RoomCreate, RoomUpdate
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
