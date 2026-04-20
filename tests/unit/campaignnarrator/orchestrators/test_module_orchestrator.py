"""Unit tests for ModuleOrchestrator."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock

from campaignnarrator.agents.module_generator_agent import (
    ModuleGenerationResult,
    ModuleGeneratorAgent,
)
from campaignnarrator.agents.narrator_agent import NarratorAgent
from campaignnarrator.domain.models import (
    ActorState,
    ActorType,
    CampaignState,
    EncounterPhase,
    EncounterState,
    Milestone,
    ModuleState,
    NextEncounterPlan,
    NpcPresenceResult,
    SceneOpeningResponse,
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
    next_encounter_seed: str | None = None,
    completed_encounter_ids: tuple[str, ...] = (),
    completed_encounter_summaries: tuple[str, ...] = (),
) -> ModuleState:
    return ModuleState(
        module_id="module-001",
        campaign_id="c-1",
        title="The Dockside Murders",
        summary="Bodies wash ashore.",
        guiding_milestone_id="m1",
        completed_encounter_ids=completed_encounter_ids,
        completed_encounter_summaries=completed_encounter_summaries,
        next_encounter_seed=next_encounter_seed,
    )


def _make_active_encounter(
    phase: EncounterPhase = EncounterPhase.SCENE_OPENING,
    outcome: str | None = None,
) -> EncounterState:
    return EncounterState(
        encounter_id="module-001-enc-001",
        phase=phase,
        setting="The docks at dusk.",
        actors={"pc:player": _make_player()},
        outcome=outcome,
    )


def _make_orchestrator(
    *,
    module: ModuleState | None = None,
    active_encounter: EncounterState | None = None,
    plan: NextEncounterPlan | None = None,
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
    mock_compendium_repo.monster_index_path.return_value = MagicMock(
        exists=lambda: False
    )

    mock_module_repo.load.return_value = module or _make_module(
        next_encounter_seed="The docks at midnight."
    )
    mock_encounter_repo.load_active.return_value = active_encounter

    # After run_encounter, simulate a non-complete encounter (player quit)
    mock_narrator = MagicMock(spec=NarratorAgent)
    mock_narrator.summarize_encounter.return_value = summarize_returns
    mock_narrator.plan_next_encounter.return_value = plan or NextEncounterPlan(
        seed="The warehouse at midnight.", milestone_achieved=False
    )
    mock_narrator.open_scene.return_value = SceneOpeningResponse(
        text="The docks loom ahead.",
        scene_tone="tense and foreboding",
        introduced_npcs=[],
    )
    mock_module_gen = MagicMock(spec=ModuleGeneratorAgent)
    mock_encounter_orch = MagicMock()
    mock_encounter_orch.run_encounter.return_value = MagicMock(
        output_text="Scene narration."
    )
    mock_actor_repo.load_player.return_value = _make_player()

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
    orch, _, mock_enc_repo, _, mock_enc_orch, _ = _make_orchestrator(
        active_encounter=active
    )
    # After run_encounter, reload returns non-complete phase (player quit)
    mock_enc_repo.load_active.side_effect = [active, active]
    orch.run(campaign=_make_campaign(), player=_make_player())
    mock_enc_orch.run_encounter.assert_called_once_with(
        encounter_id="module-001-enc-001"
    )


def test_run_with_no_active_encounter_does_not_call_run_encounter_immediately() -> None:
    """Step 2a: no active encounter → skip to plan next (implemented in Task 3)."""
    orch, _, _, _, mock_enc_orch, _ = _make_orchestrator(
        active_encounter=None,
        module=_make_module(next_encounter_seed="The docks at midnight."),
    )
    orch.run(campaign=_make_campaign(), player=_make_player())
    # run_encounter IS called (step 6 creates and runs a new encounter)
    mock_enc_orch.run_encounter.assert_called_once()


def test_run_does_not_forward_encounter_output_to_io() -> None:
    """Encounter output is displayed live in EncounterOrchestrator; not forwarded."""
    active = _make_active_encounter(phase=EncounterPhase.SCENE_OPENING)
    orch, _, mock_enc_repo, _, mock_enc_orch, _ = _make_orchestrator(
        active_encounter=active
    )
    mock_enc_orch.run_encounter.return_value = MagicMock(output_text="Docks at dusk.")
    mock_enc_repo.load_active.side_effect = [active, active]
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
    # Module save called at least once (archive + after plan)
    assert mock_module_repo.save.call_count >= 1
    last_saved = mock_module_repo.save.call_args[0][0]
    assert "module-001-enc-001" in last_saved.completed_encounter_ids


def test_run_creates_encounter_id_from_log_length() -> None:
    """Encounter ID is {module_id}-enc-{len(completed)+1:03d}."""
    orch, _, mock_enc_repo, _, mock_enc_orch, _ = _make_orchestrator(
        active_encounter=None,
        module=_make_module(
            next_encounter_seed="The docks at midnight.",
            completed_encounter_ids=("module-001-enc-001", "module-001-enc-002"),
        ),
    )
    mock_enc_repo.load_active.return_value = None  # after creation, player quit
    orch.run(campaign=_make_campaign(), player=_make_player())
    call_kwargs = mock_enc_orch.run_encounter.call_args[1]
    assert call_kwargs["encounter_id"] == "module-001-enc-003"


def test_run_milestone_achieved_saves_new_module() -> None:
    """milestone_achieved=True → new module is generated and saved."""
    active = _make_active_encounter(
        phase=EncounterPhase.ENCOUNTER_COMPLETE,
        outcome="Malachar defeated.",
    )
    plan = NextEncounterPlan(seed="", milestone_achieved=True)
    orch, mock_module_repo, mock_enc_repo, mock_narrator, _, _ = _make_orchestrator(
        active_encounter=active,
        module=_make_module(),
        plan=plan,
    )
    mock_enc_repo.load_active.return_value = active
    mock_narrator.plan_next_encounter.return_value = plan

    module_result = ModuleGenerationResult(
        title="The Cult Revealed",
        summary="The sea cult unmasked.",
        guiding_milestone_id="m2",
        opening_encounter_seed="A candlelit cellar beneath the tavern.",
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
    """When milestone_achieved and no more milestones exist, display end-of-campaign."""
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
    plan = NextEncounterPlan(seed="", milestone_achieved=True)
    orch, _, mock_enc_repo, mock_narrator, _, _ = _make_orchestrator(
        active_encounter=active,
        module=_make_module(),
        plan=plan,
    )
    mock_enc_repo.load_active.return_value = active
    mock_narrator.plan_next_encounter.return_value = plan
    orch.run(campaign=campaign, player=_make_player())
    orch._io.display.assert_any_call(
        "\nThe campaign is complete. Your legend will be remembered.\n"
    )


def test_create_encounter_seeds_simple_npc(tmp_path: Path) -> None:
    """NPCs declared by narrator are seeded into EncounterState."""
    tmp = tmp_path
    (tmp / "state" / "actors").mkdir(parents=True)
    (tmp / "state" / "encounters").mkdir(parents=True)
    (tmp / "compendium" / "monsters").mkdir(parents=True)
    (tmp / "compendium" / "monsters" / "index.json").write_text("[]")

    actor_repo = ActorRepository(tmp / "state")
    encounter_repo = EncounterRepository(tmp / "state")
    campaign_repo = MagicMock(spec=CampaignRepository)
    module_repo = MagicMock(spec=ModuleRepository)
    memory_repo = MagicMock(spec=MemoryRepository)
    memory_repo.store_narrative = MagicMock()
    memory_repo.retrieve_relevant = MagicMock(return_value=[])
    compendium_repo = CompendiumRepository(tmp / "compendium")

    mock_narrator = MagicMock()
    mock_narrator.open_scene.return_value = SceneOpeningResponse(
        text="The tavern hums with life.",
        scene_tone="warm and welcoming",
        introduced_npcs=[
            NpcPresenceResult(
                display_name="Mira",
                description="the innkeeper",
                name_known=False,
                stat_source="simple_npc",
            )
        ],
    )
    mock_module_gen = MagicMock()
    mock_encounter_orchestrator = MagicMock()
    mock_encounter_orchestrator.run_encounter.return_value = None

    io = ScriptedIO(["exit"])

    orchestrator = ModuleOrchestrator(
        io=io,
        repositories=ModuleOrchestratorRepositories(
            campaign=campaign_repo,
            module=module_repo,
            encounter=encounter_repo,
            actor=actor_repo,
            memory=memory_repo,
            compendium=compendium_repo,
        ),
        agents=ModuleOrchestratorAgents(
            narrator=mock_narrator,
            module_generator=mock_module_gen,
        ),
        encounter_orchestrator=mock_encounter_orchestrator,
    )

    player = ActorState(
        actor_id="pc:fighter",
        name="Fighter",
        actor_type=ActorType.PC,
        hp_max=12,
        hp_current=12,
        armor_class=16,
        strength=16,
        dexterity=12,
        constitution=14,
        intelligence=10,
        wisdom=10,
        charisma=10,
        proficiency_bonus=2,
        initiative_bonus=1,
        speed=30,
        attacks_per_action=1,
        action_options=("Attack",),
        ac_breakdown=("chain mail",),
    )
    module = ModuleState(
        module_id="module-001",
        campaign_id="camp-001",
        title="Test Module",
        summary="A test module",
        guiding_milestone_id="m-001",
        next_encounter_seed="A dimly lit tavern.",
    )

    orchestrator._create_and_run_encounter(
        campaign=MagicMock(),
        player=player,
        module=module,
    )

    saved = encounter_repo.load_active()
    assert saved is not None
    npc_ids = [aid for aid in saved.actors if aid != "pc:fighter"]
    assert len(npc_ids) == 1
    assert "mira" in npc_ids[0]
    assert len(saved.npc_presences) == 1
    assert saved.npc_presences[0].description == "the innkeeper"
    assert saved.phase == EncounterPhase.SOCIAL
