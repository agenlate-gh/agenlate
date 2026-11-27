"""Running one agent's turn.

An agent is given its own persona, the room's objective, what has happened so
far, and one concrete instruction from the Supervisor. It answers once.

Deliberately narrow: the agent does not decide what happens next, does not
choose who goes after it, and cannot end the run. All of that belongs to the
Supervisor, and an agent that could do any of it would be a second orchestrator
with no guard around it.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..llm import LLMClient, Usage
from ..models import Agent, Message
from ..supervisor.prompt import PromptBudget, render_history
from .sources import find_links, remove_links, unsupported_links
from .tools import MAX_TOOL_CALLS, WEB_SEARCH, build_tool_payload, resolve_tools

AGENT_SYSTEM_TEMPLATE = """\
{persona}

# Context

You are one member of a team working toward this shared objective:

{objective}

Your role in the team: {role}

# Your task

Another member coordinates the team and has given you one instruction. Carry \
out that instruction and report the result. Do not decide what the team should \
do next, and do not address other members — report to the coordinator.

Be concrete and complete. What you write is passed on to whoever works next, so \
say what you found or produced rather than describing what you did.

Your reply is the deliverable itself, and the user may download it as it is. \
Write nothing that narrates your process: no "Let me check…", "Good, those are \
verified", "Now I will…", or remarks about limits you ran into. Begin directly \
with the result.

You may have tools for searching the web and reading pages. Use them when the \
task needs current or verifiable information rather than answering from memory, \
and say where anything you report came from. Do all your searching first and \
write your reply once, at the end — any text you write between searches becomes \
part of the deliverable. If you have no tools, work from what is already in the \
transcript and say plainly what you could not check.

Only include a link you got from a search result, from a page you read, or from \
the transcript and instructions above. Never write a link from memory, and \
never guess an article's address: a link that leads nowhere is worse than no \
link. If the task asks for sources, search before you write.\
"""

AGENT_TASK_TEMPLATE = """\
# What has happened so far

{transcript}

# Your instruction

{instruction}\
"""


@dataclass
class AgentResult:
    """What an agent produced, and what it cost."""

    content: str
    usage: Usage
    model: str = ""
    tool_rounds: int = 0
    # Links taken out because nothing the agent searched or was given backs them.
    removed_links: int = 0

    @property
    def is_empty(self) -> bool:
        """Whether the agent effectively said nothing.

        Distinct from failure: the call succeeded and was paid for. It simply
        moved the objective nowhere, which is what the no-progress guard exists
        to notice.
        """
        return not self.content.strip()


def build_agent_prompts(
    agent: Agent,
    instruction: str,
    objective: str,
    transcript: list[Message],
    budget: PromptBudget | None = None,
) -> tuple[str, list[dict[str, str]]]:
    history, _ = render_history(transcript, budget)
    system = AGENT_SYSTEM_TEMPLATE.format(
        persona=agent.system_prompt,
        objective=objective,
        role=agent.role,
    )
    task = AGENT_TASK_TEMPLATE.format(transcript=history, instruction=instruction)
    return system, [{"role": "user", "content": task}]


async def execute_agent(
    agent: Agent,
    instruction: str,
    objective: str,
    transcript: list[Message],
    llm: LLMClient,
    *,
    budget: PromptBudget | None = None,
    max_tokens: int | None = 2048,
    max_tool_calls: int = MAX_TOOL_CALLS,
) -> AgentResult:
    """Run one agent turn.

    One request, even when tools are used. OpenRouter runs the tool loop on its
    own infrastructure and returns a finished answer, so there is no
    client-side round tripping to manage here — and no sandbox for us to build.

    Provider failures propagate: the orchestrator decides what a failed turn
    means for the run, and swallowing it here would hide a dead key behind a
    silently empty answer.
    """
    system, messages = build_agent_prompts(
        agent, instruction, objective, transcript, budget
    )
    tools = build_tool_payload(agent.enabled_tools)

    async def ask(conversation: list[dict[str, str]]):
        return await llm.complete(
            system=system,
            messages=conversation,
            temperature=0.7,  # agents do the creative work; the Supervisor does not
            max_tokens=max_tokens,
            tools=tools,
            max_tool_calls=max_tool_calls if tools else None,
        )

    response = await ask(messages)
    usage = response.usage
    content = response.content.strip()

    # Links the agent could legitimately use: what it was given, plus what any
    # search on this turn returned. The full transcript, not the windowed
    # prompt, so a source found many turns ago still counts.
    given = find_links(
        "\n".join(
            [agent.system_prompt, objective, instruction]
            + [message.content for message in transcript]
        )
    )
    unsupported = unsupported_links(content, given + response.citations)

    # One chance to do it properly, when searching is possible at all. Paid
    # for like any call, and recorded with the turn's usage.
    if unsupported and WEB_SEARCH in resolve_tools(agent.enabled_tools):
        retry = await ask(
            messages
            + [
                {"role": "assistant", "content": content},
                {"role": "user", "content": _unsourced_note(unsupported)},
            ]
        )
        usage = usage + retry.usage
        if retry.content.strip():
            content = retry.content.strip()
        unsupported = unsupported_links(
            content, given + response.citations + retry.citations
        )

    if unsupported:
        content = remove_links(content, unsupported)
        noun = "link was" if len(unsupported) == 1 else "links were"
        content += (
            f"\n\n_{len(unsupported)} {noun} removed because they did not come "
            "from a search or a page the agent read._"
        )

    return AgentResult(
        content=content,
        usage=usage,
        model=response.model,
        tool_rounds=usage.server_tool_calls,
        removed_links=len(unsupported),
    )


def _unsourced_note(links: list[str]) -> str:
    listed = "\n".join(f"- {url}" for url in links[:10])
    return (
        "These links in your reply did not come from a search you ran, a page "
        f"you read, or the transcript:\n{listed}\n\n"
        "Search the web now and rewrite your reply using only links from your "
        "results. Remove any claim or link you cannot back up. Reply with the "
        "complete corrected result only."
    )
