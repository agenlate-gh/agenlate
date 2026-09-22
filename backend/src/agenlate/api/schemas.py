"""Request and response shapes for the HTTP API.

Explicit rather than reusing the database models. Two reasons: the frontend
generates its TypeScript from this schema, so it should describe a contract we
intend to keep rather than whatever the tables happen to look like today; and a
column added later is then a deliberate decision to expose, not an accident.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from ..agents.tools import SUPPORTED_TOOLS
from ..models import (
    NAME_MAX,
    OBJECTIVE_MAX,
    ROLE_MAX,
    ROOM_NAME_MAX,
    SYSTEM_PROMPT_MAX,
    Agent,
    Emitter,
    Message,
    Room,
    RoomStatus,
    RoomWithAgents,
)


def _validate_tools(tools: list[str] | None) -> list[str] | None:
    """Reject tools this deployment cannot actually use.

    Accepting an unusable identifier and silently dropping it later would leave
    a user looking at an agent that claims a capability it does not have.
    """
    if tools is None:
        return None
    unknown = [t for t in tools if t not in SUPPORTED_TOOLS]
    if unknown:
        raise ValueError(
            f"unsupported tools: {', '.join(sorted(unknown))}. "
            f"Available: {', '.join(sorted(SUPPORTED_TOOLS))}"
        )
    return tools


# -- agents -----------------------------------------------------------------


class AgentIn(BaseModel):
    name: str = Field(min_length=1, max_length=NAME_MAX)
    role: str = Field(min_length=1, max_length=ROLE_MAX)
    system_prompt: str = Field(min_length=1, max_length=SYSTEM_PROMPT_MAX)
    enabled_tools: list[str] | None = Field(
        default=None,
        description="Null means the defaults. An empty list means no tools.",
    )

    _check_tools = field_validator("enabled_tools")(
        classmethod(lambda cls, v: _validate_tools(v))
    )


class AgentPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=NAME_MAX)
    role: str | None = Field(default=None, min_length=1, max_length=ROLE_MAX)
    system_prompt: str | None = Field(
        default=None, min_length=1, max_length=SYSTEM_PROMPT_MAX
    )
    enabled_tools: list[str] | None = None

    _check_tools = field_validator("enabled_tools")(
        classmethod(lambda cls, v: _validate_tools(v))
    )


class AgentOut(BaseModel):
    id: str
    name: str
    role: str
    system_prompt: str
    enabled_tools: list[str] | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, agent: Agent) -> "AgentOut":
        return cls(
            id=agent.id,
            name=agent.name,
            role=agent.role,
            system_prompt=agent.system_prompt,
            enabled_tools=agent.enabled_tools,
            created_at=agent.created_at,
            updated_at=agent.updated_at,
        )


# -- rooms ------------------------------------------------------------------


class RoomIn(BaseModel):
    name: str = Field(min_length=1, max_length=ROOM_NAME_MAX)
    objective: str = Field(min_length=1, max_length=OBJECTIVE_MAX)
    agent_ids: list[str] = Field(
        default_factory=list, description="Agents to seat at this roundtable."
    )


class RoomPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=ROOM_NAME_MAX)
    objective: str | None = Field(default=None, min_length=1, max_length=OBJECTIVE_MAX)
    status: RoomStatus | None = Field(
        default=None,
        description="Set to paused to stop this room accepting new runs.",
    )


class RoomOut(BaseModel):
    id: str
    name: str
    objective: str
    status: RoomStatus
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, room: Room) -> "RoomOut":
        return cls(
            id=room.id,
            name=room.name,
            objective=room.objective,
            status=room.status,
            created_at=room.created_at,
            updated_at=room.updated_at,
        )


class RoomDetailOut(RoomOut):
    """A room together with its roster.

    Returned as one object because the interface always needs both, and asking
    for them separately is a round trip the room view would make every time.
    """

    agents: list[AgentOut]

    @classmethod
    def of_detail(cls, detail: RoomWithAgents) -> "RoomDetailOut":
        return cls(
            **RoomOut.of(detail.room).model_dump(),
            agents=[AgentOut.of(a) for a in detail.agents],
        )


# -- messages ---------------------------------------------------------------


class MessageOut(BaseModel):
    id: str
    seq: int
    emitter: Emitter
    emitter_name: str
    content: str
    created_at: datetime

    @classmethod
    def of(cls, message: Message) -> "MessageOut":
        return cls(
            id=message.id,
            seq=message.seq,
            emitter=message.emitter,
            emitter_name=message.emitter_name,
            content=message.content,
            created_at=message.created_at,
        )


class MessagePage(BaseModel):
    """A page of transcript.

    Paged by ``seq`` rather than an offset. A transcript grows while it is
    being read, and an offset would skip or repeat messages as it does.
    """

    items: list[MessageOut]
    next_after_seq: int | None = Field(
        default=None,
        description="Pass as after_seq to continue. Null when the page is the last.",
    )
