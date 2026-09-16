"""Keeping the user's key out of logs, errors and storage.

The acceptance test here is the last class: a full run, including an induced
provider failure, with every log record captured and searched for the key.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import pytest

from agenlate.llm import FakeLLM, LLMError, Usage
from agenlate.models import (
    Agent,
    Message,
    MessageCreate,
    Room,
    RoomWithAgents,
    UsageEventCreate,
)
from agenlate.orchestrator import run_room
from agenlate.security import (
    REDACTED,
    SecretRedactingFilter,
    install_redaction,
    looks_like_openrouter_key,
    redact,
)

KEY = "sk-or-v1-0a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f6071"
NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)


class TestRedaction:
    def test_removes_an_openrouter_key(self) -> None:
        assert KEY not in redact(f"failed with key {KEY} attached")
        assert REDACTED in redact(f"failed with key {KEY}")

    def test_removes_a_key_embedded_in_a_header_dump(self) -> None:
        """The realistic case: an exception that stringified a request."""
        dump = f"{{'Authorization': 'Bearer {KEY}', 'X-Title': 'Agenlate'}}"

        cleaned = redact(dump)

        assert KEY not in cleaned
        assert "X-Title" in cleaned  # only the secret goes

    def test_removes_several_keys_from_one_string(self) -> None:
        other = "sk-or-v1-ffffffffffffffffffffffffffffffffffffffff"

        cleaned = redact(f"{KEY} and {other}")

        assert KEY not in cleaned and other not in cleaned

    def test_removes_a_key_from_another_provider(self) -> None:
        """A user pasting the wrong key should not have that leak either."""
        openai_key = "sk-proj0000000000000000000000000000000000"

        assert openai_key not in redact(f"using {openai_key}")

    def test_leaves_ordinary_text_alone(self) -> None:
        text = "The Supervisor dispatched to agent-1 and the run completed."

        assert redact(text) == text

    def test_leaves_short_sk_words_alone(self) -> None:
        """Not everything beginning with sk- is a secret."""
        assert redact("sk-test") == "sk-test"


class TestLogFilter:
    @pytest.fixture
    def captured(self):
        records: list[str] = []

        class Capture(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(self.format(record))

        handler = Capture()
        handler.addFilter(SecretRedactingFilter())
        logger = logging.getLogger("test.redaction")
        logger.handlers = [handler]
        logger.propagate = False
        logger.setLevel(logging.DEBUG)
        return logger, records

    def test_a_key_in_a_message_is_redacted(self, captured) -> None:
        logger, records = captured

        logger.error("provider rejected %s", KEY)

        assert KEY not in records[0]

    def test_a_key_in_a_formatted_message_is_redacted(self, captured) -> None:
        logger, records = captured

        logger.error(f"provider rejected {KEY}")

        assert KEY not in records[0]

    def test_a_key_in_a_traceback_is_redacted(self, captured) -> None:
        """The likeliest carrier of all."""
        logger, records = captured

        try:
            raise RuntimeError(f"request failed with Bearer {KEY}")
        except RuntimeError:
            logger.exception("run failed")

        assert KEY not in records[0]

    def test_a_key_in_dict_arguments_is_redacted(self, captured) -> None:
        logger, records = captured

        logger.error("auth %(key)s", {"key": KEY})

        assert KEY not in records[0]

    def test_installing_twice_does_not_stack_filters(self) -> None:
        install_redaction()
        install_redaction()

        root = logging.getLogger()
        filters = [f for f in root.filters if isinstance(f, SecretRedactingFilter)]
        assert len(filters) == 1


class TestKeyShape:
    def test_accepts_a_well_formed_key(self) -> None:
        assert looks_like_openrouter_key(KEY)

    def test_tolerates_surrounding_whitespace(self) -> None:
        """People paste keys, and pasting brings whitespace."""
        assert looks_like_openrouter_key(f"  {KEY}\n")

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "   ",
            "not-a-key",
            "sk-or-v1-",           # prefix only
            "sk-or-v1-short",      # truncated
            "sk-proj-0000000000000000000000000000",  # another provider
        ],
    )
    def test_rejects_malformed_values(self, value) -> None:
        assert not looks_like_openrouter_key(value)


class TestKeyNeverReachesStorageOrLogs:
    """The acceptance test: a full run, including a provider failure, with
    every log record captured."""

    @staticmethod
    def make_room() -> RoomWithAgents:
        agent = Agent(
            id="agent-1",
            creator_id="u1",
            name="Researcher",
            role="finds things",
            system_prompt="research",
            created_at=NOW,
            updated_at=NOW,
        )
        return RoomWithAgents(
            room=Room(
                id="room-1",
                creator_id="u1",
                name="R",
                objective="Find something out",
                created_at=NOW,
                updated_at=NOW,
            ),
            agents=[agent],
        )

    class Store:
        def __init__(self) -> None:
            self.messages: list[Message] = []
            self.usage: list[UsageEventCreate] = []

        async def append(self, message: MessageCreate) -> Message:
            stored = Message(
                id=f"m{len(self.messages) + 1}",
                seq=len(self.messages) + 1,
                room_id=message.room_id,
                emitter=message.emitter,
                emitter_name=message.emitter_name,
                content=message.content,
                created_at=NOW,
            )
            self.messages.append(stored)
            return stored

        async def record_usage(self, event: UsageEventCreate) -> None:
            self.usage.append(event)

        def dump(self) -> str:
            return json.dumps(
                [m.model_dump(mode="json") for m in self.messages]
                + [u.model_dump(mode="json") for u in self.usage],
                default=str,
            )

    @pytest.fixture
    def all_logs(self):
        """Capture everything logged anywhere, with redaction installed."""
        records: list[str] = []

        class Capture(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                try:
                    records.append(self.format(record))
                except Exception:
                    records.append(str(record.msg))

        handler = Capture()
        root = logging.getLogger()
        previous_level = root.level
        root.addHandler(handler)
        root.setLevel(logging.DEBUG)
        install_redaction()
        handler.addFilter(SecretRedactingFilter())
        yield records
        root.removeHandler(handler)
        root.setLevel(previous_level)

    async def test_a_failing_run_leaks_no_key_to_logs_or_storage(self, all_logs) -> None:
        """A provider error is where a key is most likely to escape: the
        failure path is the one nobody exercises by hand."""
        from agenlate.llm.openrouter import OpenRouterClient

        client = OpenRouterClient(KEY)
        logging.getLogger("run").error("starting with client %s", client)
        logging.getLogger("run").error("headers were %s", client._headers())

        try:
            raise LLMError(f"OpenRouter returned 401 for Bearer {KEY}")
        except LLMError:
            logging.getLogger("run").exception("run failed")

        await client.aclose()

        joined = "\n".join(all_logs)
        assert KEY not in joined, "the key reached a log record"

    async def test_a_complete_run_writes_no_key_to_storage(self) -> None:
        script = [
            json.dumps(
                {
                    "reasoning": "Research first.",
                    "action": "dispatch",
                    "objective_status": "in_progress",
                    "agent_id": "agent-1",
                    "instruction": "Find it",
                }
            ),
            "Found it.",
            json.dumps(
                {
                    "reasoning": "Done.",
                    "action": "complete",
                    "objective_status": "achieved",
                    "message_to_user": "Here you are.",
                }
            ),
        ]
        store = self.Store()

        async for _ in run_room(
            self.make_room(), [], FakeLLM(script), store, user_id="u1"
        ):
            pass

        assert KEY not in store.dump()
        assert "sk-or-v1" not in store.dump()

    async def test_a_provider_failure_mid_run_writes_no_key(self) -> None:
        script = [
            json.dumps(
                {
                    "reasoning": "Research first.",
                    "action": "dispatch",
                    "objective_status": "in_progress",
                    "agent_id": "agent-1",
                    "instruction": "Find it",
                }
            ),
            LLMError(f"OpenRouter returned 401: invalid key {KEY}"),
        ]
        store = self.Store()

        async for _ in run_room(
            self.make_room(), [], FakeLLM(script), store, user_id="u1"
        ):
            pass

        assert KEY not in store.dump()

    async def test_the_usage_ledger_carries_no_key(self) -> None:
        store = self.Store()
        script = [
            json.dumps(
                {
                    "reasoning": "Done.",
                    "action": "complete",
                    "objective_status": "achieved",
                    "message_to_user": "Here you are.",
                }
            )
        ]

        async for _ in run_room(
            self.make_room(),
            [],
            FakeLLM(script, usage_per_call=Usage.for_call(cost_usd=0.01)),
            store,
            user_id="u1",
        ):
            pass

        assert store.usage
        for event in store.usage:
            assert KEY not in json.dumps(event.model_dump(mode="json"), default=str)
