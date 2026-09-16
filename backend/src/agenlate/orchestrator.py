"""The roundtable loop.

Consult the Supervisor, persist its decision, dispatch one agent, persist what
the agent produced, and repeat until something says stop. Everything that can
end a run passes through here, which is why the guard only reports and this
module decides.

Implemented as an async generator so one loop serves both callers: the API
streams the events as they happen, the CLI drains them to completion. A second
implementation for streaming would be a second place for the loop to be subtly
wrong.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import AsyncIterator, Protocol

from .agents.executor import AgentResult, execute_agent
from .llm import (
    LLMAuthError,
    LLMClient,
    LLMCreditError,
    LLMError,
    LLMRateLimited,
    Usage,
)
from .models import Emitter, Message, MessageCreate, RoomWithAgents, UsageEventCreate
from .supervisor import (
    RunGuard,
    RunLimits,
    Supervisor,
    SupervisorConfig,
    SupervisorDecision,
    SupervisorError,
    TerminationReason,
)
from .supervisor.contract import SupervisorAction

def _reason_for(error: LLMError) -> TerminationReason:
    """Map a provider failure to what the user should do about it."""
    if isinstance(error, LLMAuthError):
        return TerminationReason.KEY_REJECTED
    if isinstance(error, LLMCreditError):
        return TerminationReason.OUT_OF_CREDIT
    if isinstance(error, LLMRateLimited):
        return TerminationReason.RATE_LIMITED
    return TerminationReason.PROVIDER_FAILURE


SUPERVISOR_NAME = "Supervisor"
SYSTEM_NAME = "System"
EMPTY_AGENT_NOTE = "(produced no output)"


class RunStore(Protocol):
    """Where a run's messages and costs are written.

    A protocol rather than the repository directly, so the loop can be driven
    end to end with no database. The persistence order matters — a message is
    written before the event announcing it is yielded — and that is far easier
    to verify in memory than against Supabase.
    """

    async def append(self, message: MessageCreate) -> Message: ...

    async def record_usage(self, event: UsageEventCreate) -> None: ...


# -- events -----------------------------------------------------------------


@dataclass
class RunEvent:
    """Base for everything the loop emits."""

    type: str = field(init=False, default="event")


@dataclass
class SupervisorDecided(RunEvent):
    decision: SupervisorDecision
    message: Message
    attempts: int

    def __post_init__(self) -> None:
        self.type = "supervisor_decision"


@dataclass
class AgentStarted(RunEvent):
    agent_id: str
    agent_name: str
    instruction: str

    def __post_init__(self) -> None:
        self.type = "agent_started"


@dataclass
class AgentSpoke(RunEvent):
    agent_id: str
    message: Message

    def __post_init__(self) -> None:
        self.type = "agent_message"


@dataclass
class UsageReported(RunEvent):
    """Emitted after every paid call so the interface can show live spending."""

    usage: Usage
    total: Usage

    def __post_init__(self) -> None:
        self.type = "usage"


@dataclass
class RunFinished(RunEvent):
    result: "RunResult"

    def __post_init__(self) -> None:
        self.type = "run_finished"


@dataclass
class RunResult:
    """How a run ended."""

    reason: TerminationReason
    turns: int
    usage: Usage
    messages_added: int
    final_message: str | None = None
    """What to show the user: the Supervisor's closing words, or why we stopped."""

    detail: str | None = None
    """The underlying failure, when there was one.

    A run that ends in provider_failure has a reason the provider gave — an
    invalid key, an unsupported parameter, a rate limit. Reporting only the
    category tells the user to check their key when the cause was something
    else entirely, and leaves them nothing to act on.
    """

    @property
    def succeeded(self) -> bool:
        return self.reason.is_success

    @property
    def summary(self) -> str:
        return self.final_message or self.reason.describe()


# -- the loop ---------------------------------------------------------------


