"""Run a roundtable from the terminal.

The milestone gate for the orchestration core: everything below the HTTP layer,
exercised against a real provider, with agents defined in a local file and no
interface, no database and no account involved.

    python -m agenlate.cli run --objective "..." --agents agents.json
    python -m agenlate.cli run --objective "..." --agents agents.json --dry-run
    python -m agenlate.cli example > agents.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .agents.tools import DEFAULT_TOOLS
from .llm import FakeLLM, LLMClient
from .llm.openrouter import OpenRouterClient
from .models import Agent, Room, RoomWithAgents
from .orchestrator import (
    AgentSpoke,
    AgentStarted,
    RunFinished,
    SupervisorDecided,
    UsageReported,
    run_room,
)
from .store import InMemoryRunStore
from .supervisor import RunLimits

NOW = datetime.now(timezone.utc)

EXAMPLE = {
    "objective": "Write a short, well-sourced brief on coffee shop trends in 2026",
    "agents": [
        {
            "name": "Researcher",
            "role": "finds and verifies current information",
            "system_prompt": (
                "You are a meticulous researcher. You search for current "
                "information, check it against more than one source, and always "
                "say where a claim came from. You never guess at a figure."
            ),
        },
        {
            "name": "Writer",
            "role": "turns research into clear prose for a general audience",
            "system_prompt": (
                "You are a clear, plain-spoken writer. You explain things to "
                "small business owners without jargon. You only state what the "
                "research supports."
            ),
        },
        {
            "name": "Critic",
            "role": "reviews drafts and names specific weaknesses",
            "system_prompt": (
                "You are a sharp editor. You point out unsupported claims, weak "
                "arguments and vague wording, and you say exactly what would fix "
                "each one. You are specific rather than encouraging."
            ),
        },
    ],
}


# -- presentation -----------------------------------------------------------

_COLOUR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _use_unicode() -> bool:
    """Whether this terminal can render the box-drawing characters.

    The Windows console defaults to cp1252, which cannot. Discovering that
    mid-run raises UnicodeEncodeError and takes the whole command down, so the
    glyphs are chosen up front — after asking the stream to switch to UTF-8,
    which usually succeeds and is the nicer outcome.
    """
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, OSError, ValueError):
        pass
    try:
        "─→".encode(sys.stdout.encoding or "ascii")
        return True
    except (UnicodeEncodeError, LookupError):
        return False


_UNICODE = _use_unicode()
_BAR = "─" if _UNICODE else "-"
_ARROW = "→" if _UNICODE else "->"


def _paint(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOUR else text


def _rule(label: str = "") -> str:
    return _paint(f"{_BAR * 4} {label} " + _BAR * max(0, 66 - len(label)), "90")


def _wrap(text: str, indent: str = "    ") -> str:
    import textwrap

    paragraphs = text.strip().split("\n")
    lines = []
    for paragraph in paragraphs:
        if not paragraph.strip():
            lines.append("")
            continue
        lines.extend(
            textwrap.wrap(paragraph, width=76, initial_indent=indent, subsequent_indent=indent)
            or [indent]
        )
    return "\n".join(lines)


# -- loading ----------------------------------------------------------------


def load_room(path: Path, objective: str | None) -> RoomWithAgents:
    """Build a room from a local agents file."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"No such file: {path}. Try: python -m agenlate.cli example > {path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path} is not valid JSON: {exc}")

    definitions = raw.get("agents") if isinstance(raw, dict) else raw
    if not isinstance(definitions, list) or not definitions:
        raise SystemExit(f"{path} must contain a non-empty list of agents")

    resolved = objective or (raw.get("objective") if isinstance(raw, dict) else None)
    if not resolved:
        raise SystemExit("An objective is required: pass --objective or set it in the file")

    agents = []
    for index, definition in enumerate(definitions):
        missing = [k for k in ("name", "role", "system_prompt") if not definition.get(k)]
        if missing:
            raise SystemExit(f"Agent {index + 1} is missing: {', '.join(missing)}")
        agents.append(
            Agent(
                id=f"agent-{index + 1}",
                creator_id="local",
                name=definition["name"],
                role=definition["role"],
                system_prompt=definition["system_prompt"],
                enabled_tools=definition.get("enabled_tools"),
                created_at=NOW,
                updated_at=NOW,
            )
        )

    room = Room(
        id="local-room",
        creator_id="local",
        name="Local run",
        objective=resolved,
        created_at=NOW,
        updated_at=NOW,
    )
    return RoomWithAgents(room=room, agents=agents)


def build_client(args, room: RoomWithAgents) -> LLMClient:
    if args.dry_run:
        return FakeLLM(_rehearsal(room), model="fake/model")

    key = args.key or os.environ.get("OPENROUTER_API_KEY") or _key_from_env_file()
    if not key:
        raise SystemExit(
            "No OpenRouter key. Pass --key, set OPENROUTER_API_KEY, add it to "
            "backend/.env, or use --dry-run."
        )
    return OpenRouterClient(key, model=args.model)


def _key_from_env_file() -> str | None:
    """Read a developer's own key from backend/.env.

    A local convenience for this command only. The server never obtains a key
    this way: under BYOK the key arrives per run from the user's browser and is
    never read from configuration.
    """
    env_file = Path(__file__).resolve().parents[2] / ".env"
    if not env_file.exists():
        return None
    for line in env_file.read_text(encoding="utf-8").splitlines():
        name, _, value = line.partition("=")
        if name.strip() == "OPENROUTER_API_KEY" and value.strip():
            return value.strip()
    return None


