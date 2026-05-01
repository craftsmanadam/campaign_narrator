"""Unit tests for ModuleOrchestrator."""

from __future__ import annotations

import dataclasses
from dataclasses import replace
from unittest.mock import MagicMock

from campaignnarrator.agents.module_generator_agent import (
    ModuleGenerationResult,
    ModuleGeneratorAgent,
)
from campaignnarrator.agents.narrator_agent import NarratorAgent
from campaignnarrator.domain.models import (
    ActorRegistry,
    ActorState,
    CampaignState,
    EncounterPhase,
    EncounterReady,
    EncounterState,
    GameState,
    Milestone,
    MilestoneAchieved,
    ModuleState,
    NpcPresence,
    NpcPresenceStatus,
)
from campaignnarrator.orchestrators.encounter_planner_orchestrator import (
    EncounterPlannerOrchestrator,
)
from campaignnarrator.orchestrators.module_orchestrator import (
    ModuleOrchestrator,
    ModuleOrchestratorAgents,
    ModuleOrchestratorRepositories,
)
from campaignnarrator.repositories.compendium_repository import CompendiumRepository
from campaignnarrator.repositories.game_state_repository import GameStateRepository
from campaignnarrator.repositories.narrative_memory_repository import (
    NarrativeMemoryRepository,
)

from tests.conftest import ScriptedIO
from tests.fixtures.fighter_talia import TALIA
from tests.fixtures.goblin_scout import make_goblin_scout


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
        actor_ids=("pc:player",),
        player_actor_id="pc:player",
        outcome=outcome,
    )


def _make_planner_encounter() -> EncounterState:
    """Return an encounter the planner would create (different id to avoid loops)."""
    return EncounterState(
        encounter_id="module-001-enc-new",
        phase=EncounterPhase.SCENE_OPENING,
        setting="A new scene.",
    )


def _make_game_state(
    *,
    module: ModuleState | None = None,
    encounter: EncounterState | None = None,
    campaign: CampaignState | None = None,
) -> GameState:
    player_registry = ActorRegistry(actors={"pc:player": _make_player()})
    return GameState(
        campaign=campaign or _make_campaign(),
        module=module if module is not None else _make_module(),
        encounter=encounter,
        actor_registry=player_registry,
    )


def _make_orchestrator(
    *,
    module: ModuleState | None = None,
    active_encounter: EncounterState | None = None,
    encounter_ready: EncounterReady | MilestoneAchieved | None = None,
    summarize_returns: str = "Rich encounter summary.",
) -> tuple[
    ModuleOrchestrator,
    MagicMock,  # mock_narrator
    MagicMock,  # mock_encounter_orch
    MagicMock,  # mock_narrative_repo
    MagicMock,  # mock_game_state_repo
]:
    io = MagicMock()

    mock_narrative_repo = MagicMock(spec=NarrativeMemoryRepository)
    mock_compendium_repo = MagicMock(spec=CompendiumRepository)
    mock_game_state_repo = MagicMock(spec=GameStateRepository)

    resolved_module = module or _make_module()

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

    # Default game state: module loaded, no active encounter, player in registry.
    player_registry = ActorRegistry(actors={"pc:player": _make_player()})
    mock_game_state_repo.load.return_value = GameState(
        campaign=_make_campaign(),
        module=resolved_module,
        encounter=active_encounter,
        actor_registry=player_registry,
    )

    repos = ModuleOrchestratorRepositories(
        narrative=mock_narrative_repo,
        compendium=mock_compendium_repo,
        game_state=mock_game_state_repo,
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
        mock_narrator,
        mock_encounter_orch,
        mock_narrative_repo,
        mock_game_state_repo,
    )


def test_module_orchestrator_instantiates() -> None:
    orch, _, _, mock_narrative_repo, _ = _make_orchestrator()
    assert orch._repos.narrative is mock_narrative_repo


