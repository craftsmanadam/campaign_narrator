"""Unit tests for the CLI entrypoint."""

from __future__ import annotations

from collections.abc import Iterable
from io import StringIO
from pathlib import Path

import pytest
from campaignnarrator.cli import _build_application_graph, main


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


def test_build_application_graph_wires_real_dependencies(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """The application graph should pass the shared adapter through the real wiring."""

    captured: dict[str, object] = {}
    adapter = object()
    state_repository = object()
    rules_repository = object()
    compendium_repository = object()
    memory_repository = object()
    rules_paths: list[Path] = []
    compendium_paths: list[Path] = []
    memory_paths: list[Path] = []

    def roll_dice(_expr: str) -> int:
        return 7

    def _fake_from_env() -> object:
        return adapter

    def _fake_rules_repository(path: Path) -> object:
        rules_paths.append(path)
        return rules_repository

    def _fake_compendium_repository(path: Path) -> object:
        compendium_paths.append(path)
        return compendium_repository

    def _fake_memory_repository(path: Path) -> object:
        memory_paths.append(path)
        return memory_repository

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
            captured["rules_agent"] = self

    class _FakeNarratorAgent:
        def __init__(self, *, adapter: object) -> None:
            self.adapter = adapter
            captured["narrator_agent"] = self

    class _FakeCampaignOrchestrator:
        def __init__(self, **kwargs: object) -> None:
            self.state_repository = kwargs["state_repository"]
            self.rules_agent = kwargs["rules_agent"]
            self.narrator_agent = kwargs["narrator_agent"]
            self.roll_dice = kwargs["roll_dice"]
            self.decision_adapter = kwargs["decision_adapter"]
            self.memory_repository = kwargs["memory_repository"]
            captured["orchestrator"] = self

    monkeypatch.setattr(
        "campaignnarrator.cli.OpenAIAdapter.from_env",
        _fake_from_env,
    )
    monkeypatch.setattr(
        "campaignnarrator.cli.StateRepository.from_default_encounter",
        lambda: state_repository,
    )
    monkeypatch.setattr(
        "campaignnarrator.cli.RulesRepository",
        _fake_rules_repository,
    )
    monkeypatch.setattr(
        "campaignnarrator.cli.CompendiumRepository",
        _fake_compendium_repository,
    )
    monkeypatch.setattr(
        "campaignnarrator.cli.MemoryRepository",
        _fake_memory_repository,
    )
    monkeypatch.setattr("campaignnarrator.cli.RulesAgent", _FakeRulesAgent)
    monkeypatch.setattr("campaignnarrator.cli.NarratorAgent", _FakeNarratorAgent)
    monkeypatch.setattr(
        "campaignnarrator.cli.CampaignOrchestrator",
        _FakeCampaignOrchestrator,
    )
    monkeypatch.setattr("campaignnarrator.cli.roll_dice", roll_dice)

    result = _build_application_graph(tmp_path)

    rules_agent = captured["rules_agent"]
    narrator_agent = captured["narrator_agent"]
    orchestrator = captured["orchestrator"]
    assert rules_agent.adapter == adapter
    assert rules_agent.rules_repository == rules_repository
    assert rules_agent.compendium_repository == compendium_repository
    assert narrator_agent.adapter == adapter
    assert rules_paths == [tmp_path / "rules"]
    assert compendium_paths == [tmp_path / "compendium"]
    assert memory_paths == [tmp_path / "memory"]
    assert orchestrator.state_repository == state_repository
    assert orchestrator.rules_agent == rules_agent
    assert orchestrator.narrator_agent == narrator_agent
    assert orchestrator.roll_dice == roll_dice
    assert orchestrator.decision_adapter == adapter
    assert orchestrator.memory_repository == memory_repository
    assert isinstance(result, _FakeCampaignOrchestrator)
