"""Unit tests for the CLI entrypoint."""

from __future__ import annotations

import contextlib
import signal
from io import StringIO
from pathlib import Path
from typing import ClassVar
from unittest.mock import MagicMock, patch

import pytest
from campaignnarrator.adapters.embedding_adapter import (
    OllamaEmbeddingAdapter,
    StubEmbeddingAdapter,
)
from campaignnarrator.application_factory import ApplicationFactory, ApplicationGraph
from campaignnarrator.cli import (
    _build_embedding_adapter,
    main,
)
from campaignnarrator.settings import Settings
from campaignnarrator.terminal_io import TerminalIO

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
        self.save_state_called = False

    def run(self) -> None:
        self.run_called = True

    def save_state(self) -> None:
        self.save_state_called = True


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
        io: object,
        adapter: object | None = None,
    ) -> None:
        self.repositories = repositories
        self.agents = agents
        self.io = io
        self.adapter = adapter


# ---------------------------------------------------------------------------
# CLI behaviour tests
# ---------------------------------------------------------------------------


def test_cli_routes_to_game_orchestrator_when_no_encounter_id(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """When no --encounter-id is given, main() calls game_orchestrator.run()."""

    fake_game_orch = _FakeGameOrchestrator()

    monkeypatch.setattr(
        "campaignnarrator.cli._build_application_graph",
        lambda _data_root, stdin, stdout: ApplicationGraph(
            game_orchestrator=fake_game_orch,
        ),
    )

    exit_code = main(
        ["--data-root", str(tmp_path)],
        stdin=StringIO("exit\n"),
        stdout=StringIO(),
    )

    assert exit_code == 0
    assert fake_game_orch.run_called is True


def test_cli_rejects_legacy_input_flag(tmp_path: Path) -> None:
    """The CLI should no longer accept the legacy --input flag."""

    with pytest.raises(SystemExit):
        main(["--data-root", str(tmp_path), "--input", "I drink a potion"])


def test_main_uses_settings_data_root_as_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--data-root is optional; omitting it uses DATA_ROOT from env (via Settings)."""
    monkeypatch.setenv("DATA_ROOT", "tmp/test_store")
    captured: list[Path] = []

    def _fake_build(data_root: Path, stdin: object, stdout: object) -> ApplicationGraph:
        captured.append(data_root)
        return ApplicationGraph(game_orchestrator=_FakeGameOrchestrator())

    monkeypatch.setattr(
        "campaignnarrator.cli._build_application_graph",
        _fake_build,
    )

    exit_code = main([], stdin=StringIO(), stdout=StringIO())

    assert exit_code == 0
    assert captured == [Path("tmp/test_store")]


def test_main_uses_settings_default_data_root_when_env_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When DATA_ROOT is not set, --data-root defaults to Settings field default."""
    monkeypatch.delenv("DATA_ROOT", raising=False)
    captured: list[Path] = []

    def _fake_build(data_root: Path, stdin: object, stdout: object) -> ApplicationGraph:
        captured.append(data_root)
        return ApplicationGraph(game_orchestrator=_FakeGameOrchestrator())

    monkeypatch.setattr(
        "campaignnarrator.cli._build_application_graph",
        _fake_build,
    )

    exit_code = main([], stdin=StringIO(), stdout=StringIO())

    assert exit_code == 0
    assert captured == [Path("var/data_store")]


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

    af_ns = "campaignnarrator.application_factory"
    monkeypatch.setattr(f"{af_ns}.PydanticAIAdapter.from_env", object)
    monkeypatch.setattr(f"{af_ns}.ActorRepository", _FakeActorRepository)
    monkeypatch.setattr(f"{af_ns}.EncounterRepository", _FakeEncounterRepository)
    monkeypatch.setattr(f"{af_ns}.StateRepository", _FakeStateRepository)
    monkeypatch.setattr(
        f"{af_ns}.RulesRepository",
        lambda path: rules_paths.append(path) or object(),
    )
    monkeypatch.setattr(
        f"{af_ns}.CompendiumRepository",
        lambda path: compendium_paths.append(path) or object(),
    )
    monkeypatch.setattr(
        f"{af_ns}.MemoryRepository",
        lambda path, **_kw: memory_paths.append(path) or object(),
    )
    monkeypatch.setattr(f"{af_ns}.RulesAgent", _FakeRulesAgent)
    monkeypatch.setattr(f"{af_ns}.NarratorAgent", _FakeNarratorAgent)
    monkeypatch.setattr(f"{af_ns}.EncounterOrchestrator", _FakeEncounterOrchestrator)
    monkeypatch.setattr(f"{af_ns}.StartupInterpreterAgent", lambda **_kw: object())
    monkeypatch.setattr(f"{af_ns}.BackstoryAgent", lambda **_kw: object())
    monkeypatch.setattr(f"{af_ns}.CampaignGeneratorAgent", lambda **_kw: object())
    monkeypatch.setattr(f"{af_ns}.ModuleGeneratorAgent", lambda **_kw: object())
    monkeypatch.setattr(f"{af_ns}.CampaignRepository", lambda _path: object())
    monkeypatch.setattr(f"{af_ns}.ModuleRepository", lambda _path: object())
    monkeypatch.setattr(f"{af_ns}.CharacterTemplateRepository", lambda _path: object())
    monkeypatch.setattr(
        f"{af_ns}.CharacterCreationOrchestrator", lambda **_kw: object()
    )
    monkeypatch.setattr(f"{af_ns}.EncounterPlannerAgent", lambda **_kw: object())
    monkeypatch.setattr(f"{af_ns}.EncounterPlannerOrchestrator", lambda **_kw: object())
    monkeypatch.setattr(f"{af_ns}.ModuleOrchestrator", lambda **_kw: object())
    monkeypatch.setattr(f"{af_ns}.CampaignCreationOrchestrator", lambda **_kw: object())
    monkeypatch.setattr(f"{af_ns}.StartupOrchestrator", lambda **_kw: object())

    ApplicationFactory(tmp_path, stdin=StringIO(), stdout=StringIO()).build()

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

    af_ns = "campaignnarrator.application_factory"
    monkeypatch.setattr(f"{af_ns}.PydanticAIAdapter.from_env", lambda: adapter)
    monkeypatch.setattr(f"{af_ns}.ActorRepository", _FakeActorRepository)
    monkeypatch.setattr(f"{af_ns}.EncounterRepository", _FakeEncounterRepository)
    monkeypatch.setattr(f"{af_ns}.StateRepository", _FakeStateRepository)
    monkeypatch.setattr(f"{af_ns}.RulesRepository", lambda _path: object())
    compendium_instance = object()
    monkeypatch.setattr(
        f"{af_ns}.CompendiumRepository", lambda _path: compendium_instance
    )
    monkeypatch.setattr(f"{af_ns}.MemoryRepository", lambda _path, **_kw: object())
    monkeypatch.setattr(f"{af_ns}.RulesAgent", _FakeRulesAgent)
    monkeypatch.setattr(f"{af_ns}.NarratorAgent", _FakeNarratorAgent)
    monkeypatch.setattr(f"{af_ns}.EncounterOrchestrator", _FakeEncounterOrchestrator)
    monkeypatch.setattr(f"{af_ns}.StartupInterpreterAgent", lambda **_kw: object())
    monkeypatch.setattr(f"{af_ns}.BackstoryAgent", lambda **_kw: object())
    monkeypatch.setattr(f"{af_ns}.CampaignGeneratorAgent", lambda **_kw: object())
    monkeypatch.setattr(f"{af_ns}.ModuleGeneratorAgent", lambda **_kw: object())
    monkeypatch.setattr(f"{af_ns}.CampaignRepository", lambda _path: object())
    monkeypatch.setattr(f"{af_ns}.ModuleRepository", lambda _path: object())
    monkeypatch.setattr(f"{af_ns}.CharacterTemplateRepository", lambda _path: object())
    monkeypatch.setattr(
        f"{af_ns}.CharacterCreationOrchestrator", lambda **_kw: object()
    )
    monkeypatch.setattr(f"{af_ns}.EncounterPlannerAgent", lambda **_kw: object())
    monkeypatch.setattr(f"{af_ns}.EncounterPlannerOrchestrator", lambda **_kw: object())
    monkeypatch.setattr(f"{af_ns}.ModuleOrchestrator", lambda **_kw: object())
    monkeypatch.setattr(f"{af_ns}.CampaignCreationOrchestrator", lambda **_kw: object())
    monkeypatch.setattr(f"{af_ns}.StartupOrchestrator", lambda **_kw: object())

    result = ApplicationFactory(tmp_path, stdin=StringIO(), stdout=StringIO()).build()

    assert isinstance(result, ApplicationGraph)
    assert result.game_orchestrator is not None
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
    """When no --encounter-id is given, GameOrchestrator.run() is called."""
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")

    mock_game_orch = MagicMock()

    with patch(
        "campaignnarrator.cli._build_application_graph",
        return_value=MagicMock(game_orchestrator=mock_game_orch),
    ):
        main(["--data-root", str(tmp_path)])

    mock_game_orch.run.assert_called_once()


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


def _noop_repo_with_kw(_path: object, **_kw: object) -> object:
    return object()


def test_application_factory_build_returns_application_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ApplicationFactory.build() returns a valid ApplicationGraph."""
    af_ns = "campaignnarrator.application_factory"
    monkeypatch.setattr(f"{af_ns}.PydanticAIAdapter.from_env", object)
    monkeypatch.setattr(f"{af_ns}.RulesAgent", _FakeRulesAgent)
    monkeypatch.setattr(f"{af_ns}.NarratorAgent", _FakeNarratorAgent)
    monkeypatch.setattr(f"{af_ns}.EncounterOrchestrator", _FakeEncounterOrchestrator)
    monkeypatch.setattr(f"{af_ns}.StartupInterpreterAgent", _noop_agent)
    monkeypatch.setattr(f"{af_ns}.BackstoryAgent", _noop_agent)
    monkeypatch.setattr(f"{af_ns}.CampaignGeneratorAgent", _noop_agent)
    monkeypatch.setattr(f"{af_ns}.ModuleGeneratorAgent", _noop_agent)
    monkeypatch.setattr(f"{af_ns}.ActorRepository", _noop_repo)
    monkeypatch.setattr(f"{af_ns}.EncounterRepository", _noop_repo)
    monkeypatch.setattr(f"{af_ns}.CampaignRepository", _noop_repo)
    monkeypatch.setattr(f"{af_ns}.ModuleRepository", _noop_repo)
    monkeypatch.setattr(f"{af_ns}.RulesRepository", _noop_repo)
    monkeypatch.setattr(f"{af_ns}.CompendiumRepository", _noop_repo)
    monkeypatch.setattr(f"{af_ns}.MemoryRepository", _noop_repo_with_kw)
    monkeypatch.setattr(f"{af_ns}.CharacterTemplateRepository", _noop_repo)
    monkeypatch.setattr(f"{af_ns}.StateRepository", _noop_repo_kw)
    monkeypatch.setattr(f"{af_ns}.CharacterCreationOrchestrator", _noop_repo_kw)
    monkeypatch.setattr(f"{af_ns}.EncounterPlannerAgent", _noop_agent)
    monkeypatch.setattr(f"{af_ns}.EncounterPlannerOrchestrator", _noop_repo_kw)
    monkeypatch.setattr(f"{af_ns}.ModuleOrchestrator", _noop_repo_kw)
    monkeypatch.setattr(f"{af_ns}.CampaignCreationOrchestrator", _noop_repo_kw)
    monkeypatch.setattr(f"{af_ns}.StartupOrchestrator", _noop_repo_kw)

    factory = ApplicationFactory(tmp_path, StringIO(), StringIO())
    graph = factory.build()
    assert graph is not None
    assert graph.game_orchestrator is not None


# ---------------------------------------------------------------------------
# _build_embedding_adapter tests
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# TerminalIO tests
# ---------------------------------------------------------------------------


def test_terminal_io_prompt_strips_trailing_newline() -> None:
    """prompt() must strip a trailing LF so callers receive clean input."""
    io = TerminalIO(StringIO("hello\n"), StringIO())
    assert io.prompt("> ") == "hello"


def test_terminal_io_prompt_strips_trailing_carriage_return_newline() -> None:
    """prompt() strips CRLF from Windows-style copy-paste so no stray \\r remains."""
    io = TerminalIO(StringIO("hello\r\n"), StringIO())
    assert io.prompt("> ") == "hello"


def test_terminal_io_prompt_preserves_internal_whitespace() -> None:
    """prompt() must not strip leading/trailing spaces — only the line terminator."""
    io = TerminalIO(StringIO("  hello world  \n"), StringIO())
    assert io.prompt("> ") == "  hello world  "


def test_terminal_io_prompt_skips_blank_lines_and_returns_first_non_blank() -> None:
    """prompt() must silently discard blank lines and re-read until non-blank input."""
    io = TerminalIO(StringIO("\n\r\n   \nhello\n"), StringIO())
    assert io.prompt("> ") == "hello"


def test_terminal_io_prompt_skips_whitespace_only_lines() -> None:
    """prompt() must treat whitespace-only lines as blank and keep reading."""
    io = TerminalIO(StringIO("   \n\thello there\n"), StringIO())
    assert io.prompt("> ") == "\thello there"


def test_terminal_io_prompt_optional_returns_blank_immediately() -> None:
    """prompt_optional() must return blank input without looping."""
    io = TerminalIO(StringIO("\n"), StringIO())
    assert io.prompt_optional("> ") == ""


def test_terminal_io_prompt_optional_strips_line_terminators() -> None:
    """prompt_optional() must strip CRLF just like prompt()."""
    io = TerminalIO(StringIO("hello\r\n"), StringIO())
    assert io.prompt_optional("> ") == "hello"


def test_terminal_io_prompt_optional_returns_whitespace_only_input() -> None:
    """prompt_optional() must return whitespace-only input as-is (caller decides)."""
    io = TerminalIO(StringIO("   \n"), StringIO())
    assert io.prompt_optional("> ") == "   "


def test_terminal_io_prompt_multiline_collects_lines_until_blank() -> None:
    """prompt_multiline() joins lines until a blank line terminates input."""
    io = TerminalIO(StringIO("line one\nline two\n\n"), StringIO())
    assert io.prompt_multiline("> ") == "line one\nline two"


def test_terminal_io_prompt_multiline_single_line() -> None:
    """prompt_multiline() works with a single line followed by blank."""
    io = TerminalIO(StringIO("just one line\n\n"), StringIO())
    assert io.prompt_multiline("> ") == "just one line"


def test_terminal_io_prompt_multiline_stops_at_eof() -> None:
    """prompt_multiline() terminates cleanly at EOF without a trailing blank."""
    io = TerminalIO(StringIO("no trailing blank\n"), StringIO())
    assert io.prompt_multiline("> ") == "no trailing blank"


def test_build_embedding_adapter_returns_stub_when_provider_is_stub() -> None:
    settings = Settings(embedding_provider="stub")
    adapter = _build_embedding_adapter(settings)
    assert isinstance(adapter, StubEmbeddingAdapter)


def test_build_embedding_adapter_returns_ollama_when_provider_is_ollama() -> None:
    settings = Settings(
        embedding_provider="ollama",
        embedding_model="nomic-embed-text",
        embedding_base_url="http://localhost:11434",
    )
    adapter = _build_embedding_adapter(settings)
    assert isinstance(adapter, OllamaEmbeddingAdapter)


def test_build_embedding_adapter_ollama_uses_configured_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EMBEDDING_MODEL", "my-custom-model")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "ollama")
    settings = Settings()
    adapter = _build_embedding_adapter(settings)
    assert isinstance(adapter, OllamaEmbeddingAdapter)
    assert adapter._model == "my-custom-model"


# ---------------------------------------------------------------------------
# Signal handling tests
# ---------------------------------------------------------------------------


def test_sigterm_handler_calls_save_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SIGTERM handler must call game_orchestrator.save_state()."""
    captured_handler: dict[int, object] = {}

    def _fake_signal(signum: int, handler: object) -> None:
        captured_handler[signum] = handler

    monkeypatch.setattr(signal, "signal", _fake_signal)

    fake_game_orch = _FakeGameOrchestrator()
    monkeypatch.setattr(
        "campaignnarrator.cli._build_application_graph",
        lambda *_a, **_kw: MagicMock(game_orchestrator=fake_game_orch),
    )
    main(["--data-root", str(tmp_path)])

    handler = captured_handler.get(signal.SIGTERM)
    assert handler is not None, "SIGTERM handler was not registered"
    # The handler calls sys.exit(0) after save_state() — catch the SystemExit:
    with pytest.raises(SystemExit):
        handler(signal.SIGTERM, None)  # type: ignore[call-arg]
    assert fake_game_orch.save_state_called


def test_sigint_calls_save_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """KeyboardInterrupt during run() must trigger game_orchestrator.save_state()."""
    fake_game_orch = _FakeGameOrchestrator()

    def _raise_keyboard_interrupt() -> None:
        raise KeyboardInterrupt

    fake_game_orch.run = _raise_keyboard_interrupt  # type: ignore[method-assign]

    monkeypatch.setattr(
        "campaignnarrator.cli._build_application_graph",
        lambda *_a, **_kw: MagicMock(game_orchestrator=fake_game_orch),
    )
    # If cli.py catches KeyboardInterrupt and calls save_state(), no exception escapes.
    # If it doesn't, suppress the KeyboardInterrupt so pytest can report the assertion failure.
    with contextlib.suppress(KeyboardInterrupt):
        main(["--data-root", str(tmp_path)])
    assert fake_game_orch.save_state_called


def test_encounter_id_flag_removed(tmp_path: Path) -> None:
    """--encounter-id must no longer be accepted by the CLI."""
    with pytest.raises(SystemExit):
        main(["--data-root", str(tmp_path), "--encounter-id", "goblin-camp"])