def test_run_with_in_progress_encounter_calls_run_encounter() -> None:
    """Step 2c: active encounter not complete → resume it."""
    active = _make_active_encounter(phase=EncounterPhase.SCENE_OPENING)
    orch, _, mock_enc_orch, _, _ = _make_orchestrator(active_encounter=active)
    orch.run(game_state=_make_game_state(encounter=active))
    mock_enc_orch.run_encounter.assert_called_once_with(
        encounter_id="module-001-enc-001", campaign_id="c-1"
    )


def test_run_with_no_active_encounter_calls_encounter_planner() -> None:
    """No active encounter → encounter_planner.prepare() is called."""
    orch, _, _, _, _ = _make_orchestrator(active_encounter=None)
    orch.run(game_state=_make_game_state())
    orch._agents.encounter_planner.prepare.assert_called_once()


def test_run_with_no_active_encounter_calls_run_encounter() -> None:
    """No active encounter → run_encounter is called with planner's encounter_id."""
    orch, _, mock_enc_orch, _, _ = _make_orchestrator(active_encounter=None)
    orch.run(game_state=_make_game_state())
    mock_enc_orch.run_encounter.assert_called_once_with(
        encounter_id="module-001-enc-new", campaign_id="c-1"
    )


def test_run_does_not_forward_encounter_output_to_io() -> None:
    """Encounter output is displayed live in EncounterOrchestrator; not forwarded."""
    active = _make_active_encounter(phase=EncounterPhase.SCENE_OPENING)
    orch, _, mock_enc_orch, _, _ = _make_orchestrator(active_encounter=active)
    mock_enc_orch.run_encounter.return_value = MagicMock(output_text="Docks at dusk.")
    orch.run(game_state=_make_game_state())
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
    orch, mock_narrator, _, _, _ = _make_orchestrator(
        active_encounter=active,
        module=_make_module(),
    )
    orch.run(game_state=_make_game_state(module=_make_module(), encounter=active))
    mock_narrator.summarize_encounter.assert_called_once()


def test_run_with_completed_encounter_stores_narrative() -> None:
    active = _make_active_encounter(
        phase=EncounterPhase.ENCOUNTER_COMPLETE,
        outcome="Cultist subdued.",
    )
    orch, _, _, mock_narrative_repo, _ = _make_orchestrator(
        active_encounter=active,
        module=_make_module(),
        summarize_returns="Rich summary text.",
    )
    orch.run(game_state=_make_game_state(module=_make_module(), encounter=active))
    mock_narrative_repo.store_narrative.assert_called_once()
    args = mock_narrative_repo.store_narrative.call_args
    assert args[0][0] == "Rich summary text."
    assert args[0][1]["event_type"] == "encounter_summary"


def test_run_with_completed_encounter_clears_encounter() -> None:
    """Archiving a completed encounter stages encounter=None and calls persist."""
    active = _make_active_encounter(
        phase=EncounterPhase.ENCOUNTER_COMPLETE,
        outcome="Cultist subdued.",
    )
    orch, _, _, _, mock_game_state_repo = _make_orchestrator(
        active_encounter=active,
        module=_make_module(),
    )
    orch.run(game_state=_make_game_state(module=_make_module(), encounter=active))
    mock_game_state_repo.persist.assert_called()


def test_run_with_completed_encounter_saves_updated_module() -> None:
    active = _make_active_encounter(
        phase=EncounterPhase.ENCOUNTER_COMPLETE,
        outcome="Cultist subdued.",
    )
    orch, _, _, _, mock_game_state_repo = _make_orchestrator(
        active_encounter=active,
        module=_make_module(),
        summarize_returns="Session notes.",
    )
    orch.run(game_state=_make_game_state(module=_make_module(), encounter=active))
    # persist() called at least once (archive)
    assert mock_game_state_repo.persist.call_count >= 1
    # The persisted game state carries the updated module with the completed encounter id
    all_staged = [call[0][0] for call in mock_game_state_repo.persist.call_args_list]
    archived = next(
        gs
        for gs in all_staged
        if gs.module is not None
        and "module-001-enc-001" in gs.module.completed_encounter_ids
    )
    assert archived is not None


