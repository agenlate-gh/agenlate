"""The Supervisor engine: one validated decision per call.

Structured output degrades across chained calls. A model that returns clean
JSON on turn one will, somewhere in a twenty-turn run, wrap it in markdown,
add a sentence of commentary, invent a field, or name an agent that does not
exist. Treating that as an exception would end runs that were going fine.

So the engine repairs. Cheap recoveries happen locally — stripping fences,
locating the JSON inside prose — because they cost nothing. Anything the model
itself has to fix costs a round trip, and round trips cost the user real money,
so they are bounded and counted.

What the engine will not do is guess. When repairs are exhausted it raises. A
fabricated decision would dispatch work nobody asked for, and an orchestrator
that invents its own instructions is worse than one that stops.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from ..llm import LLMClient, Usage
from ..structured import extract_json
from ..models import Message, RoomWithAgents
from .contract import SupervisorDecision
from .prompt import PromptBudget, build_repair_messages, build_supervisor_messages


class SupervisorError(RuntimeError):
    """The Supervisor could not produce a valid decision.

    Raised only after every repair attempt is spent. The run ends; it does not
    continue on a guess.
    """


@dataclass(frozen=True)
class SupervisorConfig:
    max_repair_attempts: int = 2
    """Repair round trips allowed after the first reply. Each costs money."""

    temperature: float = 0.0
    """Turn-taking is a decision, not a creative act."""

    max_tokens: int | None = 1024
    budget: PromptBudget = field(default_factory=PromptBudget)


@dataclass
class SupervisorTurn:
    """The outcome of one consultation.

    Usage is returned alongside the decision rather than accumulated on the
    Supervisor itself: a shared mutable total would interleave between
    concurrent runs and bill the wrong user.
    """

    decision: SupervisorDecision
    usage: Usage
    attempts: int
    """Model calls made, including repairs. One means the first reply stood."""

    model: str = ""
    """Which model produced it. Recorded so the ledger says what was billed."""

    @property
    def needed_repair(self) -> bool:
        return self.attempts > 1


class Supervisor:
    def __init__(self, llm: LLMClient, config: SupervisorConfig | None = None) -> None:
        self._llm = llm
        self._config = config or SupervisorConfig()

    async def decide(
        self, room: RoomWithAgents, messages: list[Message]
    ) -> SupervisorTurn:
        """Produce one validated decision.

        Provider failures propagate untouched: re-prompting cannot fix an
        invalid key or a rate limit, and pretending otherwise would spend the
        repair budget on something no repair can address.
        """
        system, request = build_supervisor_messages(room, messages, self._config.budget)
        valid_ids = {agent.id for agent in room.agents}

        usage = Usage()
        last_error = ""
        raw = ""

        for attempt in range(1, self._config.max_repair_attempts + 2):
            response = await self._llm.complete(
                system=system,
                messages=request,
                temperature=self._config.temperature,
                max_tokens=self._config.max_tokens,
                json_mode=True,
            )
            # Counted before validation: a reply that fails still cost money.
            usage = usage + response.usage
            raw = response.content

            try:
                decision = self._parse(raw, valid_ids)
            except _InvalidDecision as exc:
                last_error = str(exc)
                request = build_repair_messages(request, raw, last_error)
                continue

            return SupervisorTurn(
                decision=decision, usage=usage, attempts=attempt, model=response.model
            )

        raise SupervisorError(
            f"Supervisor produced no valid decision in {self._config.max_repair_attempts + 1} "
            f"attempt(s). Last error: {last_error}"
        )

    def _parse(self, raw: str, valid_ids: set[str]) -> SupervisorDecision:
        payload = extract_json(raw)
        if payload is None:
            raise _InvalidDecision(
                "The reply was not valid JSON. Return only a JSON object."
            )

        try:
            decision = SupervisorDecision.model_validate(payload)
        except ValidationError as exc:
            raise _InvalidDecision(_describe(exc)) from None

        # Checked here rather than in the contract because validity depends on
        # this room's roster, which the schema cannot express.
        if decision.is_dispatch and decision.agent_id not in valid_ids:
            available = ", ".join(sorted(valid_ids)) or "(none)"
            raise _InvalidDecision(
                f"agent_id '{decision.agent_id}' is not in this room. "
                f"Available agent ids: {available}."
            )

        return decision


class _InvalidDecision(Exception):
    """A reply that the model can be asked to fix."""


def _describe(error: ValidationError) -> str:
    """Turn a pydantic error into an instruction the model can act on."""
    lines = []
    for item in error.errors():
        location = ".".join(str(part) for part in item["loc"]) or "(root)"
        lines.append(f"- {location}: {item['msg']}")
    return "The reply did not match the schema:\n" + "\n".join(lines)
