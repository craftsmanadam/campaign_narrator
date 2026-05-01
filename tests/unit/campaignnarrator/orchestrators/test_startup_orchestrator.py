"""Unit tests for StartupOrchestrator."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock

from campaignnarrator.orchestrators.module_orchestrator import ModuleOrchestrator
from campaignnarrator.orchestrators.startup_orchestrator import StartupOrchestrator
from campaignnarrator.repositories.game_state_repository import GameStateRepository
from campaignnarrator.repositories.narrative_memory_repository import (
    NarrativeMemoryRepository,
)

from tests.fixtures.fighter_talia import TALIA


def _make_orchestrator(
    intent: str,
    *,
    confirm_intent: str = "abort",
) -> StartupOrchestrator:
    io = MagicMock()
    # first prompt for main menu, second for confirmation
    io.prompt.side_effect = ["load it", "discard"]

    mock_interpreter = MagicMock()
    mock_interpreter.interpret.side_effect = [intent, confirm_intent]

    mock_game_state_repo = MagicMock(spec=GameStateRepository)
    campaign_mock = MagicMock(
        campaign_id="c1",
        name="The Cursed Coast",
        current_module_id="module-001",
    )
    mock_game_state_repo.load.return_value = MagicMock(campaign=campaign_mock)

    mock_campaign_creation = MagicMock()
    mock_module_orch = MagicMock(spec=ModuleOrchestrator)

    player = replace(TALIA, actor_id="pc:player", name="Aldric")

    return StartupOrchestrator(
        io=io,
        player=player,
        narrative_repository=MagicMock(),
        game_state_repository=mock_game_state_repo,
        interpreter=mock_interpreter,
        campaign_creation_orchestrator=mock_campaign_creation,
        module_orchestrator=mock_module_orch,
    )


def test_load_campaign_delegates_to_module_orchestrator() -> None:
    orch = _make_orchestrator("load_campaign")
    orch.handle_returning_with_campaign()
    orch._module_orchestrator.run.assert_called_once()


def test_new_campaign_confirmed_destroys_state_and_creates_campaign() -> None:
    orch = _make_orchestrator("new_campaign", confirm_intent="confirm_destroy")
    orch.handle_returning_with_campaign()
    orch._campaign_creation_orchestrator.run.assert_called_once()


def test_new_campaign_aborted_does_nothing() -> None:
    orch = _make_orchestrator("new_campaign", confirm_intent="abort")
    orch.handle_returning_with_campaign()
    orch._campaign_creation_orchestrator.run.assert_not_called()
    orch._module_orchestrator.run.assert_not_called()


def test_abort_at_top_level_does_nothing() -> None:
    orch = _make_orchestrator("abort")
    orch.handle_returning_with_campaign()
    orch._campaign_creation_orchestrator.run.assert_not_called()
    orch._module_orchestrator.run.assert_not_called()


def test_handle_returning_without_campaign_delegates_to_campaign_creation() -> None:
    orch = _make_orchestrator("load_campaign")
    orch.handle_returning_without_campaign()
    orch._campaign_creation_orchestrator.run.assert_called_once()


def test_v2_load_campaign_delegates_to_module_orchestrator() -> None:
    orch = _make_orchestrator("load_campaign")
    orch.handle_returning_with_campaign()
    orch._module_orchestrator.run.assert_called_once()


def test_module_orchestrator_is_wired() -> None:
    orch = _make_orchestrator("load_campaign")
    assert hasattr(orch, "_module_orchestrator")
    assert not hasattr(orch, "_encounter_orchestrator")


def _make_orchestrator_with_narrative(
    intent: str,
    *,
    confirm_intent: str = "abort",
) -> StartupOrchestrator:
    io = MagicMock()
    io.prompt.side_effect = ["load it", "discard"]
    mock_interpreter = MagicMock()
    mock_interpreter.interpret.side_effect = [intent, confirm_intent]
    mock_game_state_repo = MagicMock(spec=GameStateRepository)
    campaign_mock = MagicMock(
        campaign_id="c1",
        name="The Cursed Coast",
        current_module_id="module-001",
    )
    mock_game_state_repo.load.return_value = MagicMock(campaign=campaign_mock)
    mock_narrative_repo = MagicMock(spec=NarrativeMemoryRepository)
    mock_campaign_creation = MagicMock()
    mock_module_orch = MagicMock()
    player = MagicMock()
    player.name = "Aldric"
    return StartupOrchestrator(
        io=io,
        player=player,
        narrative_repository=mock_narrative_repo,
        game_state_repository=mock_game_state_repo,
        interpreter=mock_interpreter,
        campaign_creation_orchestrator=mock_campaign_creation,
        module_orchestrator=mock_module_orch,
    )


def test_confirm_destroy_clears_narrative_memory() -> None:
    orch = _make_orchestrator_with_narrative(
        "new_campaign", confirm_intent="confirm_destroy"
    )
    orch.handle_returning_with_campaign()
    orch._narrative_repo.clear_narrative.assert_called_once_with("c1")


def test_confirm_destroy_clears_narrative_before_campaign_creation() -> None:
    """Narrative must be cleared before the new campaign creation starts."""
    call_order: list[str] = []
    orch = _make_orchestrator_with_narrative(
        "new_campaign", confirm_intent="confirm_destroy"
    )
    orch._narrative_repo.clear_narrative.side_effect = lambda _: call_order.append(
        "clear"
    )
    orch._campaign_creation_orchestrator.run.side_effect = lambda: call_order.append(
        "create"
    )
    orch.handle_returning_with_campaign()
    assert call_order == ["clear", "create"]


def test_confirm_destroy_calls_game_state_repo_destroy() -> None:
    """_destroy_campaign must call game_state_repo.destroy_campaign()."""
    orch = _make_orchestrator_with_narrative(
        "new_campaign", confirm_intent="confirm_destroy"
    )
    orch.handle_returning_with_campaign()
    orch._game_state_repo.destroy_campaign.assert_called_once_with("c1")


def test_confirm_destroy_calls_structured_before_narrative() -> None:
    """Structured state must be deleted before narrative memory is cleared."""
    call_order: list[str] = []
    orch = _make_orchestrator_with_narrative(
        "new_campaign", confirm_intent="confirm_destroy"
    )
    orch._game_state_repo.destroy_campaign.side_effect = lambda _: call_order.append(
        "structured"
    )
    orch._narrative_repo.clear_narrative.side_effect = lambda _: call_order.append(
        "narrative"
    )
    orch._campaign_creation_orchestrator.run.side_effect = lambda: call_order.append(
        "create"
    )
    orch.handle_returning_with_campaign()
    assert call_order == ["structured", "narrative", "create"]
