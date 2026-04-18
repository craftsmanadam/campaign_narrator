"""Unit tests for StartupOrchestrator."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock

from campaignnarrator.orchestrators.startup_orchestrator import StartupOrchestrator

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

    mock_campaign_repo = MagicMock()
    mock_campaign_repo.load.return_value = MagicMock(
        campaign_id="c1",
        name="The Cursed Coast",
    )
    mock_campaign_repo.exists.return_value = True

    mock_campaign_creation = MagicMock()
    mock_encounter_orch = MagicMock()

    player = replace(TALIA, actor_id="pc:player", name="Aldric")

    return StartupOrchestrator(
        io=io,
        player=player,
        campaign_repository=mock_campaign_repo,
        interpreter=mock_interpreter,
        campaign_creation_orchestrator=mock_campaign_creation,
        encounter_orchestrator=mock_encounter_orch,
    )


def test_load_campaign_delegates_to_encounter_orchestrator() -> None:
    orch = _make_orchestrator("load_campaign")
    orch.handle_returning_with_campaign()
    orch._encounter_orchestrator.run_encounter.assert_called_once()


def test_new_campaign_confirmed_destroys_state_and_creates_campaign() -> None:
    orch = _make_orchestrator("new_campaign", confirm_intent="confirm_destroy")
    orch.handle_returning_with_campaign()
    orch._campaign_creation_orchestrator.run.assert_called_once()


def test_new_campaign_aborted_does_nothing() -> None:
    orch = _make_orchestrator("new_campaign", confirm_intent="abort")
    orch.handle_returning_with_campaign()
    orch._campaign_creation_orchestrator.run.assert_not_called()
    orch._encounter_orchestrator.run_encounter.assert_not_called()


def test_abort_at_top_level_does_nothing() -> None:
    orch = _make_orchestrator("abort")
    orch.handle_returning_with_campaign()
    orch._campaign_creation_orchestrator.run.assert_not_called()
    orch._encounter_orchestrator.run_encounter.assert_not_called()


def test_handle_returning_without_campaign_delegates_to_campaign_creation() -> None:
    orch = _make_orchestrator("load_campaign")
    orch.handle_returning_without_campaign()
    orch._campaign_creation_orchestrator.run.assert_called_once()