def test_run_archive_increments_next_encounter_index() -> None:
    """_archive_encounter must bump next_encounter_index by 1."""
    _initial_index = 2
    active = _make_active_encounter(
        phase=EncounterPhase.ENCOUNTER_COMPLETE,
        outcome="Done.",
    )
    orch, _, _, _, mock_game_state_repo = _make_orchestrator(
        active_encounter=active,
        module=_make_module(next_encounter_index=_initial_index),
    )
    orch.run(
        game_state=_make_game_state(
            module=_make_module(next_encounter_index=_initial_index),
            encounter=active,
        )
    )
    all_staged = [call[0][0] for call in mock_game_state_repo.persist.call_args_list]
    archived = next(
        gs
        for gs in all_staged
        if gs.module is not None
        and "module-001-enc-001" in gs.module.completed_encounter_ids
    )
    assert archived.module.next_encounter_index == _initial_index + 1


def test_run_milestone_achieved_saves_new_module() -> None:
    """MilestoneAchieved from planner → new module is generated and persisted."""
    active = _make_active_encounter(
        phase=EncounterPhase.ENCOUNTER_COMPLETE,
        outcome="Malachar defeated.",
    )
    orch, _, _, _, mock_game_state_repo = _make_orchestrator(
        active_encounter=active,
        module=_make_module(),
        encounter_ready=MilestoneAchieved(),
    )

    module_result = ModuleGenerationResult(
        title="The Cult Revealed",
        summary="The sea cult unmasked.",
        guiding_milestone_id="m2",
    )
    orch._agents.module_generator.generate.return_value = module_result

    orch.run(game_state=_make_game_state(module=_make_module()))

    all_staged = [call[0][0] for call in mock_game_state_repo.persist.call_args_list]
    new_module = next(
        (
            gs.module
            for gs in all_staged
            if gs.module and gs.module.module_id == "module-002"
        ),
        None,
    )
    assert new_module is not None
    assert new_module.title == "The Cult Revealed"


def test_run_returns_early_when_module_not_found() -> None:
    orch, _, mock_enc_orch, _, mock_game_state_repo = _make_orchestrator()
    # Override default game state: module is absent
    mock_game_state_repo.load.return_value = GameState(
        module=None,
        actor_registry=ActorRegistry(actors={"pc:player": _make_player()}),
    )
    orch.run(
        game_state=GameState(
            campaign=_make_campaign(),
            module=None,
            actor_registry=ActorRegistry(actors={"pc:player": _make_player()}),
        )
    )
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
    orch, _, _, _, mock_game_state_repo = _make_orchestrator(
        active_encounter=active,
        module=_make_module(),
        encounter_ready=MilestoneAchieved(),
    )
    mock_game_state_repo.load.return_value = GameState(
        campaign=campaign,
        module=_make_module(),
        encounter=active,
        actor_registry=ActorRegistry(actors={"pc:player": _make_player()}),
    )
    orch.run(game_state=_make_game_state(campaign=campaign, module=_make_module()))
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
    orch, _, _, _, _ = _make_orchestrator(
        active_encounter=active,
        module=_make_module(next_encounter_index=_initial_index),
    )
    orch.run(
        game_state=_make_game_state(
            module=_make_module(next_encounter_index=_initial_index),
            encounter=active,
        )
    )
    prepare_call = orch._agents.encounter_planner.prepare.call_args
    passed_module = prepare_call[1]["module"]
    assert passed_module.next_encounter_index == _initial_index + 1


def test_run_planner_receive_correct_campaign_and_player() -> None:
    """prepare() must be called with the correct campaign and player."""
    orch, _, _, _, _ = _make_orchestrator(active_encounter=None)
    campaign = _make_campaign()
    expected_player = _make_player()
    initial_gs = GameState(
        campaign=campaign,
        module=_make_module(),
        encounter=None,
        actor_registry=ActorRegistry(actors={"pc:player": expected_player}),
    )
    orch.run(game_state=initial_gs)
    prepare_call = orch._agents.encounter_planner.prepare.call_args
    assert prepare_call[1]["campaign"] is campaign
    assert prepare_call[1]["player"] is expected_player


