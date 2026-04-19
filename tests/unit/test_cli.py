"""Unit tests for the CLI entrypoint."""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import ClassVar
from unittest.mock import MagicMock, patch

import pytest
from campaignnarrator.cli import (
    _DEFAULT_NARRATOR_PERSONALITY,
    ApplicationFactory,
    _ApplicationGraph,
    _build_application_graph,
    main,
)

# ---------------------------------------------------------------------------
# Shared fakes
# ---------------------------------------------------------------------------


class _FakeRunResult:
    def __init__(self, *, output_text: str, completed: bool) -> None:
        self.output_text = output_text
        self.completed = completed


class _FakeApplicationOrchestrator:
    def __init__(self, *, encounter_orchestrator: object) -> None:
        self.encounter_orchestrator = encounter_orchestrator
        self.encounter_id: str | None = None

    def run_encounter(self, *, encounter_id: str) -> _FakeRunResult:
        self.encounter_id = encounter_id
        return _FakeRunResult(output_text="Encounter output\n", completed=True)


class _FakeGameOrchestrator:
    def __init__(self) -> None:
        self.run_called = False

    def run(self) -> None:
        self.run_called = True


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
    def __init__(
        self,
        *,
        adapter: object,
        personality: str,
        memory_repository: object = None,
    ) -> None:
        self.adapter = adapter
        self._adapter = adapter  # mirrors real NarratorAgent for wiring assertions
        self.personality = personality
        self.memory_repository = memory_repository


class _FakeEncounterOrchestrator:
    def __init__(
        self,
        *,
        repositories: object,
        agents: object,
        tools: object,
        io: object,
        adapter: object | None = None,
    ) -> None:
        self.repositories = repositories
        self.agents = agents
        self.tools = tools
        self.io = io
        self.adapter = adapter


# ---------------------------------------------------------------------------
# CLI behaviour tests
# ---------------------------------------------------------------------------


