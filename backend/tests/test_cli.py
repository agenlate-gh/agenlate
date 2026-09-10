"""The command-line runner. Offline: no provider, no database."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agenlate.cli import EXAMPLE, _rehearsal, build_parser, load_room, main


@pytest.fixture
def agents_file(tmp_path: Path) -> Path:
    path = tmp_path / "agents.json"
    path.write_text(json.dumps(EXAMPLE), encoding="utf-8")
    return path


class TestLoadingAgents:
    def test_loads_the_example_file(self, agents_file: Path) -> None:
        room = load_room(agents_file, None)

        assert len(room.agents) == 3
        assert [a.name for a in room.agents] == ["Researcher", "Writer", "Critic"]

    def test_agent_ids_are_stable_and_distinct(self, agents_file: Path) -> None:
        """The Supervisor dispatches by id, so collisions would misroute work."""
        room = load_room(agents_file, None)

        ids = [a.id for a in room.agents]
        assert len(set(ids)) == len(ids)

    def test_a_bare_list_of_agents_is_accepted(self, tmp_path: Path) -> None:
        path = tmp_path / "agents.json"
        path.write_text(json.dumps(EXAMPLE["agents"]), encoding="utf-8")

        room = load_room(path, "an objective")

        assert len(room.agents) == 3

    def test_the_flag_overrides_the_file_objective(self, agents_file: Path) -> None:
        room = load_room(agents_file, "a different objective")

        assert room.room.objective == "a different objective"

    def test_per_agent_tools_are_carried_through(self, tmp_path: Path) -> None:
        path = tmp_path / "agents.json"
        path.write_text(
            json.dumps(
                {
                    "objective": "o",
                    "agents": [
                        {
                            "name": "N",
                            "role": "r",
                            "system_prompt": "p",
                            "enabled_tools": ["openrouter:web_search"],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        room = load_room(path, None)

        assert room.agents[0].enabled_tools == ["openrouter:web_search"]


class TestLoadingFailures:
    """Failures a person will actually hit, each naming what to do about it."""

    def test_a_missing_file_suggests_the_example_command(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit, match="example"):
            load_room(tmp_path / "nope.json", "o")

    def test_malformed_json_is_reported_as_such(self, tmp_path: Path) -> None:
        path = tmp_path / "agents.json"
        path.write_text("{not json", encoding="utf-8")

        with pytest.raises(SystemExit, match="not valid JSON"):
            load_room(path, "o")

    def test_an_empty_agent_list_is_refused(self, tmp_path: Path) -> None:
        path = tmp_path / "agents.json"
        path.write_text(json.dumps({"objective": "o", "agents": []}), encoding="utf-8")

        with pytest.raises(SystemExit, match="non-empty list"):
            load_room(path, None)

    def test_a_missing_objective_is_refused(self, tmp_path: Path) -> None:
        path = tmp_path / "agents.json"
        path.write_text(json.dumps({"agents": EXAMPLE["agents"]}), encoding="utf-8")

        with pytest.raises(SystemExit, match="objective is required"):
            load_room(path, None)

    def test_an_incomplete_agent_names_its_missing_fields(self, tmp_path: Path) -> None:
        path = tmp_path / "agents.json"
        path.write_text(
            json.dumps({"objective": "o", "agents": [{"name": "N"}]}), encoding="utf-8"
        )

        with pytest.raises(SystemExit, match="role"):
            load_room(path, None)


class TestRehearsal:
    def test_dispatches_to_every_agent_then_finishes(self, agents_file: Path) -> None:
        room = load_room(agents_file, None)

        script = _rehearsal(room)

        # One dispatch and one reply per agent, then the completion.
        assert len(script) == len(room.agents) * 2 + 1
        assert json.loads(script[-1])["action"] == "complete"

    def test_every_dispatch_names_a_real_agent(self, agents_file: Path) -> None:
        """A rehearsal that dispatched to an invented id would exercise the
        repair loop instead of the happy path."""
        room = load_room(agents_file, None)
        valid = {a.id for a in room.agents}

        for entry in _rehearsal(room):
            try:
                decision = json.loads(entry)
            except ValueError:
                continue
            if decision.get("action") == "dispatch":
                assert decision["agent_id"] in valid


class TestDryRun:
    """main() owns its own event loop, so these are deliberately synchronous."""

    def test_a_full_run_completes_without_a_provider(
        self, agents_file: Path, capsys
    ) -> None:
        """The whole loop — supervisor, guard, persistence, accounting — with
        only the provider replaced."""
        exit_code = main(["run", "--agents", str(agents_file), "--dry-run"])

        output = capsys.readouterr().out
        assert exit_code == 0
        assert "completed" in output
        assert "SUPERVISOR" in output
        assert "RESEARCHER" in output

    def test_the_summary_reports_the_accounting(
        self, agents_file: Path, capsys
    ) -> None:
        main(["run", "--agents", str(agents_file), "--dry-run"])

        output = capsys.readouterr().out
        assert "turns" in output
        assert "tokens" in output
        assert "reported cost" in output
        assert "tool steps" in output

    def test_limits_are_honoured(self, agents_file: Path, capsys) -> None:
        main(["run", "--agents", str(agents_file), "--dry-run", "--max-turns", "1"])

        assert "max turns" in capsys.readouterr().out.lower().replace("_", " ")


class TestArguments:
    def test_example_prints_a_loadable_file(self, capsys, tmp_path: Path) -> None:
        assert main(["example"]) == 0

        path = tmp_path / "agents.json"
        path.write_text(capsys.readouterr().out, encoding="utf-8")
        assert len(load_room(path, None).agents) == 3

    def test_a_real_run_without_a_key_says_what_to_do(
        self, agents_file: Path, monkeypatch
    ) -> None:
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.setattr("agenlate.cli._key_from_env_file", lambda: None)

        with pytest.raises(SystemExit, match="OPENROUTER_API_KEY"):
            main(["run", "--agents", str(agents_file)])

    def test_a_command_is_required(self) -> None:
        with pytest.raises(SystemExit):
            build_parser().parse_args([])

    def test_the_spend_cap_defaults_low(self) -> None:
        """This spends the operator's own credit; a surprising default here is
        a surprising bill."""
        args = build_parser().parse_args(["run"])

        assert args.spend_cap <= 1.0
