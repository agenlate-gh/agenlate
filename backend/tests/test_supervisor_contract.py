"""The Supervisor decision contract.

Every turn of every session is validated by this schema, so its edges are worth
pinning down precisely.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agenlate.supervisor.contract import (
    INSTRUCTION_MAX,
    REASONING_MAX,
    ObjectiveStatus,
    SupervisorAction,
    SupervisorDecision,
    decision_json_schema,
    decision_schema_prompt,
)


def dispatch(**overrides) -> SupervisorDecision:
    return SupervisorDecision(
        **{
            "reasoning": "The objective needs research first.",
            "action": "dispatch",
            "objective_status": "in_progress",
            "agent_id": "agent-1",
            "instruction": "Find three current sources on coffee trends",
            **overrides,
        }
    )


def complete(**overrides) -> SupervisorDecision:
    return SupervisorDecision(
        **{
            "reasoning": "The draft has been written and reviewed.",
            "action": "complete",
            "objective_status": "achieved",
            "message_to_user": "Here is your finished post.",
            **overrides,
        }
    )


class TestValidActions:
    def test_dispatch(self) -> None:
        decision = dispatch()

        assert decision.is_dispatch is True
        assert decision.is_terminal is False
        assert decision.agent_id == "agent-1"

    def test_complete(self) -> None:
        decision = complete()

        assert decision.action is SupervisorAction.COMPLETE
        assert decision.is_terminal is True
        assert decision.objective_status is ObjectiveStatus.ACHIEVED

    def test_await_user(self) -> None:
        decision = SupervisorDecision(
            reasoning="This needs a human decision.",
            action="await_user",
            objective_status="blocked",
            message_to_user="Should I publish this?",
        )

        assert decision.is_terminal is True

    def test_every_action_has_a_valid_shape(self) -> None:
        """Guards against an action being added to the enum with no way to
        construct it."""
        constructed = {dispatch().action, complete().action}
        constructed.add(
            SupervisorDecision(
                reasoning="r",
                action="await_user",
                objective_status="blocked",
                message_to_user="m",
            ).action
        )

        assert constructed == set(SupervisorAction)


class TestDispatchRequirements:
    def test_dispatch_without_agent_id_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="requires agent_id"):
            dispatch(agent_id=None)

    def test_dispatch_with_blank_agent_id_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="requires agent_id"):
            dispatch(agent_id="   ")

    def test_dispatch_without_instruction_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="non-empty instruction"):
            dispatch(instruction=None)

    @pytest.mark.parametrize("blank", ["", "   ", "\n\t "])
    def test_dispatch_with_whitespace_instruction_is_rejected(self, blank) -> None:
        """An instruction of only whitespace passes a length check and tells
        the agent nothing."""
        with pytest.raises(ValidationError, match="non-empty instruction"):
            dispatch(instruction=blank)


class TestTerminalRequirements:
    @pytest.mark.parametrize("action", ["complete", "await_user"])
    def test_terminal_action_without_a_message_is_rejected(self, action) -> None:
        with pytest.raises(ValidationError, match="requires message_to_user"):
            SupervisorDecision(
                reasoning="r", action=action, objective_status="achieved"
            )

    @pytest.mark.parametrize("action", ["complete", "await_user"])
    def test_terminal_action_with_a_blank_message_is_rejected(self, action) -> None:
        with pytest.raises(ValidationError, match="requires message_to_user"):
            SupervisorDecision(
                reasoning="r",
                action=action,
                objective_status="achieved",
                message_to_user="  ",
            )


class TestInapplicableFieldsAreCleared:
    """A field that does not apply to the chosen action is cleared rather than
    rejected, so no caller downstream can act on it."""

    def test_completing_clears_a_stray_dispatch_target(self) -> None:
        decision = complete(agent_id="agent-1", instruction="do more work")

        assert decision.agent_id is None
        assert decision.instruction is None
        assert decision.dispatch_signature() is None

    def test_dispatching_clears_a_stray_user_message(self) -> None:
        decision = dispatch(message_to_user="all done!")

        assert decision.message_to_user is None

    def test_clearing_is_preferred_to_rejecting(self) -> None:
        """Rejecting would cost a repair round trip, and a repair costs real
        money. The action field is the authoritative statement of intent."""
        decision = complete(agent_id="agent-1", instruction="ignored")

        assert decision.action is SupervisorAction.COMPLETE


class TestClosedSchema:
    def test_an_unknown_field_is_rejected(self) -> None:
        """A model inventing a field is a failure to repair, not a value to
        silently ignore."""
        with pytest.raises(ValidationError):
            dispatch(next_steps=["something the model made up"])

    def test_an_unknown_action_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            dispatch(action="ask_another_agent")

    def test_an_unknown_objective_status_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            dispatch(objective_status="probably_fine")


class TestFieldLimits:
    def test_reasoning_is_required(self) -> None:
        with pytest.raises(ValidationError):
            dispatch(reasoning="")

    def test_reasoning_is_capped(self) -> None:
        """Reasoning is re-sent as context and shown to the user; an essay per
        turn is paid for twice."""
        with pytest.raises(ValidationError):
            dispatch(reasoning="x" * (REASONING_MAX + 1))

    def test_instruction_is_capped(self) -> None:
        with pytest.raises(ValidationError):
            dispatch(instruction="x" * (INSTRUCTION_MAX + 1))


class TestDispatchSignature:
    def test_combines_agent_and_instruction(self) -> None:
        signature = dispatch(agent_id="a1", instruction="Research coffee").dispatch_signature()

        assert signature == "a1::research coffee"

    def test_is_none_for_non_dispatch_decisions(self) -> None:
        assert complete().dispatch_signature() is None

    def test_case_differences_collide(self) -> None:
        first = dispatch(instruction="Research Coffee Trends").dispatch_signature()
        second = dispatch(instruction="research coffee trends").dispatch_signature()

        assert first == second

    def test_whitespace_differences_collide(self) -> None:
        first = dispatch(instruction="research   coffee\n trends").dispatch_signature()
        second = dispatch(instruction=" research coffee trends ").dispatch_signature()

        assert first == second

    def test_trailing_punctuation_differences_collide(self) -> None:
        """A Supervisor going in circles rephrases lightly rather than
        repeating itself exactly."""
        first = dispatch(instruction="Research coffee trends.").dispatch_signature()
        second = dispatch(instruction="Research coffee trends").dispatch_signature()

        assert first == second

    def test_the_same_instruction_to_a_different_agent_does_not_collide(self) -> None:
        first = dispatch(agent_id="a1", instruction="summarise").dispatch_signature()
        second = dispatch(agent_id="a2", instruction="summarise").dispatch_signature()

        assert first != second

    def test_genuinely_different_instructions_do_not_collide(self) -> None:
        """Normalisation must not be so aggressive that real progress looks
        like a stall."""
        first = dispatch(instruction="Research coffee trends").dispatch_signature()
        second = dispatch(instruction="Research tea trends").dispatch_signature()

        assert first != second


class TestGeneratedSchema:
    def test_schema_properties_match_the_model_fields(self) -> None:
        """The schema is generated, not hand-written. A hand-written copy is
        correct the day it is written and quietly wrong thereafter."""
        schema = decision_json_schema()

        assert set(schema["properties"]) == set(SupervisorDecision.model_fields)

    def test_schema_marks_the_always_required_fields(self) -> None:
        schema = decision_json_schema()

        assert set(schema["required"]) == {"reasoning", "action", "objective_status"}

    def test_schema_enumerates_exactly_the_valid_actions(self) -> None:
        schema = decision_json_schema()
        action_enum = schema["$defs"]["SupervisorAction"]["enum"]

        assert set(action_enum) == {a.value for a in SupervisorAction}

    def test_schema_enumerates_exactly_the_valid_statuses(self) -> None:
        schema = decision_json_schema()
        status_enum = schema["$defs"]["ObjectiveStatus"]["enum"]

        assert set(status_enum) == {s.value for s in ObjectiveStatus}

    def test_schema_forbids_additional_properties(self) -> None:
        assert decision_json_schema()["additionalProperties"] is False

    def test_schema_prompt_is_valid_json(self) -> None:
        import json

        assert json.loads(decision_schema_prompt()) == decision_json_schema()

    def test_field_descriptions_reach_the_schema(self) -> None:
        """The descriptions are how the model learns when each field applies."""
        properties = decision_json_schema()["properties"]

        assert "dispatch" in properties["agent_id"]["description"]
        assert "complete" in properties["message_to_user"]["description"]


class TestRoundTrip:
    def test_a_decision_survives_serialisation(self) -> None:
        original = dispatch()

        restored = SupervisorDecision.model_validate(original.model_dump())

        assert restored == original

    def test_json_from_a_model_parses_back(self) -> None:
        """The path a real decision takes: model emits JSON, we parse it."""
        raw = (
            '{"reasoning": "Research is needed first.", "action": "dispatch", '
            '"objective_status": "in_progress", "agent_id": "a1", '
            '"instruction": "Find sources"}'
        )

        decision = SupervisorDecision.model_validate_json(raw)

        assert decision.is_dispatch
        assert decision.dispatch_signature() == "a1::find sources"
