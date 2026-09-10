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

__all__ = [
    "ObjectiveStatus",
    "SupervisorAction",
    "SupervisorDecision",
    "decision_json_schema",
    "decision_schema_prompt",
]
