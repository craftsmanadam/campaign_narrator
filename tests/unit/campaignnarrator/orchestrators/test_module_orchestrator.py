"""Unit tests for ModuleOrchestrator."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock

from campaignnarrator.agents.module_generator_agent import (
    ModuleGenerationResult,
    ModuleGeneratorAgent,
)
from campaignnarrator.agents.narrator_agent import NarratorAgent
from campaignnarrator.domain.models import (
    ActorState,
    CampaignState,
    EncounterPhase,
    EncounterReady,
    EncounterState,
    GameState,
    Milestone,
    MilestoneAchieved,
    ModuleState,
)
from campaignnarrator.orchestrators.encounter_planner_orchestrator import (
    EncounterPlannerOrchestrator,
)
from campaignnarrator.orchestrators.module_orchestrator import (
    ModuleOrchestrator,
    ModuleOrchestratorAgents,
    ModuleOrchestratorRepositories,
)
from campaignnarrator.repositories.actor_repository import ActorRepository
from campaignnarrator.repositories.campaign_repository import CampaignRepository
from campaignnarrator.repositories.compendium_repository import CompendiumRepository
from campaignnarrator.repositories.encounter_repository import EncounterRepository
from campaignnarrator.repositories.memory_repository import MemoryRepository
from campaignnarrator.repositories.module_repository import ModuleRepository

from tests.conftest import ScriptedIO
from tests.fixtures.fighter_talia import TALIA


def _make_player() -> ActorState:
    return replace(TALIA, actor_id="pc:player", name="Aldric", race="Human")


def _make_campaign(current_module_id: str = "module-001") -> CampaignState:
    return CampaignState(
        campaign_id="c-1",
        name="The Cursed Coast",
        setting="A fog-draped coastal city.",
        narrator_personality="Grim.",
        hidden_goal="Awaken the drowned god.",
        bbeg_name="Malachar",
        bbeg_description="A lich.",
        milestones=(
            Milestone(milestone_id="m1", title="First Blood", description="Survive."),
            Milestone(milestone_id="m2", title="The Cult", description="Unmask."),
        ),
        current_milestone_index=0,
        starting_level=1,
        target_level=5,
        player_brief="Dark coastal horror.",
        player_actor_id="pc:player",
        current_module_id=current_module_id,
    )


def _make_module(
    *,
    completed_encounter_ids: tuple[str, ...] = (),
    completed_encounter_summaries: tuple[str, ...] = (),
    next_encounter_index: int = 0,
) -> ModuleState:
    return ModuleState(
        module_id="module-001",
        campaign_id="c-1",
        title="The Dockside Murders",
        summary="Bodies wash ashore.",
        guiding_milestone_id="m1",
        completed_encounter_ids=completed_encounter_ids,
        completed_encounter_summaries=completed_encounter_summaries,
        next_encounter_index=next_encounter_index,
    )


def _make_active_encounter(
    phase: EncounterPhase = EncounterPhase.SCENE_OPENING,
    encounter_id: str = "module-001-enc-001",
    outcome: str | None = None,
) -> EncounterState:
    return EncounterState(
        encounter_id=encounter_id,
        phase=phase,
        setting="The docks at dusk.",
        actors={"pc:player": _make_player()},
        outcome=outcome,
    )


def _make_planner_encounter() -> EncounterState:
    """Return an encounter the planner would create (different id to avoid loops)."""
    return EncounterState(
        encounter_id="module-001-enc-new",
        phase=EncounterPhase.SCENE_OPENING,
        setting="A new scene.",
        actors={},
    )


def _make_orchestrator(
    *,
    module: ModuleState | None = None,
    active_encounter: EncounterState | None = None,
    encounter_ready: EncounterReady | MilestoneAchieved | None = None,
    summarize_returns: str = "Rich encounter summary.",
) -> tuple[
    ModuleOrchestrator,
    MagicMock,
    MagicMock,
    MagicMock,
    MagicMock,
    MagicMock,
]:
    io = MagicMock()

    mock_campaign_repo = MagicMock(spec=CampaignRepository)
    mock_module_repo = MagicMock(spec=ModuleRepository)
    mock_encounter_repo = MagicMock(spec=EncounterRepository)
    mock_actor_repo = MagicMock(spec=ActorRepository)
    mock_memory_repo = MagicMock(spec=MemoryRepository)
    mock_compendium_repo = MagicMock(spec=CompendiumRepository)

    resolved_module = module or _make_module()
    mock_module_repo.load.return_value = resolved_module
    mock_encounter_repo.load_active.return_value = active_encounter

    mock_narrator = MagicMock(spec=NarratorAgent)
    mock_narrator.summarize_encounter.return_value = summarize_returns

    mock_encounter_planner = MagicMock(spec=EncounterPlannerOrchestrator)
    default_ready = EncounterReady(
        encounter_state=_make_planner_encounter(),
        module=resolved_module,
    )
    mock_encounter_planner.prepare.return_value = encounter_ready or default_ready

    mock_module_gen = MagicMock(spec=ModuleGeneratorAgent)
    mock_encounter_orch = MagicMock()
    mock_encounter_orch.run_encounter.return_value = None
    mock_actor_repo.load_player.return_value = _make_player()
    # Default: post-run memory read returns no active encounter (player quit, no completion)
    mock_memory_repo.load_game_state.return_value = GameState(
        player=_make_player(), encounter=None
    )

    repos = ModuleOrchestratorRepositories(
        campaign=mock_campaign_repo,
        module=mock_module_repo,
        encounter=mock_encounter_repo,
        actor=mock_actor_repo,
        memory=mock_memory_repo,
        compendium=mock_compendium_repo,
    )
    agents = ModuleOrchestratorAgents(
        narrator=mock_narrator,
        module_generator=mock_module_gen,
        encounter_planner=mock_encounter_planner,
    )
    orch = ModuleOrchestrator(
        io=io,
        repositories=repos,
        agents=agents,
        encounter_orchestrator=mock_encounter_orch,
    )
    return (
        orch,
        mock_module_repo,
        mock_encounter_repo,
        mock_narrator,
        mock_encounter_orch,
        mock_memory_repo,
    )


def test_module_orchestrator_instantiates() -> None:
    orch, mock_module_repo, _, _, _, _ = _make_orchestrator()
    assert orch._repos.module is mock_module_repo


def test_run_with_in_progress_encounter_calls_run_encounter() -> None:
    """Step 2c: active encounter not complete → resume it."""
    active = _make_active_encounter(phase=EncounterPhase.SCENE_OPENING)
    orch, _, _, _, mock_enc_orch, _ = _make_orchestrator(active_encounter=active)
    orch.run(campaign=_make_campaign(), player=_make_player())
    mock_enc_orch.run_encounter.assert_called_once_with(
        encounter_id="module-001-enc-001"
    )


def test_run_with_no_active_encounter_calls_encounter_planner() -> None:
    """No active encounter → encounter_planner.prepare() is called."""
    orch, _, _, _, _, _ = _make_orchestrator(active_encounter=None)
    orch.run(campaign=_make_campaign(), player=_make_player())
    orch._agents.encounter_planner.prepare.assert_called_once()


def test_run_with_no_active_encounter_calls_run_encounter() -> None:
    """No active encounter → run_encounter is called with planner's encounter_id."""
    orch, _, _, _, mock_enc_orch, _ = _make_orchestrator(active_encounter=None)
    orch.run(campaign=_make_campaign(), player=_make_player())
    mock_enc_orch.run_encounter.assert_called_once_with(
        encounter_id="module-001-enc-new"
    )