def _rehearsal(room: RoomWithAgents) -> list[str]:
    """A scripted run for --dry-run.

    Exercises the real loop — supervisor, guard, persistence, accounting — with
    only the provider replaced. Useful for showing the mechanism to someone
    without spending their credit.
    """
    script: list[str] = []
    for agent in room.agents:
        script.append(
            json.dumps(
                {
                    "reasoning": f"{agent.name} is the right fit for the next step.",
                    "action": "dispatch",
                    "objective_status": "in_progress",
                    "agent_id": agent.id,
                    "instruction": f"Carry out your part of: {room.room.objective}",
                }
            )
        )
        script.append(f"[rehearsal] {agent.name} would do its work here.")
    script.append(
        json.dumps(
            {
                "reasoning": "Every agent has contributed and the objective is met.",
                "action": "complete",
                "objective_status": "achieved",
                "message_to_user": "Rehearsal complete — no provider was called.",
            }
        )
    )
    return script


# -- running ----------------------------------------------------------------


async def run(args) -> int:
    room = load_room(Path(args.agents), args.objective)
    llm = build_client(args, room)
    store = InMemoryRunStore(room.room.id)
    limits = RunLimits(max_turns=args.max_turns, spend_cap_usd=args.spend_cap)

    print(_rule("objective"))
    print(_wrap(room.room.objective))
    print(_rule("roster"))
    for agent in room.agents:
        tools = agent.enabled_tools if agent.enabled_tools is not None else list(DEFAULT_TOOLS)
        print(f"    {_paint(agent.name, '1')} — {agent.role}")
        print(f"        tools: {', '.join(t.split(':')[-1] for t in tools) or 'none'}")
    print(_rule("run"))

    result = None
    try:
        async for event in run_room(room, [], llm, store, limits=limits):
            if isinstance(event, SupervisorDecided):
                repaired = "" if event.attempts == 1 else f" (repaired ×{event.attempts - 1})"
                print(_paint(f"\n  SUPERVISOR{repaired}", "36;1"))
                print(_wrap(event.decision.reasoning, "    "))
                if event.decision.is_dispatch:
                    print(_paint(f"    {_ARROW} {event.decision.instruction}", "36"))
            elif isinstance(event, AgentStarted):
                print(_paint(f"\n  {event.agent_name.upper()}", "33;1"))
            elif isinstance(event, AgentSpoke):
                print(_wrap(event.message.content, "    "))
            elif isinstance(event, RunFinished):
                result = event.result
    finally:
        await llm.aclose()

    assert result is not None
    _report(result, store)
    return 0 if result.succeeded else 1


def _report(result, store: InMemoryRunStore) -> None:
    usage = result.usage
    print()
    print(_rule("result"))
    print(f"    outcome        {_paint(result.reason.value, '1')}")
    print(f"    {_wrap(result.reason.describe(), '                   ').strip()}")
    if result.final_message:
        print()
        print(_wrap(result.final_message, "    "))
    if result.detail:
        print()
        print(_paint(_wrap(result.detail, "    "), "31"))

    print()
    print(_rule("accounting"))
    print(f"    turns          {result.turns}")
    print(f"    messages       {result.messages_added}")
    print(f"    model calls    {usage.calls}")
    print(f"    tokens         {usage.total_tokens:,} "
          f"({usage.prompt_tokens:,} in / {usage.completion_tokens:,} out)")
    cost = "not reported" if usage.cost_usd is None else f"${usage.cost_usd:.6f}"
    print(f"    reported cost  {cost}")
    print(f"    tool steps     {usage.server_tool_calls}")

    if usage.has_unknown_cost:
        print()
        print(_paint(
            f"    {usage.unpriced_calls} of {usage.calls} calls reported no cost, so the "
            "figure above is a floor, not a total.", "33"))

    # Tool charges are inside the reported cost: a free model with no tools
    # reports exactly zero, and the same free model performing one web search
    # reports $0.007. So the figure above already includes tool use. The step
    # count is not reliable — server_tool_use is frequently null — which is why
    # it is not used to reason about spending.
    if usage.server_tool_calls:
        print()
        print(_paint(
            f"    {usage.server_tool_calls} tool step(s) reported. Tool charges are "
            "included in the cost above.", "90"))


# -- entry point ------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agenlate",
        description="Run a roundtable of AI agents from the terminal.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_cmd = sub.add_parser("run", help="run a roundtable")
    run_cmd.add_argument("--agents", default="agents.json", help="JSON file defining the agents")
    run_cmd.add_argument("--objective", help="what the team should achieve")
    run_cmd.add_argument("--key", help="OpenRouter API key (or set OPENROUTER_API_KEY)")
    run_cmd.add_argument("--model", default="anthropic/claude-sonnet-4.5")
    run_cmd.add_argument("--max-turns", type=int, default=12)
    run_cmd.add_argument("--spend-cap", type=float, default=0.50,
                         help="stop once this much reported cost is reached")
    run_cmd.add_argument("--dry-run", action="store_true",
                         help="use a scripted provider; calls nothing and costs nothing")

    sub.add_parser("example", help="print a starter agents file")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "example":
        print(json.dumps(EXAMPLE, indent=2))
        return 0

    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
