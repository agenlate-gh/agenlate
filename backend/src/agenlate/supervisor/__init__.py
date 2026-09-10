"""The Supervisor: the governance layer that decides who acts next.

Its structured output contract is the architectural heart of the system.
Everything else exists to feed it context or to act on its decisions.
"""

from .contract import (
    ObjectiveStatus,
    SupervisorAction,
    SupervisorDecision,
    decision_json_schema,
    decision_schema_prompt,
)
from .prompt import (
    PromptBudget,
    build_supervisor_messages,
    build_system_prompt,
    build_repair_messages,
    estimate_tokens,
    render_history,
)
from .supervisor import Supervisor, SupervisorConfig, SupervisorError, SupervisorTurn

__all__ = [
    "PromptBudget",
    "Supervisor",
    "SupervisorConfig",
    "SupervisorError",
    "SupervisorTurn",
    "ObjectiveStatus",
    "SupervisorAction",
    "SupervisorDecision",
    "build_repair_messages",
    "build_supervisor_messages",
    "build_system_prompt",
    "decision_json_schema",
    "decision_schema_prompt",
    "estimate_tokens",
    "render_history",
]