def test_run_does_not_forward_encounter_output_to_io() -> None:
    """Encounter output is displayed live in EncounterOrchestrator; not forwarded."""
    active = _make_active_encounter(phase=EncounterPhase.SCENE_OPENING)
    orch, _, _, _, mock_enc_orch, _ = _make_orchestrator(active_encounter=active)
    mock_enc_orch.run_encounter.return_value = MagicMock(output_text="Docks at dusk.")
    orch.run(campaign=_make_campaign(), player=_make_player())
    # Output display is the encounter orchestrator's responsibility; module orchestrator
    # must not re-display it via io.display.
    for call in orch._io.display.call_args_list:
        assert "Docks at dusk." not in str(call)


def test_run_with_completed_encounter_calls_summarize() -> None:
    """Step 2b: completed encounter → archive → summarize_encounter called."""
    active = _make_active_encounter(
        phase=EncounterPhase.ENCOUNTER_COMPLETE,
        outcome="Cultist subdued.",
    )
    orch, _, mock_enc_repo, mock_narrator, _, _ = _make_orchestrator(
        active_encounter=active,
        module=_make_module(),
    )
    mock_enc_repo.load_active.return_value = active
    orch.run(campaign=_make_campaign(), player=_make_player())
    mock_narrator.summarize_encounter.assert_called_once()