async def run_room(
    room: RoomWithAgents,
    transcript: list[Message],
    llm: LLMClient,
    store: RunStore,
    *,
    limits: RunLimits | None = None,
    config: SupervisorConfig | None = None,
    user_id: str | None = None,
) -> AsyncIterator[RunEvent]:
    """Run one roundtable to completion, yielding events as they happen."""
    guard = RunGuard(limits)
    supervisor = Supervisor(llm, config)
    history = list(transcript)
    messages_added = 0
    reason: TerminationReason | None = None
    final_message: str | None = None
    detail: str | None = None
    last_turn_was_silent = False

    async def bill(usage: Usage, model: str, message_id: str | None) -> RunEvent:
        """Count a paid call against the guard and write it to the ledger.

        Every call is billed, including Supervisor repairs and turns that
        produced nothing: they were paid for whether or not they helped.
        """
        guard.record_usage(usage)
        if user_id is not None:
            await store.record_usage(
                UsageEventCreate(
                    user_id=user_id,
                    room_id=room.room.id,
                    message_id=message_id,
                    model=model or "unknown",
                    prompt_tokens=usage.prompt_tokens,
                    completion_tokens=usage.completion_tokens,
                    cost_usd=usage.cost_usd,
                    server_tool_calls=usage.server_tool_calls,
                )
            )
        return UsageReported(usage=usage, total=guard.state.usage)

    while reason is None:
        stop = guard.check()
        if stop is not None:
            reason = stop
            break

        # -- consult the Supervisor --------------------------------------
        try:
            turn = await supervisor.decide(room, history)
        except LLMError as exc:
            reason = _reason_for(exc)
            detail = str(exc)
            break
        except SupervisorError as exc:
            reason = TerminationReason.SUPERVISOR_FAILURE
            detail = str(exc)
            break

        decision = turn.decision
        note = await store.append(
            MessageCreate(
                room_id=room.room.id,
                emitter=Emitter.SUPERVISOR,
                emitter_name=SUPERVISOR_NAME,
                content=decision.reasoning,
            )
        )
        history.append(note)
        messages_added += 1
        yield await bill(turn.usage, turn.model, note.id)
        yield SupervisorDecided(decision=decision, message=note, attempts=turn.attempts)

        if decision.is_terminal:
            if decision.action is not SupervisorAction.COMPLETE:
                reason = TerminationReason.AWAITING_USER
            elif last_turn_was_silent:
                # The Supervisor claimed success immediately after an agent
                # produced nothing. Observed with a weaker model: the user is
                # told the objective was achieved and receives an empty result,
                # which is worse than being told it failed. The run still ends —
                # another turn costs money on no evidence it would help — but it
                # ends honestly.
                reason = TerminationReason.COMPLETED_EMPTY
            else:
                reason = TerminationReason.COMPLETED
            final_message = decision.message_to_user
            break

        # -- dispatch ----------------------------------------------------
        # Registered before the agent runs so a stall is caught before paying
        # for the execution that would repeat it.
        guard.record_dispatch(decision)
        stop = guard.check()
        if stop is not None:
            reason = stop
            break

        agent = room.agent_by_id(decision.agent_id or "")
        if agent is None:
            # The Supervisor validates ids against this roster, so reaching
            # here means the roster changed underneath a running room.
            reason = TerminationReason.SUPERVISOR_FAILURE
            break

        yield AgentStarted(
            agent_id=agent.id,
            agent_name=agent.name,
            instruction=decision.instruction or "",
        )

        try:
            result = await execute_agent(
                agent,
                decision.instruction or "",
                room.room.objective,
                history,
                llm,
            )
        except LLMError as exc:
            reason = _reason_for(exc)
            detail = str(exc)
            break

        spoke = await store.append(_agent_message(room.room.id, agent.name, result))
        history.append(spoke)
        messages_added += 1
        yield await bill(result.usage, result.model, spoke.id)
        yield AgentSpoke(agent_id=agent.id, message=spoke)

        last_turn_was_silent = result.is_empty
        guard.record_progress(0 if result.is_empty else 1)

    yield RunFinished(
        result=RunResult(
            reason=reason,
            turns=guard.state.turns,
            usage=guard.state.usage,
            messages_added=messages_added,
            final_message=final_message,
            detail=detail,
        )
    )


def _agent_message(room_id: str, agent_name: str, result: AgentResult) -> MessageCreate:
    """Record what the agent produced, including when it produced nothing.

    A silent turn is written down rather than dropped. The transcript is what
    the Supervisor reasons from next, and a gap it cannot see would look like a
    step that never happened.
    """
    if result.is_empty:
        return MessageCreate(
            room_id=room_id,
            emitter=Emitter.SYSTEM,
            emitter_name=SYSTEM_NAME,
            content=f"{agent_name} {EMPTY_AGENT_NOTE}",
        )
    return MessageCreate(
        room_id=room_id,
        emitter=Emitter.AGENT,
        emitter_name=agent_name,
        content=result.content,
    )
