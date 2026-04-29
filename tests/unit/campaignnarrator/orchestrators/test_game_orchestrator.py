"""Unit tests for GameOrchestrator."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock

from campaignnarrator.orchestrators.game_orchestrator import GameOrchestrator

from tests.fixtures.fighter_talia import TALIA


def _make_orchestrator(
    *,
    player_exists: bool,
    campaign_exists: bool,
) -> GameOrchestrator:
    mock_actor_repo = MagicMock()
    mock_campaign_repo = MagicMock()
    mock_char_creation = MagicMock()
    mock_campaign_creation = MagicMock()
    mock_startup = MagicMock()

    if player_exists:
        mock_actor_repo.load.return_value = replace(TALIA, actor_id="pc:player")
    else:
        mock_actor_repo.load.side_effect = FileNotFoundError("no player")

    mock_campaign_repo.exists.return_value = campaign_exists

    return GameOrchestrator(
        actor_repository=mock_actor_repo,
        campaign_repository=mock_campaign_repo,
        character_creation_orchestrator=mock_char_creation,
        campaign_creation_orchestrator=mock_campaign_creation,
        startup_orchestrator=mock_startup,
    )


def test_no_player_runs_character_creation_then_campaign_creation() -> None:
    orch = _make_orchestrator(player_exists=False, campaign_exists=False)
    orch.run()
    orch._character_creation_orchestrator.run.assert_called_once()
    orch._campaign_creation_orchestrator.run.assert_called_once()


def test_player_exists_no_campaign_runs_startup_without_campaign() -> None:
    orch = _make_orchestrator(player_exists=True, campaign_exists=False)
    orch.run()
    orch._startup_orchestrator.handle_returning_without_campaign.assert_called_once()
    orch._character_creation_orchestrator.run.assert_not_called()


def test_player_exists_campaign_exists_runs_startup_with_campaign() -> None:
    orch = _make_orchestrator(player_exists=True, campaign_exists=True)
    orch.run()
    orch._startup_orchestrator.handle_returning_with_campaign.assert_called_once()
    orch._character_creation_orchestrator.run.assert_not_called()
