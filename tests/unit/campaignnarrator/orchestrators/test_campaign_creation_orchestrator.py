"""Unit tests for CampaignCreationOrchestrator."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock

from campaignnarrator.agents.campaign_generator_agent import (
    CampaignGenerationResult,
    MilestoneResult,
)
from campaignnarrator.agents.module_generator_agent import ModuleGenerationResult
from campaignnarrator.domain.models import GameState
from campaignnarrator.orchestrators.campaign_creation_orchestrator import (
    CampaignCreationAgents,
    CampaignCreationOrchestrator,
    CampaignCreationRepositories,
)
from campaignnarrator.orchestrators.module_orchestrator import ModuleOrchestrator
from campaignnarrator.repositories.narrative_memory_repository import (
    NarrativeMemoryRepository,
)

from tests.conftest import ScriptedIO
from tests.fixtures.fighter_talia import TALIA

_CAMPAIGN_RESULT = CampaignGenerationResult(
    name="The Cursed Coast",
    setting="A fog-draped coastal city.",
    narrator_personality="Grim and dramatic.",
    hidden_goal="Awaken the drowned god.",
    bbeg_name="Malachar",
    bbeg_description="A lich who walks the tides.",
    milestones=[
        MilestoneResult(milestone_id="m1", title="First Blood", description="Survive."),
        MilestoneResult(milestone_id="m2", title="The Truth", description="Uncover."),
        MilestoneResult(milestone_id="m3", title="Reckoning", description="Face."),
    ],
    target_level=5,
)

_MODULE_RESULT = ModuleGenerationResult(
    title="The Dockside Murders",
    summary="Bodies wash ashore.",
    guiding_milestone_id="m1",
)


def _make_orchestrator() -> tuple[CampaignCreationOrchestrator, MagicMock, MagicMock]:
    io = MagicMock()
    io.prompt_multiline.return_value = "I want dark coastal horror with undead."

    mock_narrative_repo = MagicMock(spec=NarrativeMemoryRepository)
    mock_game_state_repo = MagicMock()
    mock_game_state_repo.load.return_value = GameState()
    mock_campaign_agent = MagicMock()
    mock_module_agent = MagicMock()
    mock_module_orch = MagicMock(spec=ModuleOrchestrator)

    mock_campaign_agent.generate.return_value = _CAMPAIGN_RESULT
    mock_module_agent.generate.return_value = _MODULE_RESULT

    player = replace(
        TALIA, actor_id="pc:player", name="Aldric", race="Human", background="Soldier."
    )

    repos = CampaignCreationRepositories(
        narrative=mock_narrative_repo,
        game_state=mock_game_state_repo,
    )
    agents = CampaignCreationAgents(
        campaign_generator=mock_campaign_agent,
        module_generator=mock_module_agent,
    )
    orch = CampaignCreationOrchestrator(
        io=io,
        player=player,
        repositories=repos,
        agents=agents,
        module_orchestrator=mock_module_orch,
    )
    return orch, mock_narrative_repo, mock_game_state_repo


def test_run_persists_campaign_via_game_state() -> None:
    orch, _, mock_game_state_repo = _make_orchestrator()
    orch.run()
    mock_game_state_repo.persist.assert_called()
    call_args_list = mock_game_state_repo.persist.call_args_list
    staged_campaigns = [
        call.args[0].campaign
        for call in call_args_list
        if call.args[0].campaign is not None
    ]
    assert any(getattr(c, "name", None) == "The Cursed Coast" for c in staged_campaigns)


def test_run_persists_module_via_game_state() -> None:
    orch, _, mock_game_state_repo = _make_orchestrator()
    orch.run()
    mock_game_state_repo.persist.assert_called()
    call_args_list = mock_game_state_repo.persist.call_args_list
    staged_modules = [
        call.args[0].module
        for call in call_args_list
        if call.args[0].module is not None
    ]
    assert any(
        getattr(m, "title", None) == "The Dockside Murders" for m in staged_modules
    )


def test_hidden_goal_not_in_player_facing_output() -> None:
    """hidden_goal must never appear in any display() or prompt() call."""
    orch, _, __ = _make_orchestrator()
    orch.run()
    all_display_calls = [str(call) for call in orch._io.display.call_args_list]
    for call_str in all_display_calls:
        assert "Awaken the drowned god" not in call_str


def test_v2_run_saves_campaign() -> None:
    orch, _, mock_game_state_repo = _make_orchestrator()
    orch.run()
    mock_game_state_repo.persist.assert_called()


def test_v2_run_stores_campaign_setting_in_narrative() -> None:
    orch, mock_narrative_repo, _ = _make_orchestrator()
    orch.run()
    mock_narrative_repo.store_narrative.assert_called_once()
    args = mock_narrative_repo.store_narrative.call_args
    assert args[0][1]["event_type"] == "campaign_setting"


def test_v2_run_delegates_to_module_orchestrator() -> None:
    orch, *_ = _make_orchestrator()
    orch.run()
    orch._module_orchestrator.run.assert_called_once()


def test_v2_run_saves_module_with_empty_log() -> None:
    orch, _, mock_game_state_repo = _make_orchestrator()
    orch.run()
    call_args_list = mock_game_state_repo.persist.call_args_list
    staged_modules = [
        call.args[0].module
        for call in call_args_list
        if call.args[0].module is not None
    ]
    assert any(m.completed_encounter_ids == () for m in staged_modules)


def test_v2_campaign_has_current_module_id() -> None:
    orch, _, mock_game_state_repo = _make_orchestrator()
    orch.run()
    call_args_list = mock_game_state_repo.persist.call_args_list
    staged_campaigns = [
        call.args[0].campaign
        for call in call_args_list
        if call.args[0].campaign is not None
    ]
    assert any(
        getattr(c, "current_module_id", None) == "module-001" for c in staged_campaigns
    )


def test_run_displays_building_world_message_before_campaign_generation() -> None:
    """Player must see a progress message immediately after submitting their brief."""
    io = ScriptedIO(["I want dark coastal horror with undead."])
    mock_narrative_repo = MagicMock(spec=NarrativeMemoryRepository)
    mock_game_state_repo = MagicMock()
    mock_game_state_repo.load.return_value = GameState()
    mock_campaign_agent = MagicMock()
    mock_module_agent = MagicMock()
    mock_module_orch = MagicMock(spec=ModuleOrchestrator)

    mock_campaign_agent.generate.return_value = _CAMPAIGN_RESULT
    mock_module_agent.generate.return_value = _MODULE_RESULT

    player = replace(
        TALIA, actor_id="pc:player", name="Aldric", race="Human", background="Soldier."
    )
    orch = CampaignCreationOrchestrator(
        io=io,
        player=player,
        repositories=CampaignCreationRepositories(
            narrative=mock_narrative_repo,
            game_state=mock_game_state_repo,
        ),
        agents=CampaignCreationAgents(
            campaign_generator=mock_campaign_agent,
            module_generator=mock_module_agent,
        ),
        module_orchestrator=mock_module_orch,
    )
    orch.run()
    assert any("Building your world" in msg for msg in io.displayed)
