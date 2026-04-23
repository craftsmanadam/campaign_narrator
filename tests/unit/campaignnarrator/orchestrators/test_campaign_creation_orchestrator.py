"""Unit tests for CampaignCreationOrchestrator."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock

from campaignnarrator.agents.campaign_generator_agent import (
    CampaignGenerationResult,
    MilestoneResult,
)
from campaignnarrator.agents.module_generator_agent import ModuleGenerationResult
from campaignnarrator.orchestrators.campaign_creation_orchestrator import (
    CampaignCreationAgents,
    CampaignCreationOrchestrator,
    CampaignCreationRepositories,
)
from campaignnarrator.orchestrators.module_orchestrator import ModuleOrchestrator
from campaignnarrator.repositories.memory_repository import MemoryRepository

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


def _make_orchestrator() -> tuple[
    CampaignCreationOrchestrator, MagicMock, MagicMock, MagicMock
]:
    io = MagicMock()
    io.prompt.return_value = "I want dark coastal horror with undead."

    mock_campaign_repo = MagicMock()
    mock_module_repo = MagicMock()
    mock_memory_repo = MagicMock(spec=MemoryRepository)
    mock_campaign_agent = MagicMock()
    mock_module_agent = MagicMock()
    mock_module_orch = MagicMock(spec=ModuleOrchestrator)

    mock_campaign_agent.generate.return_value = _CAMPAIGN_RESULT
    mock_module_agent.generate.return_value = _MODULE_RESULT

    player = replace(
        TALIA, actor_id="pc:player", name="Aldric", race="Human", background="Soldier."
    )

    repos = CampaignCreationRepositories(
        campaign=mock_campaign_repo,
        module=mock_module_repo,
        memory=mock_memory_repo,
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
    return orch, mock_campaign_repo, mock_module_repo, mock_memory_repo


def test_run_saves_campaign() -> None:
    orch, mock_campaign_repo, _, __ = _make_orchestrator()
    orch.run()
    mock_campaign_repo.save.assert_called_once()
    saved_campaign = mock_campaign_repo.save.call_args[0][0]
    assert saved_campaign.name == "The Cursed Coast"
    assert saved_campaign.bbeg_name == "Malachar"
    assert saved_campaign.player_actor_id == "pc:player"
    assert saved_campaign.starting_level == 1
    assert saved_campaign.target_level == _CAMPAIGN_RESULT.target_level


def test_run_saves_module() -> None:
    orch, _, mock_module_repo, __ = _make_orchestrator()
    orch.run()
    mock_module_repo.save.assert_called_once()
    saved_module = mock_module_repo.save.call_args[0][0]
    assert saved_module.title == "The Dockside Murders"
    assert saved_module.guiding_milestone_id == "m1"


def test_hidden_goal_not_in_player_facing_output() -> None:
    """hidden_goal must never appear in any display() or prompt() call."""
    orch, _, __, ___ = _make_orchestrator()
    orch.run()
    all_display_calls = [str(call) for call in orch._io.display.call_args_list]
    for call_str in all_display_calls:
        assert "Awaken the drowned god" not in call_str


def test_v2_run_saves_campaign() -> None:
    orch, mock_campaign_repo, _, __ = _make_orchestrator()
    orch.run()
    mock_campaign_repo.save.assert_called_once()


def test_v2_run_stores_campaign_setting_in_memory() -> None:
    orch, _, __, mock_memory_repo = _make_orchestrator()
    orch.run()
    mock_memory_repo.store_narrative.assert_called_once()
    args = mock_memory_repo.store_narrative.call_args
    assert args[0][1]["event_type"] == "campaign_setting"


def test_v2_run_delegates_to_module_orchestrator() -> None:
    orch, *_ = _make_orchestrator()
    orch.run()
    orch._module_orchestrator.run.assert_called_once()


def test_v2_run_saves_module_with_empty_log() -> None:
    orch, _, mock_module_repo, __ = _make_orchestrator()
    orch.run()
    mock_module_repo.save.assert_called_once()
    saved = mock_module_repo.save.call_args[0][0]
    assert saved.completed_encounter_ids == ()


def test_v2_campaign_has_current_module_id() -> None:
    orch, mock_campaign_repo, *_ = _make_orchestrator()
    orch.run()
    saved_campaign = mock_campaign_repo.save.call_args[0][0]
    assert saved_campaign.current_module_id == "module-001"


def test_run_displays_building_world_message_before_campaign_generation() -> None:
    """Player must see a progress message immediately after submitting their brief."""
    io = ScriptedIO(["I want dark coastal horror with undead."])
    mock_campaign_repo = MagicMock()
    mock_module_repo = MagicMock()
    mock_memory_repo = MagicMock(spec=MemoryRepository)
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
            campaign=mock_campaign_repo,
            module=mock_module_repo,
            memory=mock_memory_repo,
        ),
        agents=CampaignCreationAgents(
            campaign_generator=mock_campaign_agent,
            module_generator=mock_module_agent,
        ),
        module_orchestrator=mock_module_orch,
    )
    orch.run()
    assert any("Building your world" in msg for msg in io.displayed)