def test_cli_uses_stdin_stdout_loop(monkeypatch, tmp_path: Path) -> None:
    """The CLI should wire stdin/stdout through _TerminalIO and call run_encounter."""

    fake_app_orch = _FakeApplicationOrchestrator(encounter_orchestrator=object())
    fake_game_orch = _FakeGameOrchestrator()
    builder_calls: list[Path] = []

    def _fake_build(
        data_root: Path, stdin: object, stdout: object
    ) -> _ApplicationGraph:
        builder_calls.append(data_root)
        return _ApplicationGraph(
            game_orchestrator=fake_game_orch,
            application_orchestrator=fake_app_orch,
        )

    monkeypatch.setattr(
        "campaignnarrator.cli._build_application_graph",
        _fake_build,
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
    assert fake_app_orch.encounter_id == "goblin-camp"
    assert stdout.getvalue() == "Encounter output\n"


def test_cli_routes_to_game_orchestrator_when_no_encounter_id(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """When no --encounter-id is given, main() calls game_orchestrator.run()."""

    fake_app_orch = _FakeApplicationOrchestrator(encounter_orchestrator=object())
    fake_game_orch = _FakeGameOrchestrator()

    monkeypatch.setattr(
        "campaignnarrator.cli._build_application_graph",
        lambda _data_root, stdin, stdout: _ApplicationGraph(
            game_orchestrator=fake_game_orch,
            application_orchestrator=fake_app_orch,
        ),
    )

    exit_code = main(
        ["--data-root", str(tmp_path)],
        stdin=StringIO("exit\n"),
        stdout=StringIO(),
    )

    assert exit_code == 0
    assert fake_game_orch.run_called is True
    assert fake_app_orch.encounter_id is None


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
    monkeypatch.setattr(
        "campaignnarrator.cli.StartupInterpreterAgent", lambda **_kw: object()
    )
    monkeypatch.setattr(
        "campaignnarrator.cli.CharacterInterpreterAgent", lambda **_kw: object()
    )
    monkeypatch.setattr("campaignnarrator.cli.BackstoryAgent", lambda **_kw: object())
    monkeypatch.setattr(
        "campaignnarrator.cli.CampaignGeneratorAgent", lambda **_kw: object()
    )
    monkeypatch.setattr(
        "campaignnarrator.cli.ModuleGeneratorAgent", lambda **_kw: object()
    )
    monkeypatch.setattr(
        "campaignnarrator.cli.CampaignRepository", lambda _path: object()
    )
    monkeypatch.setattr("campaignnarrator.cli.ModuleRepository", lambda _path: object())
    monkeypatch.setattr(
        "campaignnarrator.cli.CharacterTemplateRepository", lambda _path: object()
    )
    monkeypatch.setattr(
        "campaignnarrator.cli.CharacterCreationOrchestrator", lambda **_kw: object()
    )
    monkeypatch.setattr(
        "campaignnarrator.cli.ModuleOrchestrator", lambda **_kw: object()
    )
    monkeypatch.setattr(
        "campaignnarrator.cli.CampaignCreationOrchestrator", lambda **_kw: object()
    )
    monkeypatch.setattr(
        "campaignnarrator.cli.StartupOrchestrator", lambda **_kw: object()
    )

    _build_application_graph(tmp_path, stdin=StringIO(), stdout=StringIO())

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
    monkeypatch.setattr(
        "campaignnarrator.cli.StartupInterpreterAgent", lambda **_kw: object()
    )
    monkeypatch.setattr(
        "campaignnarrator.cli.CharacterInterpreterAgent", lambda **_kw: object()
    )
    monkeypatch.setattr("campaignnarrator.cli.BackstoryAgent", lambda **_kw: object())
    monkeypatch.setattr(
        "campaignnarrator.cli.CampaignGeneratorAgent", lambda **_kw: object()
    )
    monkeypatch.setattr(
        "campaignnarrator.cli.ModuleGeneratorAgent", lambda **_kw: object()
    )
    monkeypatch.setattr(
        "campaignnarrator.cli.CampaignRepository", lambda _path: object()
    )
    monkeypatch.setattr("campaignnarrator.cli.ModuleRepository", lambda _path: object())
    monkeypatch.setattr(
        "campaignnarrator.cli.CharacterTemplateRepository", lambda _path: object()
    )
    monkeypatch.setattr(
        "campaignnarrator.cli.CharacterCreationOrchestrator", lambda **_kw: object()
    )
    monkeypatch.setattr(
        "campaignnarrator.cli.ModuleOrchestrator", lambda **_kw: object()
    )
    monkeypatch.setattr(
        "campaignnarrator.cli.CampaignCreationOrchestrator", lambda **_kw: object()
    )
    monkeypatch.setattr(
        "campaignnarrator.cli.StartupOrchestrator", lambda **_kw: object()
    )

    result = _build_application_graph(tmp_path, stdin=StringIO(), stdout=StringIO())

    assert isinstance(result, _ApplicationGraph)
    assert isinstance(result.application_orchestrator, _FakeApplicationOrchestrator)
    enc = result.application_orchestrator.encounter_orchestrator
    assert isinstance(enc, _FakeEncounterOrchestrator)
    assert isinstance(enc.agents.rules, _FakeRulesAgent)
    assert isinstance(enc.agents.narrator, _FakeNarratorAgent)
    assert enc.agents.rules.adapter is adapter
    assert enc.agents.narrator.adapter is adapter
    assert enc.agents.narrator.personality == _DEFAULT_NARRATOR_PERSONALITY
    assert enc.adapter is adapter
    state_repo = _FakeStateRepository.instances[0]
    assert isinstance(state_repo.actor_repo, _FakeActorRepository)
    assert isinstance(state_repo.encounter_repo, _FakeEncounterRepository)
    assert state_repo.compendium is compendium_instance


# ---------------------------------------------------------------------------
# New GameOrchestrator routing tests
# ---------------------------------------------------------------------------


def test_main_without_encounter_id_calls_game_orchestrator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When --encounter-id is omitted, GameOrchestrator.run() is called."""
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")

    mock_game_orch = MagicMock()
    mock_app_orch = MagicMock()

    with patch(
        "campaignnarrator.cli._build_application_graph",
        return_value=MagicMock(
            game_orchestrator=mock_game_orch,
            application_orchestrator=mock_app_orch,
        ),
    ):
        main(["--data-root", str(tmp_path)])

    mock_game_orch.run.assert_called_once()
    mock_app_orch.run_encounter.assert_not_called()


def test_main_with_encounter_id_calls_application_orchestrator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When --encounter-id is provided, legacy ApplicationOrchestrator is used."""
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")

    mock_game_orch = MagicMock()
    mock_app_orch = MagicMock()
    mock_app_orch.run_encounter.return_value = MagicMock(output_text="done\n")

    with patch(
        "campaignnarrator.cli._build_application_graph",
        return_value=MagicMock(
            game_orchestrator=mock_game_orch,
            application_orchestrator=mock_app_orch,
        ),
    ):
        main(["--data-root", str(tmp_path), "--encounter-id", "goblin-camp"])

    mock_app_orch.run_encounter.assert_called_once_with(encounter_id="goblin-camp")
    mock_game_orch.run.assert_not_called()


# ---------------------------------------------------------------------------
# ApplicationFactory tests
# ---------------------------------------------------------------------------


def test_application_factory_exists() -> None:
    assert ApplicationFactory is not None


def _noop_agent(**_kw: object) -> object:
    return object()


def _noop_repo(_path: object) -> object:
    return object()


def _noop_repo_kw(**_kw: object) -> object:
    return object()


def test_application_factory_build_returns_application_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ApplicationFactory.build() returns a valid _ApplicationGraph."""
    cli_ns = "campaignnarrator.cli"
    monkeypatch.setattr(f"{cli_ns}.PydanticAIAdapter.from_env", object)
    monkeypatch.setattr(f"{cli_ns}.RulesAgent", _FakeRulesAgent)
    monkeypatch.setattr(f"{cli_ns}.NarratorAgent", _FakeNarratorAgent)
    monkeypatch.setattr(f"{cli_ns}.EncounterOrchestrator", _FakeEncounterOrchestrator)
    monkeypatch.setattr(
        f"{cli_ns}.ApplicationOrchestrator", _FakeApplicationOrchestrator
    )
    monkeypatch.setattr(f"{cli_ns}.StartupInterpreterAgent", _noop_agent)
    monkeypatch.setattr(f"{cli_ns}.CharacterInterpreterAgent", _noop_agent)
    monkeypatch.setattr(f"{cli_ns}.BackstoryAgent", _noop_agent)
    monkeypatch.setattr(f"{cli_ns}.CampaignGeneratorAgent", _noop_agent)
    monkeypatch.setattr(f"{cli_ns}.ModuleGeneratorAgent", _noop_agent)
    monkeypatch.setattr(f"{cli_ns}.ActorRepository", _noop_repo)
    monkeypatch.setattr(f"{cli_ns}.EncounterRepository", _noop_repo)
    monkeypatch.setattr(f"{cli_ns}.CampaignRepository", _noop_repo)
    monkeypatch.setattr(f"{cli_ns}.ModuleRepository", _noop_repo)
    monkeypatch.setattr(f"{cli_ns}.RulesRepository", _noop_repo)
    monkeypatch.setattr(f"{cli_ns}.CompendiumRepository", _noop_repo)
    monkeypatch.setattr(f"{cli_ns}.MemoryRepository", _noop_repo)
    monkeypatch.setattr(f"{cli_ns}.CharacterTemplateRepository", _noop_repo)
    monkeypatch.setattr(f"{cli_ns}.StateRepository", _noop_repo_kw)
    monkeypatch.setattr(f"{cli_ns}.CharacterCreationOrchestrator", _noop_repo_kw)
    monkeypatch.setattr(f"{cli_ns}.ModuleOrchestrator", _noop_repo_kw)
    monkeypatch.setattr(f"{cli_ns}.CampaignCreationOrchestrator", _noop_repo_kw)
    monkeypatch.setattr(f"{cli_ns}.StartupOrchestrator", _noop_repo_kw)

    factory = ApplicationFactory(tmp_path, StringIO(), StringIO())
    graph = factory.build()
    assert graph is not None
    assert graph.game_orchestrator is not None
    assert graph.application_orchestrator is not None