def test_run_with_completed_encounter_stores_narrative() -> None:
    active = _make_active_encounter(
        phase=EncounterPhase.ENCOUNTER_COMPLETE,
        outcome="Cultist subdued.",
    )
    orch, _, mock_enc_repo, _, _, mock_memory_repo = _make_orchestrator(
        active_encounter=active,
        module=_make_module(),
        summarize_returns="Rich summary text.",
    )
    mock_enc_repo.load_active.return_value = active
    orch.run(campaign=_make_campaign(), player=_make_player())
    mock_memory_repo.store_narrative.assert_called_once()
    args = mock_memory_repo.store_narrative.call_args
    assert args[0][0] == "Rich summary text."
    assert args[0][1]["event_type"] == "encounter_summary"


def test_run_with_completed_encounter_clears_encounter() -> None:
    active = _make_active_encounter(
        phase=EncounterPhase.ENCOUNTER_COMPLETE,
        outcome="Cultist subdued.",
    )
    orch, _, mock_enc_repo, _, _, _ = _make_orchestrator(
        active_encounter=active,
        module=_make_module(),
    )
    mock_enc_repo.load_active.return_value = active
    orch.run(campaign=_make_campaign(), player=_make_player())
    mock_enc_repo.clear.assert_called_once()


def test_run_with_completed_encounter_saves_updated_module() -> None:
    active = _make_active_encounter(
        phase=EncounterPhase.ENCOUNTER_COMPLETE,
        outcome="Cultist subdued.",
    )
    orch, mock_module_repo, mock_enc_repo, _, _, _ = _make_orchestrator(
        active_encounter=active,
        module=_make_module(),
        summarize_returns="Session notes.",
    )
    mock_enc_repo.load_active.return_value = active
    orch.run(campaign=_make_campaign(), player=_make_player())
    # Module save called at least once (archive)
    assert mock_module_repo.save.call_count >= 1
    # The archived module carries the completed encounter id
    all_saved = [call[0][0] for call in mock_module_repo.save.call_args_list]
    archived = next(
        m for m in all_saved if "module-001-enc-001" in m.completed_encounter_ids
    )
    assert archived is not None


def test_run_archive_increments_next_encounter_index() -> None:
    """_archive_encounter must bump next_encounter_index by 1."""
    _initial_index = 2
    active = _make_active_encounter(
        phase=EncounterPhase.ENCOUNTER_COMPLETE,
        outcome="Done.",
    )
    orch, mock_module_repo, mock_enc_repo, _, _, _ = _make_orchestrator(
        active_encounter=active,
        module=_make_module(next_encounter_index=_initial_index),
    )
    mock_enc_repo.load_active.return_value = active
    orch.run(campaign=_make_campaign(), player=_make_player())
    all_saved = [call[0][0] for call in mock_module_repo.save.call_args_list]
    archived = next(
        m for m in all_saved if "module-001-enc-001" in m.completed_encounter_ids
    )
    assert archived.next_encounter_index == _initial_index + 1


