"""Domain models.

These mirror the Supabase tables one for one, so the same shapes carry from the
orchestration core into the persistence layer without a translation step.

Field limits match the database check constraints deliberately. Validating in
both places is not redundant: the database is the guarantee, the model is the
error message a user can act on.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

# Kept in step with the check constraints in
# supabase/migrations/20260910120000_initial_schema.sql
NAME_MAX = 100
ROLE_MAX = 200
SYSTEM_PROMPT_MAX = 8000
ROOM_NAME_MAX = 200
OBJECTIVE_MAX = 4000


class Emitter(str, Enum):
    """Who produced a message. Drives how it renders into Supervisor context."""

    USER = "user"
    AGENT = "agent"
    SUPERVISOR = "supervisor"
    SYSTEM = "system"


class _Row(BaseModel):
    """Base for anything read back from the database."""

    model_config = ConfigDict(extra="ignore")


class User(_Row):
    """Table: users. Mirrors auth.users with application state attached."""

    id: str
    email: str
    credit_balance: float = 0.0
    created_at: datetime


class Agent(_Row):
    """Table: agents. A user-designed worker profile."""

    id: str
    creator_id: str
    name: str
    role: str
    system_prompt: str
    enabled_tools: list[str] | None = None
    """Which server tools this agent may call. None means the defaults."""

    created_at: datetime
    updated_at: datetime

    def capability_line(self) -> str:
        """One-line summary for the Supervisor's roster.

        Deliberately terse. The roster is re-sent on every turn, so each extra
        character here is multiplied by the turn count and paid for in tokens.
        """
        return f"- id={self.id} | name={self.name} | role={self.role}"


class AgentCreate(BaseModel):
    """What a caller may supply when creating an agent.

    Separate from ``Agent`` so server-owned fields — id, creator_id, timestamps
    — cannot be set from outside.
    """

    name: str = Field(min_length=1, max_length=NAME_MAX)
    role: str = Field(min_length=1, max_length=ROLE_MAX)
    system_prompt: str = Field(min_length=1, max_length=SYSTEM_PROMPT_MAX)
    enabled_tools: list[str] | None = None


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=NAME_MAX)
    role: str | None = Field(default=None, min_length=1, max_length=ROLE_MAX)
    system_prompt: str | None = Field(
        default=None, min_length=1, max_length=SYSTEM_PROMPT_MAX
    )
    enabled_tools: list[str] | None = None


class RoomStatus(str, Enum):
    """Whether a room will accept a new run.

    Pausing exists so that stopping the spending on a room does not mean
    deleting it. A paused room keeps its roster and its transcript; it just
    refuses to start.
    """

    ACTIVE = "active"
    PAUSED = "paused"


class Room(_Row):
    """Table: rooms. One roundtable session working toward one objective."""

    id: str
    creator_id: str
    name: str
    objective: str
    status: RoomStatus = RoomStatus.ACTIVE
    created_at: datetime
    updated_at: datetime


class RoomCreate(BaseModel):
    name: str = Field(min_length=1, max_length=ROOM_NAME_MAX)
    objective: str = Field(min_length=1, max_length=OBJECTIVE_MAX)


class RoomUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=ROOM_NAME_MAX)
    objective: str | None = Field(default=None, min_length=1, max_length=OBJECTIVE_MAX)
    status: RoomStatus | None = None


class RoomWithAgents(BaseModel):
    """A room and its roster, fetched together.

    The orchestrator needs both on every turn, and fetching them separately is
    the beginning of an N+1.
    """

    room: Room
    agents: list[Agent]

    def agent_by_id(self, agent_id: str) -> Agent | None:
        """Resolve a Supervisor's dispatch target.

        Returns None for an unknown id rather than raising: a hallucinated
        agent id is an expected model failure the Supervisor repairs, not an
        exceptional condition.
        """
        return next((a for a in self.agents if a.id == agent_id), None)

    def roster(self) -> str:
        return "\n".join(agent.capability_line() for agent in self.agents)


class Message(_Row):
    """Table: messages. The transcript, and the Supervisor's context memory."""

    id: str
    seq: int
    room_id: str
    emitter: Emitter
    emitter_name: str
    content: str
    created_at: datetime

    def render(self) -> str:
        """Format for inclusion in a prompt."""
        return f"[{self.emitter_name}]: {self.content}"


class MessageCreate(BaseModel):
    room_id: str
    emitter: Emitter
    emitter_name: str = Field(min_length=1, max_length=NAME_MAX)
    content: str


class UsageEvent(_Row):
    """Table: usage_events. What one provider request actually cost.

    ``cost_usd`` is None when the provider reported no cost. That is not the
    same as free, which is why ``is_priced`` exists alongside it and why the
    database refuses rows where the two disagree.
    """

    id: str
    user_id: str
    room_id: str | None = None
    message_id: str | None = None
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float | None = None
    is_priced: bool = False
    server_tool_calls: int = 0
    provider_generation_id: str | None = None
    created_at: datetime

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class UsageEventCreate(BaseModel):
    """A usage row about to be written.

    ``is_priced`` is derived from ``cost_usd`` rather than accepted from the
    caller, so the two cannot be set inconsistently and a missing cost can
    never be recorded as zero.
    """

    user_id: str
    model: str
    room_id: str | None = None
    message_id: str | None = None
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    server_tool_calls: int = Field(default=0, ge=0)
    provider_generation_id: str | None = None

    @property
    def is_priced(self) -> bool:
        return self.cost_usd is not None
