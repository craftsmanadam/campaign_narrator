"""Unit tests for the CLI entrypoint."""

from __future__ import annotations

from collections.abc import Iterable
from io import StringIO
from pathlib import Path
from typing import ClassVar

import pytest
from campaignnarrator.cli import _build_application_graph, main

# ---------------------------------------------------------------------------
# Shared fakes
# ---------------------------------------------------------------------------


class _FakeRunResult:
    def __init__(self, *, output_text: str, completed: bool) -> None:
        self.output_text = output_text
        self.completed = completed


class _FakeOrchestrator:
    def __init__(self) -> None:
        self.encounter_id: str | None = None
        self.player_inputs: tuple[str, ...] | None = None

    def run_encounter(
        self,
        *,
        encounter_id: str,
        player_inputs: Iterable[str],
    ) -> _FakeRunResult:
        self.encounter_id = encounter_id
        self.player_inputs = tuple(player_inputs)
        return _FakeRunResult(output_text="Encounter output\n", completed=True)


# ---------------------------------------------------------------------------
# Fakes for wiring test
# ---------------------------------------------------------------------------


class _FakeActorRepository:
    captured_paths: ClassVar[list[Path]] = []

    def __init__(self, path: Path) -> None:
        _FakeActorRepository.captured_paths.append(path)


class _FakeEncounterRepository:
    captured_paths: ClassVar[list[Path]] = []

    def __init__(self, path: Path) -> None:
        _FakeEncounterRepository.captured_paths.append(path)


class _FakeStateRepository:
    instances: ClassVar[list[_FakeStateRepository]] = []

    def __init__(
        self,
        *,
        actor_repo: object,
        encounter_repo: object,
        compendium: object = None,
    ) -> None:
        self.actor_repo = actor_repo
        self.encounter_repo = encounter_repo
        self.compendium = compendium
        _FakeStateRepository.instances.append(self)


class _FakeRulesAgent:
    def __init__(
        self,
        *,
        adapter: object,
        rules_repository: object | None = None,
        compendium_repository: object | None = None,
    ) -> None:
        self.adapter = adapter
        self.rules_repository = rules_repository
        self.compendium_repository = compendium_repository


class _FakeNarratorAgent:
    def __init__(self, *, adapter: object) -> None:
        self.adapter = adapter


class _FakeEncounterOrchestrator:
    def __init__(self, **kwargs: object) -> None:
        self.state_repository = kwargs["state_repository"]
        self.rules_agent = kwargs["rules_agent"]
        self.narrator_agent = kwargs["narrator_agent"]
        self.roll_dice = kwargs["roll_dice"]
        self.decision_adapter = kwargs["decision_adapter"]
        self.memory_repository = kwargs["memory_repository"]


class _FakeApplicationOrchestrator:
    def __init__(self, *, encounter_orchestrator: object) -> None:
        self.encounter_orchestrator = encounter_orchestrator


# ---------------------------------------------------------------------------
# CLI behaviour tests
# ---------------------------------------------------------------------------


def test_cli_uses_stdin_stdout_loop(monkeypatch, tmp_path: Path) -> None:
    """The CLI should stream player input into the encounter loop and print output."""

    fake_orchestrator = _FakeOrchestrator()
    builder_calls: list[Path] = []

    def _build_application_graph(data_root: Path) -> _FakeOrchestrator:
        builder_calls.append(data_root)
        return fake_orchestrator

    monkeypatch.setattr(
        "campaignnarrator.cli._build_application_graph",
        _build_application_graph,
    )

    stdout = StringIO()
    exit_code = main(
        [
            "--data-root",
            str(tmp_path),
            "--encounter-id",
            "goblin-camp",
        ],
        stdin=StringIO("status\nexit\n"),
        stdout=stdout,
    )

    assert exit_code == 0
    assert builder_calls == [tmp_path]
    assert fake_orchestrator.encounter_id == "goblin-camp"
    assert fake_orchestrator.player_inputs == ("status\n", "exit\n")
    assert stdout.getvalue() == "Encounter output\n"