def test_run_milestone_achieved_saves_new_module() -> None:
    """MilestoneAchieved from planner → new module is generated and saved."""
    active = _make_active_encounter(
        phase=EncounterPhase.ENCOUNTER_COMPLETE,
        outcome="Malachar defeated.",
    )
    orch, mock_module_repo, mock_enc_repo, _, _, _ = _make_orchestrator(
        active_encounter=active,
        module=_make_module(),
        encounter_ready=MilestoneAchieved(),
    )
    mock_enc_repo.load_active.return_value = active

    module_result = ModuleGenerationResult(
        title="The Cult Revealed",
        summary="The sea cult unmasked.",
        guiding_milestone_id="m2",
    )
    orch._agents.module_generator.generate.return_value = module_result

    orch.run(campaign=_make_campaign(), player=_make_player())

    saved_modules = [call[0][0] for call in mock_module_repo.save.call_args_list]
    new_module = next((m for m in saved_modules if m.module_id == "module-002"), None)
    assert new_module is not None
    assert new_module.title == "The Cult Revealed"


def test_run_returns_early_when_module_not_found() -> None:
    orch, mock_module_repo, _, _, mock_enc_orch, _ = _make_orchestrator()
    mock_module_repo.load.return_value = None
    orch.run(campaign=_make_campaign(), player=_make_player())
    mock_enc_orch.run_encounter.assert_not_called()


def test_run_displays_end_of_campaign_when_milestones_exhausted() -> None:
    """MilestoneAchieved with no further milestones → display end-of-campaign."""
    active = _make_active_encounter(
        phase=EncounterPhase.ENCOUNTER_COMPLETE,
        outcome="Final confrontation.",
    )
    # Campaign with only 1 milestone, current_milestone_index=0 → no next milestone
    campaign = CampaignState(
        campaign_id="c-1",
        name="The Cursed Coast",
        setting="A fog-draped coastal city.",
        narrator_personality="Grim.",
        hidden_goal="Awaken the drowned god.",
        bbeg_name="Malachar",
        bbeg_description="A lich.",
        milestones=(
            Milestone(milestone_id="m1", title="First Blood", description="Survive."),
        ),
        current_milestone_index=0,
        starting_level=1,
        target_level=5,
        player_brief="Dark coastal horror.",
        player_actor_id="pc:player",
        current_module_id="module-001",
    )
    orch, _, mock_enc_repo, _, _, _ = _make_orchestrator(
        active_encounter=active,
        module=_make_module(),
        encounter_ready=MilestoneAchieved(),
    )
    mock_enc_repo.load_active.return_value = active
    orch.run(campaign=campaign, player=_make_player())
    orch._io.display.assert_any_call(
        "\nThe campaign is complete. Your legend will be remembered.\n"
    )


def test_run_with_completed_encounter_passes_updated_module_to_planner() -> None:
    """After archiving, the planner receives the updated module (next_encounter_index+1)."""
    active = _make_active_encounter(
        phase=EncounterPhase.ENCOUNTER_COMPLETE,
        outcome="Cultist subdued.",
    )
    _initial_index = 1
    orch, _, mock_enc_repo, _, _, _ = _make_orchestrator(
        active_encounter=active,
        module=_make_module(next_encounter_index=_initial_index),
    )
    mock_enc_repo.load_active.return_value = active
    orch.run(campaign=_make_campaign(), player=_make_player())
    prepare_call = orch._agents.encounter_planner.prepare.call_args
    passed_module = prepare_call[1]["module"]
    assert passed_module.next_encounter_index == _initial_index + 1