def test_run_reads_player_from_registry() -> None:
    """ModuleOrchestrator.run() no longer accepts player param; reads from registry."""
    orch, _, _, _, _ = _make_orchestrator(active_encounter=None)
    # Should not raise — player is in registry (seeded by _make_orchestrator)
    orch.run(game_state=_make_game_state())


def test_run_with_scripted_io_module_not_found_no_crash() -> None:
    """ModuleOrchestrator must not crash when module is absent."""
    io = ScriptedIO([])
    mock_game_state_repo = MagicMock(spec=GameStateRepository)
    mock_game_state_repo.load.return_value = GameState(
        module=None,
        actor_registry=ActorRegistry(actors={"pc:player": _make_player()}),
    )
    mock_encounter_planner = MagicMock(spec=EncounterPlannerOrchestrator)
    repos = ModuleOrchestratorRepositories(
        narrative=MagicMock(spec=NarrativeMemoryRepository),
        compendium=MagicMock(spec=CompendiumRepository),
        game_state=mock_game_state_repo,
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
    orch.run(
        game_state=GameState(
            campaign=_make_campaign(),
            module=None,
            actor_registry=ActorRegistry(actors={"pc:player": _make_player()}),
        )
    )
    mock_encounter_planner.prepare.assert_not_called()


def test_archive_encounter_calls_persist() -> None:
    """_archive_encounter() must call persist() to flush registry and reset cache."""
    active = _make_active_encounter(
        phase=EncounterPhase.ENCOUNTER_COMPLETE,
        outcome="victory",
    )
    orch, _, _, _, mock_game_state_repo = _make_orchestrator(active_encounter=active)
    orch.run(game_state=_make_game_state(encounter=active))
    mock_game_state_repo.persist.assert_called_once()


def test_run_player_quits_mid_encounter_does_not_archive() -> None:
    """If player quits (encounter not complete after run), no archiving occurs."""
    active = _make_active_encounter(phase=EncounterPhase.COMBAT)
    orch, mock_narrator, _, _, mock_game_state_repo = _make_orchestrator(
        active_encounter=active
    )
    # After run_encounter, game state returns COMBAT phase (player quit, not complete)
    mock_game_state_repo.load.return_value = GameState(
        module=_make_module(),
        encounter=active,
        actor_registry=ActorRegistry(actors={"pc:player": _make_player()}),
    )
    orch.run(game_state=_make_game_state())
    mock_narrator.summarize_encounter.assert_not_called()
    mock_game_state_repo.persist.assert_not_called()


def test_run_encounter_completes_during_run_triggers_archive() -> None:
    """Encounter that reaches ENCOUNTER_COMPLETE during run_encounter is archived."""
    active = _make_active_encounter(phase=EncounterPhase.SCENE_OPENING)
    completed = _make_active_encounter(
        phase=EncounterPhase.ENCOUNTER_COMPLETE, outcome="victory"
    )
    orch, mock_narrator, _, _, mock_game_state_repo = _make_orchestrator(
        active_encounter=active
    )
    # After run_encounter, game state cache holds the completed encounter
    mock_game_state_repo.load.return_value = GameState(
        campaign=_make_campaign(),
        module=_make_module(),
        encounter=completed,
        actor_registry=ActorRegistry(actors={"pc:player": _make_player()}),
    )
    orch.run(game_state=_make_game_state(encounter=active))
    mock_narrator.summarize_encounter.assert_called_once()
    mock_game_state_repo.persist.assert_called()


# ─── _archive_encounter registry sync and transition ─────────────────────────


def _make_completed_encounter(
    *,
    traveling_actor_ids: tuple[str, ...] = (),
    next_location_hint: str | None = None,
) -> EncounterState:
    """ENCOUNTER_COMPLETE state with the player + one NPC actor."""
    presence = NpcPresence(
        actor_id="npc:goblin",
        display_name="Goblin Scout",
        description="a goblin",
        name_known=False,
        status=NpcPresenceStatus.AVAILABLE,
    )
    return dataclasses.replace(
        _make_active_encounter(
            phase=EncounterPhase.ENCOUNTER_COMPLETE,
            outcome="goblin fled",
        ),
        actor_ids=("pc:player", "npc:goblin"),
        npc_presences=(presence,),
        traveling_actor_ids=traveling_actor_ids,
        next_location_hint=next_location_hint,
    )


def test_prepare_receives_post_encounter_player_not_pre_encounter_snapshot() -> None:
    """Player passed to prepare() reflects what was in the game_state on entry,
    not a stale pre-encounter snapshot loaded from a separate source."""
    post_encounter_hp = 3
    post_encounter_player = dataclasses.replace(
        _make_player(), hp_current=post_encounter_hp
    )

    active = _make_completed_encounter()
    orch, _, _, _, mock_game_state_repo = _make_orchestrator(active_encounter=active)

    # Pass the post-encounter registry in the initial game_state (reflects what the
    # EncounterOrchestrator persisted before returning ENCOUNTER_COMPLETE).
    initial_gs = GameState(
        campaign=_make_campaign(),
        module=_make_module(),
        encounter=active,
        actor_registry=ActorRegistry(actors={"pc:player": post_encounter_player}),
    )
    post_state = GameState(
        campaign=_make_campaign(),
        module=_make_module(),
        actor_registry=ActorRegistry(actors={"pc:player": post_encounter_player}),
    )
    # 1 load: after _prepare_and_run's run_encounter()
    mock_game_state_repo.load.return_value = post_state

    orch.run(game_state=initial_gs)

    call_kwargs = orch._agents.encounter_planner.prepare.call_args.kwargs
    assert call_kwargs["player"].hp_current == post_encounter_hp


def test_archive_encounter_syncs_player_and_npcs_to_registry() -> None:
    """_archive_encounter calls persist() to flush the already-updated registry."""
    active = _make_completed_encounter()
    orch, _, _, _, mock_game_state_repo = _make_orchestrator(active_encounter=active)
    player_registry = ActorRegistry(actors={"pc:player": _make_player()})
    active_gs = GameState(
        campaign=_make_campaign(),
        module=_make_module(),
        encounter=active,
        actor_registry=player_registry,
    )
    post_persist_gs = GameState(
        campaign=_make_campaign(),
        module=_make_module(),
        encounter=None,
        actor_registry=player_registry,
    )
    # 1 load: after _prepare_and_run's run_encounter()
    mock_game_state_repo.load.return_value = post_persist_gs

    orch.run(game_state=active_gs)

    mock_game_state_repo.persist.assert_called_once()


def test_archive_encounter_builds_transition_with_traveling_actors() -> None:
    """When encounter has traveling_actor_ids, transition passed to planner contains them."""
    player = _make_player()
    elara = make_goblin_scout("npc:elara", "Elara")
    elara_presence = NpcPresence(
        actor_id="npc:elara",
        display_name="Elara",
        description="the herbalist",
        name_known=True,
        status=NpcPresenceStatus.INTERACTED,
    )
    active = dataclasses.replace(
        _make_active_encounter(phase=EncounterPhase.ENCOUNTER_COMPLETE, outcome="done"),
        actor_ids=("pc:player", "npc:elara"),
        npc_presences=(elara_presence,),
        traveling_actor_ids=("npc:elara",),
        next_location_hint="Cave of Whispers",
    )
    orch, _, _, _, mock_game_state_repo = _make_orchestrator(active_encounter=active)
    # Seed registry with both actors so _archive_encounter can read them.
    full_registry = ActorRegistry(actors={"pc:player": player, "npc:elara": elara})
    active_gs = GameState(
        campaign=_make_campaign(),
        module=_make_module(),
        encounter=active,
        actor_registry=full_registry,
    )
    post_persist_gs = GameState(
        campaign=_make_campaign(),
        module=_make_module(),
        encounter=None,
        actor_registry=full_registry,
    )
    # 1 load: after _prepare_and_run's run_encounter()
    mock_game_state_repo.load.return_value = post_persist_gs

    orch.run(game_state=active_gs)

    call_kwargs = orch._agents.encounter_planner.prepare.call_args.kwargs
    transition = call_kwargs.get("transition")
    assert transition is not None
    assert transition.from_encounter_id == active.encounter_id
    assert "npc:elara" in transition.traveling_actors
    assert transition.next_location_hint == "Cave of Whispers"


def test_run_loop_call_site_1_threads_transition_to_prepare() -> None:
    """When active encounter is ENCOUNTER_COMPLETE on entry, transition reaches prepare."""
    player = _make_player()
    elara = make_goblin_scout("npc:elara", "Elara")
    elara_presence = NpcPresence(
        actor_id="npc:elara",
        display_name="Elara",
        description="the herbalist",
        name_known=True,
        status=NpcPresenceStatus.INTERACTED,
    )
    active = dataclasses.replace(
        _make_active_encounter(phase=EncounterPhase.ENCOUNTER_COMPLETE, outcome="done"),
        actor_ids=("pc:player", "npc:elara"),
        npc_presences=(elara_presence,),
        traveling_actor_ids=("npc:elara",),
        next_location_hint="The cave",
    )
    orch, _, _, _, mock_game_state_repo = _make_orchestrator(active_encounter=active)
    full_registry = ActorRegistry(actors={"pc:player": player, "npc:elara": elara})
    active_gs = GameState(
        campaign=_make_campaign(),
        module=_make_module(),
        encounter=active,
        actor_registry=full_registry,
    )
    post_persist_gs = GameState(
        campaign=_make_campaign(),
        module=_make_module(),
        encounter=None,
        actor_registry=full_registry,
    )
    # 1 load: after _prepare_and_run's run_encounter()
    mock_game_state_repo.load.return_value = post_persist_gs

    orch.run(game_state=active_gs)

    call_kwargs = orch._agents.encounter_planner.prepare.call_args.kwargs
    transition = call_kwargs.get("transition")
    assert transition is not None
    assert transition.from_encounter_id == active.encounter_id


def test_run_loop_call_site_2_threads_transition_to_prepare() -> None:
    """When encounter completes during run_encounter, transition reaches prepare."""
    player = _make_player()
    elara = make_goblin_scout("npc:elara", "Elara")
    elara_presence = NpcPresence(
        actor_id="npc:elara",
        display_name="Elara",
        description="the herbalist",
        name_known=True,
        status=NpcPresenceStatus.INTERACTED,
    )
    # Start with an in-progress encounter
    active = _make_active_encounter(phase=EncounterPhase.SCENE_OPENING)
    # After run_encounter, memory returns a completed encounter with traveling actors
    completed = dataclasses.replace(
        _make_active_encounter(
            phase=EncounterPhase.ENCOUNTER_COMPLETE, outcome="victory"
        ),
        actor_ids=("pc:player", "npc:elara"),
        npc_presences=(elara_presence,),
        traveling_actor_ids=("npc:elara",),
        next_location_hint="The harbor",
    )
    orch, _, _, _, mock_game_state_repo = _make_orchestrator(active_encounter=active)
    mock_game_state_repo.load.return_value = GameState(
        campaign=_make_campaign(),
        module=_make_module(),
        encounter=completed,
        actor_registry=ActorRegistry(actors={"pc:player": player, "npc:elara": elara}),
    )

    orch.run(game_state=_make_game_state(encounter=active))

    call_kwargs = orch._agents.encounter_planner.prepare.call_args.kwargs
    transition = call_kwargs.get("transition")
    assert transition is not None
    assert transition.from_encounter_id == completed.encounter_id


def test_archive_encounter_transition_empty_when_no_traveling_actors() -> None:
    """When traveling_actor_ids is empty, transition is passed but has no traveling actors."""
    active = _make_completed_encounter(traveling_actor_ids=())
    orch, _, _, _, mock_game_state_repo = _make_orchestrator(active_encounter=active)
    player_registry = ActorRegistry(actors={"pc:player": _make_player()})
    active_gs = GameState(
        campaign=_make_campaign(),
        module=_make_module(),
        encounter=active,
        actor_registry=player_registry,
    )
    post_persist_gs = GameState(
        campaign=_make_campaign(),
        module=_make_module(),
        encounter=None,
        actor_registry=player_registry,
    )
    # 1 load: after _prepare_and_run's run_encounter()
    mock_game_state_repo.load.return_value = post_persist_gs

    orch.run(game_state=active_gs)

    call_kwargs = orch._agents.encounter_planner.prepare.call_args.kwargs
    transition = call_kwargs.get("transition")
    assert transition is not None
    assert len(transition.traveling_actors) == 0
    assert transition.traveling_actor_ids == ()


# ---------------------------------------------------------------------------
# GameStateRepository path
# ---------------------------------------------------------------------------


def _make_orchestrator_with_gs_repo(
    *,
    active_encounter: EncounterState | None = None,
    gs_after_run: GameState | None = None,
) -> tuple[ModuleOrchestrator, MagicMock, MagicMock]:
    """Build a ModuleOrchestrator wired with a GameStateRepository mock."""
    player_registry = ActorRegistry(actors={"pc:player": _make_player()})
    default_gs = GameState(
        campaign=_make_campaign(),
        module=_make_module(),
        encounter=active_encounter,
        actor_registry=player_registry,
    )
    gs_cache: list[GameState] = [default_gs]

    gs_repo = MagicMock(spec=GameStateRepository)
    gs_repo.load.side_effect = lambda: gs_cache[-1]
    gs_repo.persist.side_effect = gs_cache.append

    if gs_after_run is not None:
        gs_cache.append(gs_after_run)

    mock_enc_orch = MagicMock()
    mock_enc_orch.run_encounter.return_value = None

    mock_narrative_repo = MagicMock(spec=NarrativeMemoryRepository)

    mock_narrator = MagicMock(spec=NarratorAgent)
    mock_narrator.summarize_encounter.return_value = "Summary."

    mock_planner = MagicMock(spec=EncounterPlannerOrchestrator)
    mock_planner.prepare.return_value = EncounterReady(
        encounter_state=_make_planner_encounter(),
        module=_make_module(),
    )

    repos = ModuleOrchestratorRepositories(
        narrative=mock_narrative_repo,
        compendium=MagicMock(spec=CompendiumRepository),
        game_state=gs_repo,
    )
    agents = ModuleOrchestratorAgents(
        narrator=mock_narrator,
        module_generator=MagicMock(),
        encounter_planner=mock_planner,
    )
    orch = ModuleOrchestrator(
        io=MagicMock(),
        repositories=repos,
        agents=agents,
        encounter_orchestrator=mock_enc_orch,
    )
    return orch, gs_repo, mock_narrative_repo


def test_run_loop_uses_game_state_repo_when_set() -> None:
    """_run_loop must call game_state_repo.load()."""
    orch, gs_repo, _ = _make_orchestrator_with_gs_repo()
    orch.run(game_state=_make_game_state())
    gs_repo.load.assert_called()


def test_archive_encounter_persists_via_game_state_repo_when_set() -> None:
    """_archive_encounter must call game_state_repo.persist(), not narrative.persist()."""
    completed = _make_active_encounter(phase=EncounterPhase.ENCOUNTER_COMPLETE)
    orch, gs_repo, mock_narrative_repo = _make_orchestrator_with_gs_repo(
        active_encounter=completed,
    )
    orch.run(game_state=_make_game_state(encounter=completed))
    gs_repo.persist.assert_called()
    mock_narrative_repo.persist.assert_not_called()