def test_cli_defaults_encounter_id_to_goblin_camp(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """The CLI should use the goblin camp encounter when no override is given."""

    fake_orchestrator = _FakeOrchestrator()

    monkeypatch.setattr(
        "campaignnarrator.cli._build_application_graph",
        lambda _data_root: fake_orchestrator,
    )

    exit_code = main(
        ["--data-root", str(tmp_path)],
        stdin=StringIO("exit\n"),
        stdout=StringIO(),
    )

    assert exit_code == 0
    assert fake_orchestrator.encounter_id == "goblin-camp"


def test_cli_rejects_legacy_input_flag(tmp_path: Path) -> None:
    """The CLI should no longer accept the legacy --input flag."""

    with pytest.raises(SystemExit):
        main(["--data-root", str(tmp_path), "--input", "I drink a potion"])


# ---------------------------------------------------------------------------
# Wiring tests
# ---------------------------------------------------------------------------


def test_build_application_graph_wires_repository_paths(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """The application graph should build repositories from data-root sub-paths."""

    rules_paths: list[Path] = []
    compendium_paths: list[Path] = []
    memory_paths: list[Path] = []
    _FakeActorRepository.captured_paths.clear()
    _FakeEncounterRepository.captured_paths.clear()
    _FakeStateRepository.instances.clear()

    monkeypatch.setattr("campaignnarrator.cli.PydanticAIAdapter.from_env", object)
    monkeypatch.setattr("campaignnarrator.cli.ActorRepository", _FakeActorRepository)
    monkeypatch.setattr(
        "campaignnarrator.cli.EncounterRepository", _FakeEncounterRepository
    )
    monkeypatch.setattr("campaignnarrator.cli.StateRepository", _FakeStateRepository)
    monkeypatch.setattr(
        "campaignnarrator.cli.RulesRepository",
        lambda path: rules_paths.append(path) or object(),
    )
    monkeypatch.setattr(
        "campaignnarrator.cli.CompendiumRepository",
        lambda path: compendium_paths.append(path) or object(),
    )
    monkeypatch.setattr(
        "campaignnarrator.cli.MemoryRepository",
        lambda path: memory_paths.append(path) or object(),
    )
    monkeypatch.setattr("campaignnarrator.cli.RulesAgent", _FakeRulesAgent)
    monkeypatch.setattr("campaignnarrator.cli.NarratorAgent", _FakeNarratorAgent)
    monkeypatch.setattr(
        "campaignnarrator.cli.EncounterOrchestrator", _FakeEncounterOrchestrator
    )
    monkeypatch.setattr(
        "campaignnarrator.cli.ApplicationOrchestrator", _FakeApplicationOrchestrator
    )

    _build_application_graph(tmp_path)

    assert _FakeActorRepository.captured_paths == [tmp_path / "state"]
    assert _FakeEncounterRepository.captured_paths == [tmp_path / "state"]
    assert rules_paths == [tmp_path / "rules"]
    assert compendium_paths == [tmp_path / "compendium"]
    assert memory_paths == [tmp_path / "memory"]


def test_build_application_graph_wires_agents_and_orchestrators(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """The application graph should pass shared adapter through all components."""

    adapter = object()
    _FakeActorRepository.captured_paths.clear()
    _FakeEncounterRepository.captured_paths.clear()
    _FakeStateRepository.instances.clear()

    monkeypatch.setattr(
        "campaignnarrator.cli.PydanticAIAdapter.from_env", lambda: adapter
    )
    monkeypatch.setattr("campaignnarrator.cli.ActorRepository", _FakeActorRepository)
    monkeypatch.setattr(
        "campaignnarrator.cli.EncounterRepository", _FakeEncounterRepository
    )
    monkeypatch.setattr("campaignnarrator.cli.StateRepository", _FakeStateRepository)
    monkeypatch.setattr("campaignnarrator.cli.RulesRepository", lambda _path: object())
    compendium_instance = object()
    monkeypatch.setattr(
        "campaignnarrator.cli.CompendiumRepository", lambda _path: compendium_instance
    )
    monkeypatch.setattr("campaignnarrator.cli.MemoryRepository", lambda _path: object())
    monkeypatch.setattr("campaignnarrator.cli.RulesAgent", _FakeRulesAgent)
    monkeypatch.setattr("campaignnarrator.cli.NarratorAgent", _FakeNarratorAgent)
    monkeypatch.setattr(
        "campaignnarrator.cli.EncounterOrchestrator", _FakeEncounterOrchestrator
    )
    monkeypatch.setattr(
        "campaignnarrator.cli.ApplicationOrchestrator", _FakeApplicationOrchestrator
    )

    result = _build_application_graph(tmp_path)

    assert isinstance(result, _FakeApplicationOrchestrator)
    enc = result.encounter_orchestrator
    assert isinstance(enc, _FakeEncounterOrchestrator)
    assert isinstance(enc.rules_agent, _FakeRulesAgent)
    assert isinstance(enc.narrator_agent, _FakeNarratorAgent)
    assert enc.rules_agent.adapter is adapter
    assert enc.narrator_agent.adapter is adapter
    assert enc.decision_adapter is adapter
    state_repo = _FakeStateRepository.instances[0]
    assert isinstance(state_repo.actor_repo, _FakeActorRepository)
    assert isinstance(state_repo.encounter_repo, _FakeEncounterRepository)
    assert state_repo.compendium is compendium_instance