def test_run_planner_receive_correct_campaign_and_player() -> None:
    """prepare() must be called with the correct campaign and player."""
    orch, _, _, _, _, _ = _make_orchestrator(active_encounter=None)
    campaign = _make_campaign()
    player = _make_player()
    orch.run(campaign=campaign, player=player)
    prepare_call = orch._agents.encounter_planner.prepare.call_args
    assert prepare_call[1]["campaign"] is campaign
    assert prepare_call[1]["player"] is player


def test_run_with_scripted_io_module_not_found_no_crash() -> None:
    """ModuleOrchestrator must not crash when module is absent."""
    io = ScriptedIO([])
    mock_module_repo = MagicMock(spec=ModuleRepository)
    mock_module_repo.load.return_value = None
    mock_encounter_planner = MagicMock(spec=EncounterPlannerOrchestrator)
    repos = ModuleOrchestratorRepositories(
        campaign=MagicMock(spec=CampaignRepository),
        module=mock_module_repo,
        encounter=MagicMock(spec=EncounterRepository),
        actor=MagicMock(spec=ActorRepository),
        memory=MagicMock(spec=MemoryRepository),
        compendium=MagicMock(spec=CompendiumRepository),
    )
    agents = ModuleOrchestratorAgents(
        narrator=MagicMock(spec=NarratorAgent),
        module_generator=MagicMock(spec=ModuleGeneratorAgent),
        encounter_planner=mock_encounter_planner,
    )
    orch = ModuleOrchestrator(
        io=io,
        repositories=repos,
        agents=agents,
        encounter_orchestrator=MagicMock(),
    )
    orch.run(campaign=_make_campaign(), player=_make_player())
    mock_encounter_planner.prepare.assert_not_called()


def test_archive_encounter_calls_clear_encounter_memory() -> None:
    """_archive_encounter() must call clear_encounter_memory() after store_narrative()."""
    active = _make_active_encounter(
        phase=EncounterPhase.ENCOUNTER_COMPLETE,
        outcome="victory",
    )
    orch, _, _, _, _, mock_memory_repo = _make_orchestrator(active_encounter=active)
    orch.run(campaign=_make_campaign(), player=_make_player())
    mock_memory_repo.clear_encounter_memory.assert_called_once()


def test_run_player_quits_mid_encounter_does_not_archive() -> None:
    """If player quits (encounter not complete after run), no archiving occurs."""
    active = _make_active_encounter(phase=EncounterPhase.COMBAT)
    orch, _, mock_enc_repo, mock_narrator, _mock_enc_orch, mock_memory_repo = (
        _make_orchestrator(active_encounter=active)
    )
    # After run_encounter, memory returns COMBAT phase (player quit, not complete)
    mock_memory_repo.load_game_state.return_value = GameState(
        player=_make_player(), encounter=active
    )
    orch.run(campaign=_make_campaign(), player=_make_player())
    mock_narrator.summarize_encounter.assert_not_called()
    mock_enc_repo.clear.assert_not_called()


def test_run_encounter_completes_during_run_triggers_archive() -> None:
    """Encounter that reaches ENCOUNTER_COMPLETE during run_encounter is archived."""
    active = _make_active_encounter(phase=EncounterPhase.SCENE_OPENING)
    completed = _make_active_encounter(
        phase=EncounterPhase.ENCOUNTER_COMPLETE, outcome="victory"
    )
    orch, _, mock_enc_repo, mock_narrator, _, mock_memory_repo = _make_orchestrator(
        active_encounter=active
    )
    # After run_encounter, memory cache holds the completed encounter
    mock_memory_repo.load_game_state.return_value = GameState(
        player=_make_player(), encounter=completed
    )
    orch.run(campaign=_make_campaign(), player=_make_player())
    mock_narrator.summarize_encounter.assert_called_once()
    mock_enc_repo.clear.assert_called_once()
