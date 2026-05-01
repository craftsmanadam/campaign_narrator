"""Unit tests for EncounterPlannerOrchestrator."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from campaignnarrator.agents.encounter_planner_agent import EncounterPlannerAgent
from campaignnarrator.domain.models import (
    ActorState,
    ActorType,
    CampaignState,
    DivergenceAssessment,
    EncounterNpc,
    EncounterReady,
    EncounterRecoveryResult,
    EncounterTemplate,
    EncounterTransition,
    GameState,
    Milestone,
    MilestoneAchieved,
    ModuleState,
    NpcPresence,
    NpcPresenceStatus,
)
from campaignnarrator.orchestrators.encounter_planner_orchestrator import (
    EncounterPlannerOrchestrator,
    _OutOfBoundsTemplateError,
)
from campaignnarrator.repositories.game_state_repository import GameStateRepository
from campaignnarrator.repositories.narrative_memory_repository import (
    NarrativeMemoryRepository,
)

from tests.fixtures.goblin_scout import make_goblin_scout

# ─── Shared fixtures ─────────────────────────────────────────────────────────


def _make_player(level: int = 1) -> ActorState:
    return ActorState(
        actor_id="pc:aldric",
        name="Aldric",
        actor_type=ActorType.PC,
        hp_max=12,
        hp_current=12,
        armor_class=16,
        strength=17,
        dexterity=14,
        constitution=14,
        intelligence=8,
        wisdom=10,
        charisma=12,
        proficiency_bonus=2,
        initiative_bonus=2,
        speed=30,
        attacks_per_action=1,
        action_options=("Attack",),
        ac_breakdown=(),
        level=level,
    )


def _make_campaign() -> CampaignState:
    return CampaignState(
        campaign_id="c1",
        name="The Cursed Coast",
        setting="A dark coastal city.",
        narrator_personality="Grim and dramatic.",
        hidden_goal="Awaken the sea god.",
        bbeg_name="Malachar",
        bbeg_description="A lich.",
        milestones=(
            Milestone(
                milestone_id="m1",
                title="First Blood",
                description="Enter city.",
            ),
        ),
        current_milestone_index=0,
        starting_level=1,
        target_level=5,
        player_brief="I want dark coastal horror.",
        player_actor_id="pc:aldric",
    )


def _make_module(**kwargs) -> ModuleState:  # type: ignore[no-untyped-def]
    defaults: dict[str, object] = {
        "module_id": "module-001",
        "campaign_id": "c1",
        "title": "The Dockside Murders",
        "summary": "Bodies wash ashore nightly.",
        "guiding_milestone_id": "m1",
    }
    defaults.update(kwargs)
    return ModuleState(**defaults)  # type: ignore[arg-type]


def _make_npc(template_npc_id: str = "goblin-a") -> EncounterNpc:
    return EncounterNpc(
        template_npc_id=template_npc_id,
        display_name="Goblin A",
        role="scout",
        description="Small green creature.",
        monster_name="Goblin",
        stat_source="monster_compendium",
        cr=0.25,
    )


def _make_template(
    template_id: str = "enc-001",
    order: int = 0,
) -> EncounterTemplate:
    return EncounterTemplate(
        template_id=template_id,
        order=order,
        setting="The docks.",
        purpose="Intro.",
        npcs=(_make_npc(),),
        prerequisites=(),
        expected_outcomes=(),
        downstream_dependencies=(),
    )


def _make_simple_npc_template(
    npc_template_id: str = "goblin-scout",
) -> EncounterTemplate:
    """Template backed by a simple_npc stat source (no monster compendium needed)."""
    return EncounterTemplate(
        template_id=f"enc-{npc_template_id}",
        order=0,
        setting="A dark alley.",
        purpose="Intro.",
        npcs=(
            EncounterNpc(
                template_npc_id=npc_template_id,
                display_name="Goblin Scout",
                role="scout",
                description="a small goblin",
                monster_name=None,
                stat_source="simple_npc",
                cr=0.25,
                name_known=False,
            ),
        ),
        prerequisites=(),
        expected_outcomes=(),
        downstream_dependencies=(),
    )


def _make_transition(
    actor_id: str = "npc:elara",
    display_name: str = "Elara",
) -> EncounterTransition:
    """Build a minimal EncounterTransition carrying one traveling actor."""
    actor = make_goblin_scout(actor_id, display_name)
    presence = NpcPresence(
        actor_id=actor_id,
        display_name=display_name,
        description="the herbalist",
        name_known=True,
        status=NpcPresenceStatus.INTERACTED,
    )
    return EncounterTransition(
        from_encounter_id="enc-001",
        next_location_hint="Cave of Whispers",
        traveling_actor_ids=(actor_id,),
        traveling_actors={actor_id: actor},
        traveling_presences=(presence,),
    )


def _make_orchestrator(
    data_root: Path,
    *,
    narrative: MagicMock | None = None,
    game_state: MagicMock | None = None,
    planner: MagicMock | None = None,
) -> tuple[EncounterPlannerOrchestrator, MagicMock, MagicMock, MagicMock]:
    """Return (orchestrator, narrative_mock, game_state_mock, planner_mock)."""
    narrative = narrative or MagicMock(spec=NarrativeMemoryRepository)
    game_state = game_state or MagicMock(spec=GameStateRepository)
    planner = planner or MagicMock(spec=EncounterPlannerAgent)
    orch = EncounterPlannerOrchestrator(
        data_root=data_root,
        narrative=narrative,
        game_state=game_state,
        planner=planner,
    )
    return orch, narrative, game_state, planner


# ─── Empty plan detection ─────────────────────────────────────────────────────


class TestEmptyPlanDetection:
    def test_empty_planned_encounters_triggers_plan_call(self, tmp_path: Path) -> None:
        """When planned_encounters is empty, prepare() calls plan_encounters()."""
        templates = (_make_template("enc-001"), _make_template("enc-002", order=1))
        orch, narrative, game_state, planner = _make_orchestrator(tmp_path)
        planner.plan_encounters.return_value = templates
        planner.assess_divergence.return_value = MagicMock(
            status="viable",
            milestone_achieved=False,
        )
        narrative.retrieve_relevant.return_value = []
        game_state.load.return_value = GameState()

        module = _make_module()
        assert module.planned_encounters == ()

        orch.prepare(
            module=module,
            campaign=_make_campaign(),
            player=_make_player(),
        )

        planner.plan_encounters.assert_called_once()

    def test_empty_plan_saves_module_before_divergence_check(
        self, tmp_path: Path
    ) -> None:
        """After planning, the updated module is saved before proceeding."""
        templates = (_make_template(),)
        orch, narrative, game_state, planner = _make_orchestrator(tmp_path)
        planner.plan_encounters.return_value = templates
        planner.assess_divergence.return_value = DivergenceAssessment(
            status="viable", reason="ok", milestone_achieved=False
        )
        narrative.retrieve_relevant.return_value = []
        game_state.load.return_value = GameState()

        orch.prepare(
            module=_make_module(),
            campaign=_make_campaign(),
            player=_make_player(),
        )

        # First persist is from _ensure_planned; _recover_if_needed skips (viable)
        # The second persist is from _instantiate (encounter + actors).
        # We check the first persist call contains the planned module.
        first_stage_call = game_state.persist.call_args_list[0][0][0]
        assert len(first_stage_call.module.planned_encounters) == 1
        assert first_stage_call.module.next_encounter_index == 0

    def test_plan_encounters_receives_narrative_context_from_memory(
        self, tmp_path: Path
    ) -> None:
        """plan_encounters() receives narrative context from MemoryRepository."""
        templates = (_make_template(),)
        orch, narrative, game_state, planner = _make_orchestrator(tmp_path)
        planner.plan_encounters.return_value = templates
        planner.assess_divergence.return_value = DivergenceAssessment(
            status="viable", reason="ok", milestone_achieved=False
        )
        narrative.retrieve_relevant.return_value = ["A prior narrative entry."]
        game_state.load.return_value = GameState()

        orch.prepare(
            module=_make_module(),
            campaign=_make_campaign(),
            player=_make_player(),
        )

        call_kwargs = planner.plan_encounters.call_args[1]
        assert "A prior narrative entry." in call_kwargs["narrative_context"]

    def test_non_empty_plan_does_not_call_plan_encounters(self, tmp_path: Path) -> None:
        """When planned_encounters is populated, plan_encounters() is NOT called."""
        orch, narrative, game_state, planner = _make_orchestrator(tmp_path)
        planner.assess_divergence.return_value = DivergenceAssessment(
            status="viable", reason="ok", milestone_achieved=False
        )
        narrative.retrieve_relevant.return_value = []
        game_state.load.return_value = GameState()

        module = _make_module(
            planned_encounters=(_make_template(),),
            next_encounter_index=0,
        )

        orch.prepare(
            module=module,
            campaign=_make_campaign(),
            player=_make_player(),
        )

        planner.plan_encounters.assert_not_called()


# ─── Out-of-bounds index ──────────────────────────────────────────────────────


class TestOutOfBoundsIndex:
    def test_index_at_end_of_list_triggers_milestone_only_check(
        self, tmp_path: Path
    ) -> None:
        """When next_encounter_index >= len(planned_encounters), run milestone check."""
        orch, narrative, _, planner = _make_orchestrator(tmp_path)
        narrative.retrieve_relevant.return_value = []

        milestone_assessment = DivergenceAssessment(
            status="milestone_achieved",
            reason="Module complete.",
            milestone_achieved=True,
        )
        planner.assess_divergence.return_value = milestone_assessment

        module = _make_module(
            planned_encounters=(_make_template(),),
            next_encounter_index=1,  # out of bounds (only 1 template at index 0)
        )

        result = orch.prepare(
            module=module,
            campaign=_make_campaign(),
            player=_make_player(),
        )

        assert isinstance(result, MilestoneAchieved)
        # assess_divergence must be called with template=None (milestone-only check)
        call_kwargs = planner.assess_divergence.call_args[1]
        assert call_kwargs["template"] is None

    def test_index_at_end_viable_status_raises_value_error(
        self, tmp_path: Path
    ) -> None:
        """Out-of-bounds index + viable status → ValueError (no template at that index)."""
        orch, narrative, _, planner = _make_orchestrator(tmp_path)
        narrative.retrieve_relevant.return_value = []

        planner.assess_divergence.return_value = DivergenceAssessment(
            status="viable",
            reason="ok",
            milestone_achieved=False,
        )

        module = _make_module(
            planned_encounters=(_make_template(),),
            next_encounter_index=1,
        )

        with pytest.raises(_OutOfBoundsTemplateError):
            orch.prepare(
                module=module,
                campaign=_make_campaign(),
                player=_make_player(),
            )


# ─── Viable path ─────────────────────────────────────────────────────────────


class TestViablePath:
    def test_viable_path_calls_instantiate(self, tmp_path: Path) -> None:
        """Viable assessment → proceed directly to instantiation, returns EncounterReady."""
        orch, narrative, game_state, planner = _make_orchestrator(tmp_path)
        narrative.retrieve_relevant.return_value = []
        game_state.load.return_value = GameState()

        planner.assess_divergence.return_value = DivergenceAssessment(
            status="viable",
            reason="ok",
            milestone_achieved=False,
        )

        module = _make_module(
            planned_encounters=(_make_template(),),
            next_encounter_index=0,
        )

        result = orch.prepare(
            module=module,
            campaign=_make_campaign(),
            player=_make_player(),
        )

        assert isinstance(result, EncounterReady)
        planner.recover_encounters.assert_not_called()

    def test_milestone_achieved_returns_milestone_achieved_object(
        self, tmp_path: Path
    ) -> None:
        orch, narrative, _, planner = _make_orchestrator(tmp_path)
        narrative.retrieve_relevant.return_value = []

        planner.assess_divergence.return_value = DivergenceAssessment(
            status="milestone_achieved",
            reason="Cult leader defeated.",
            milestone_achieved=True,
        )

        module = _make_module(
            planned_encounters=(_make_template(),),
            next_encounter_index=0,
        )

        result = orch.prepare(
            module=module,
            campaign=_make_campaign(),
            player=_make_player(),
        )
        assert isinstance(result, MilestoneAchieved)


# ─── Recovery branches ────────────────────────────────────────────────────────


class TestRecovery:
    def _setup_recovery(
        self,
        data_root: Path,
        status: str,
        recovery_type: str,
        updated_templates: tuple[EncounterTemplate, ...],
    ) -> tuple[EncounterPlannerOrchestrator, MagicMock, MagicMock, MagicMock]:
        orch, narrative, game_state, planner = _make_orchestrator(data_root)
        narrative.retrieve_relevant.return_value = []
        game_state.load.return_value = GameState()

        planner.assess_divergence.return_value = DivergenceAssessment(
            status=status,
            reason="NPC is dead.",
            milestone_achieved=False,
        )
        planner.recover_encounters.return_value = EncounterRecoveryResult(
            updated_templates=updated_templates,
            recovery_type=recovery_type,
        )
        return orch, narrative, game_state, planner

    def test_needs_bridge_calls_recover_and_saves_updated_module(
        self, tmp_path: Path
    ) -> None:
        bridge = _make_template("enc-bridge")
        original = _make_template("enc-001")
        orch, _, game_state, planner = self._setup_recovery(
            tmp_path,
            "needs_bridge",
            "bridge_inserted",
            (bridge, original),
        )
        module = _make_module(
            planned_encounters=(original,),
            next_encounter_index=0,
        )

        orch.prepare(
            module=module,
            campaign=_make_campaign(),
            player=_make_player(),
        )

        planner.recover_encounters.assert_called_once()
        call_kwargs = planner.recover_encounters.call_args[1]
        assert call_kwargs["recovery_type"] == "bridge_inserted"
        game_state.persist.assert_called()

    def test_needs_bridge_updated_module_has_new_templates(
        self, tmp_path: Path
    ) -> None:
        bridge = _make_template("enc-bridge")
        original = _make_template("enc-001")
        orch, _, game_state, _ = self._setup_recovery(
            tmp_path,
            "needs_bridge",
            "bridge_inserted",
            (bridge, original),
        )
        module = _make_module(
            planned_encounters=(original,),
            next_encounter_index=0,
        )

        orch.prepare(
            module=module,
            campaign=_make_campaign(),
            player=_make_player(),
        )

        # First persist call is from _recover_if_needed; inspect its .module field
        first_staged = game_state.persist.call_args_list[0][0][0]
        expected_count = 2
        assert len(first_staged.module.planned_encounters) == expected_count
        assert first_staged.module.planned_encounters[0].template_id == "enc-bridge"

    def test_needs_rebuild_replaces_current_template(self, tmp_path: Path) -> None:
        replacement = _make_template("enc-001-rebuilt")
        original = _make_template("enc-001")
        orch, _, game_state, _ = self._setup_recovery(
            tmp_path,
            "needs_rebuild",
            "template_replaced",
            (replacement,),
        )
        module = _make_module(
            planned_encounters=(original,),
            next_encounter_index=0,
        )

        orch.prepare(
            module=module,
            campaign=_make_campaign(),
            player=_make_player(),
        )

        # First persist call is from _recover_if_needed; inspect its .module field
        first_staged = game_state.persist.call_args_list[0][0][0]
        assert (
            first_staged.module.planned_encounters[0].template_id == "enc-001-rebuilt"
        )

    def test_needs_full_replan_replaces_all_remaining_templates(
        self, tmp_path: Path
    ) -> None:
        new1 = _make_template("enc-new-001")
        new2 = _make_template("enc-new-002", order=1)
        existing_done = _make_template("enc-done")
        orch, _, game_state, _ = self._setup_recovery(
            tmp_path,
            "needs_full_replan",
            "full_replan",
            (new1, new2),
        )
        # Two templates; first is done (index=1), second needs replan
        module = _make_module(
            planned_encounters=(existing_done, _make_template("enc-002", order=1)),
            next_encounter_index=1,
        )

        orch.prepare(
            module=module,
            campaign=_make_campaign(),
            player=_make_player(),
        )

        # First persist call is from _recover_if_needed; inspect its .module field
        first_staged = game_state.persist.call_args_list[0][0][0]
        assert existing_done in first_staged.module.planned_encounters
        assert new1 in first_staged.module.planned_encounters
        assert new2 in first_staged.module.planned_encounters

    def test_recovery_empty_result_escalates_to_full_replan(
        self, tmp_path: Path
    ) -> None:
        """Empty updated_templates triggers fallback to full module replan."""
        orch, narrative, game_state, planner = _make_orchestrator(tmp_path)
        narrative.retrieve_relevant.return_value = []
        game_state.load.return_value = GameState()

        planner.assess_divergence.return_value = DivergenceAssessment(
            status="needs_rebuild",
            reason="Broken.",
            milestone_achieved=False,
        )
        # First recovery returns empty; second returns valid template
        fallback_template = _make_template("enc-fallback")
        planner.recover_encounters.side_effect = [
            EncounterRecoveryResult(
                updated_templates=(),
                recovery_type="template_replaced",
            ),
            EncounterRecoveryResult(
                updated_templates=(fallback_template,),
                recovery_type="full_replan",
            ),
        ]

        module = _make_module(
            planned_encounters=(_make_template(),),
            next_encounter_index=0,
        )

        orch.prepare(
            module=module,
            campaign=_make_campaign(),
            player=_make_player(),
        )

        # recover_encounters called twice (first empty, then fallback)
        expected_call_count = 2
        assert planner.recover_encounters.call_count == expected_call_count
        second_call_kwargs = planner.recover_encounters.call_args_list[1][1]
        assert second_call_kwargs["recovery_type"] == "full_replan"


# ─── Full instantiation ───────────────────────────────────────────────────────


class TestInstantiation:
    def _make_viable_orchestrator(
        self,
        data_root: Path,
        template: EncounterTemplate | None = None,
    ) -> tuple[
        EncounterPlannerOrchestrator,
        MagicMock,
        MagicMock,
        MagicMock,
        ModuleState,
    ]:
        """Returns (orchestrator, narrative, game_state, planner, module)."""
        orch, narrative, game_state, planner = _make_orchestrator(data_root)
        narrative.retrieve_relevant.return_value = []
        game_state.load.return_value = GameState()

        planner.assess_divergence.return_value = DivergenceAssessment(
            status="viable", reason="ok", milestone_achieved=False
        )

        module = _make_module(
            planned_encounters=(template or _make_template(),),
            next_encounter_index=0,
        )
        return orch, narrative, game_state, planner, module

    def test_prepare_returns_encounter_ready(self, tmp_path: Path) -> None:
        orch, _, _, _, module = self._make_viable_orchestrator(tmp_path)
        result = orch.prepare(
            module=module, campaign=_make_campaign(), player=_make_player()
        )
        assert isinstance(result, EncounterReady)

    def test_encounter_state_has_player_actor(self, tmp_path: Path) -> None:
        orch, _, _, _, module = self._make_viable_orchestrator(tmp_path)
        player = _make_player()
        result = orch.prepare(module=module, campaign=_make_campaign(), player=player)
        assert isinstance(result, EncounterReady)
        assert player.actor_id in result.encounter_state.actor_ids

    def test_encounter_state_has_npc_actor(self, tmp_path: Path) -> None:
        orch, _, _, _, module = self._make_viable_orchestrator(tmp_path)
        result = orch.prepare(
            module=module, campaign=_make_campaign(), player=_make_player()
        )
        assert isinstance(result, EncounterReady)
        # Non-persistent NPC gets encounter-scoped ID: npc:{encounter_id}:{template_npc_id}
        # module_id="module-001", next_encounter_index=0 → encounter_id="module-001-enc-001"
        assert "npc:module-001-enc-001:goblin-a" in result.encounter_state.actor_ids

    def test_encounter_state_has_npc_presence(self, tmp_path: Path) -> None:
        orch, _, _, _, module = self._make_viable_orchestrator(tmp_path)
        result = orch.prepare(
            module=module, campaign=_make_campaign(), player=_make_player()
        )
        assert isinstance(result, EncounterReady)
        presence_ids = {p.actor_id for p in result.encounter_state.npc_presences}
        assert "npc:module-001-enc-001:goblin-a" in presence_ids

    def test_npc_actor_id_uses_template_npc_id(self, tmp_path: Path) -> None:
        """Non-persistent NPC actor_id = f'npc:{encounter_id}:{template_npc_id}' — not position-based."""
        orch, _, _, _, module = self._make_viable_orchestrator(tmp_path)
        result = orch.prepare(
            module=module, campaign=_make_campaign(), player=_make_player()
        )
        assert isinstance(result, EncounterReady)
        assert "npc:module-001-enc-001:goblin-a" in result.encounter_state.actor_ids

    def test_encounter_state_staged_to_game_state_repository(
        self, tmp_path: Path
    ) -> None:
        orch, _, game_state, _, module = self._make_viable_orchestrator(tmp_path)
        orch.prepare(module=module, campaign=_make_campaign(), player=_make_player())
        # Encounter is now persisted via game_state_repo.persist(), not encounter.save()
        game_state.persist.assert_called_once()

    def test_encounter_ready_module_is_updated_module(self, tmp_path: Path) -> None:
        """EncounterReady.module reflects any recovery updates."""
        orch, _, _, _, module = self._make_viable_orchestrator(tmp_path)
        result = orch.prepare(
            module=module, campaign=_make_campaign(), player=_make_player()
        )
        assert isinstance(result, EncounterReady)
        assert result.module.module_id == module.module_id

    def test_encounter_id_includes_module_id(self, tmp_path: Path) -> None:
        orch, _, _, _, module = self._make_viable_orchestrator(tmp_path)
        result = orch.prepare(
            module=module, campaign=_make_campaign(), player=_make_player()
        )
        assert isinstance(result, EncounterReady)
        assert "module-001" in result.encounter_state.encounter_id

    def test_scene_tone_from_template_applied_to_encounter_state(
        self, tmp_path: Path
    ) -> None:
        """EncounterState.scene_tone is set from template.scene_tone at instantiation."""
        orch, narrative, game_state, planner = _make_orchestrator(tmp_path)
        narrative.retrieve_relevant.return_value = []
        game_state.load.return_value = GameState()
        planner.assess_divergence.return_value = DivergenceAssessment(
            status="viable", reason="ok", milestone_achieved=False
        )

        template = EncounterTemplate(
            template_id="enc-001",
            order=0,
            setting="The docks.",
            purpose="Intro.",
            scene_tone="dark and ominous",
            npcs=(_make_npc(),),
            prerequisites=(),
            expected_outcomes=(),
            downstream_dependencies=(),
        )
        module = _make_module(planned_encounters=(template,), next_encounter_index=0)
        result = orch.prepare(
            module=module, campaign=_make_campaign(), player=_make_player()
        )
        assert isinstance(result, EncounterReady)
        assert result.encounter_state.scene_tone == "dark and ominous"

    def test_prepare_with_transition_adds_traveling_actor(self, tmp_path: Path) -> None:
        """Traveling actor from transition is present in the resulting encounter actors."""
        orch, _, _, _, _ = self._make_viable_orchestrator(
            tmp_path, _make_simple_npc_template()
        )
        transition = _make_transition(actor_id="npc:elara", display_name="Elara")
        result = orch.prepare(
            module=_make_module(
                planned_encounters=(_make_simple_npc_template(),),
                next_encounter_index=0,
            ),
            campaign=_make_campaign(),
            player=_make_player(),
            transition=transition,
        )
        assert isinstance(result, EncounterReady)
        assert "npc:elara" in result.encounter_state.actor_ids

    def test_prepare_with_transition_adds_traveling_presence_as_interacted(
        self, tmp_path: Path
    ) -> None:
        """Traveling NPC presence arrives with INTERACTED status regardless of original."""
        orch, _, _, _, _ = self._make_viable_orchestrator(
            tmp_path, _make_simple_npc_template()
        )
        transition = _make_transition(actor_id="npc:elara", display_name="Elara")
        result = orch.prepare(
            module=_make_module(
                planned_encounters=(_make_simple_npc_template(),),
                next_encounter_index=0,
            ),
            campaign=_make_campaign(),
            player=_make_player(),
            transition=transition,
        )
        assert isinstance(result, EncounterReady)
        presences = {p.actor_id: p for p in result.encounter_state.npc_presences}
        assert "npc:elara" in presences
        assert presences["npc:elara"].status == NpcPresenceStatus.INTERACTED

    def test_prepare_without_transition_excludes_traveling_actor(
        self, tmp_path: Path
    ) -> None:
        """Without transition, only template actors are present."""
        orch, _, _, _, _ = self._make_viable_orchestrator(
            tmp_path, _make_simple_npc_template()
        )
        result = orch.prepare(
            module=_make_module(
                planned_encounters=(_make_simple_npc_template(),),
                next_encounter_index=0,
            ),
            campaign=_make_campaign(),
            player=_make_player(),
        )
        assert isinstance(result, EncounterReady)
        assert "npc:elara" not in result.encounter_state.actor_ids

    def test_prepare_with_transition_skips_colliding_actor_id(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Traveling actor whose ID collides with a persistent template NPC is skipped."""
        # persistent=True → actor_id="npc:elara" (global, not encounter-scoped)
        # Transition also carries actor_id="npc:elara" → collision; template wins
        persistent_npc_template = EncounterTemplate(
            template_id="enc-elara",
            order=0,
            setting="The herbalist's grove.",
            purpose="Encounter the herbalist.",
            npcs=(
                EncounterNpc(
                    template_npc_id="elara",
                    display_name="Elara",
                    role="herbalist",
                    description="A traveling herbalist.",
                    monster_name=None,
                    stat_source="simple_npc",
                    cr=0.0,
                    persistent=True,
                ),
            ),
            prerequisites=(),
            expected_outcomes=(),
            downstream_dependencies=(),
        )
        orch, narrative, game_state, planner = _make_orchestrator(tmp_path)
        narrative.retrieve_relevant.return_value = []
        game_state.load.return_value = GameState()
        planner.assess_divergence.return_value = DivergenceAssessment(
            status="viable", reason="ok", milestone_achieved=False
        )
        collision_transition = _make_transition(
            actor_id="npc:elara", display_name="Elara"
        )
        with caplog.at_level(
            logging.WARNING,
            logger="campaignnarrator.orchestrators.encounter_planner_orchestrator",
        ):
            result = orch.prepare(
                module=_make_module(
                    planned_encounters=(persistent_npc_template,),
                    next_encounter_index=0,
                ),
                campaign=_make_campaign(),
                player=_make_player(),
                transition=collision_transition,
            )
        assert isinstance(result, EncounterReady)
        assert "npc:elara" in result.encounter_state.actor_ids
        assert "collision" in caplog.text.lower() or "skipping" in caplog.text.lower()

    def test_prepare_with_transition_skips_colliding_presence(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Traveling presence whose actor_id collides with a persistent template presence is skipped."""
        persistent_npc_template = EncounterTemplate(
            template_id="enc-elara",
            order=0,
            setting="The herbalist's grove.",
            purpose="Encounter the herbalist.",
            npcs=(
                EncounterNpc(
                    template_npc_id="elara",
                    display_name="Elara",
                    role="herbalist",
                    description="A traveling herbalist.",
                    monster_name=None,
                    stat_source="simple_npc",
                    cr=0.0,
                    persistent=True,
                ),
            ),
            prerequisites=(),
            expected_outcomes=(),
            downstream_dependencies=(),
        )
        orch, narrative, game_state, planner = _make_orchestrator(tmp_path)
        narrative.retrieve_relevant.return_value = []
        game_state.load.return_value = GameState()
        planner.assess_divergence.return_value = DivergenceAssessment(
            status="viable", reason="ok", milestone_achieved=False
        )
        collision_transition = _make_transition(
            actor_id="npc:elara", display_name="Elara"
        )
        with caplog.at_level(
            logging.WARNING,
            logger="campaignnarrator.orchestrators.encounter_planner_orchestrator",
        ):
            result = orch.prepare(
                module=_make_module(
                    planned_encounters=(persistent_npc_template,),
                    next_encounter_index=0,
                ),
                campaign=_make_campaign(),
                player=_make_player(),
                transition=collision_transition,
            )
        assert isinstance(result, EncounterReady)
        elara_presences = [
            p for p in result.encounter_state.npc_presences if p.actor_id == "npc:elara"
        ]
        assert len(elara_presences) == 1

    def test_cr_scaling_applied_before_instantiation(self, tmp_path: Path) -> None:
        """Over-budget NPCs are trimmed by scale_encounter_npcs before actor creation."""
        orch, narrative, game_state, planner = _make_orchestrator(tmp_path)
        narrative.retrieve_relevant.return_value = []
        game_state.load.return_value = GameState()
        planner.assess_divergence.return_value = DivergenceAssessment(
            status="viable", reason="ok", milestone_achieved=False
        )

        # Two CR 1.0 NPCs = 2.0 total; budget for level 1 = 0.5 → trimmed to 1
        over_budget_npc1 = EncounterNpc(
            template_npc_id="orc-a",
            display_name="Orc A",
            role="fighter",
            description="An orc.",
            monster_name=None,
            stat_source="simple_npc",
            cr=1.0,
        )
        over_budget_npc2 = EncounterNpc(
            template_npc_id="orc-b",
            display_name="Orc B",
            role="fighter",
            description="An orc.",
            monster_name=None,
            stat_source="simple_npc",
            cr=1.0,
        )
        template = EncounterTemplate(
            template_id="enc-001",
            order=0,
            setting="The docks.",
            purpose="Intro.",
            npcs=(over_budget_npc1, over_budget_npc2),
            prerequisites=(),
            expected_outcomes=(),
            downstream_dependencies=(),
        )
        module = _make_module(planned_encounters=(template,), next_encounter_index=0)
        result = orch.prepare(
            module=module, campaign=_make_campaign(), player=_make_player(level=1)
        )
        assert isinstance(result, EncounterReady)
        npc_actors = [
            aid for aid in result.encounter_state.actor_ids if aid.startswith("npc:")
        ]
        expected_npc_count = 1
        assert len(npc_actors) == expected_npc_count

    def test_non_persistent_npc_gets_encounter_scoped_id(self, tmp_path: Path) -> None:
        """Non-persistent NPC actor_id = npc:{encounter_id}:{template_npc_id}."""
        orch, _, _, _, module = self._make_viable_orchestrator(tmp_path)
        result = orch.prepare(
            module=module, campaign=_make_campaign(), player=_make_player()
        )
        assert isinstance(result, EncounterReady)
        # module_id="module-001", next_encounter_index=0 → encounter_id="module-001-enc-001"
        assert "npc:module-001-enc-001:goblin-a" in result.encounter_state.actor_ids
        assert "npc:goblin-a" not in result.encounter_state.actor_ids

    def test_persistent_npc_gets_global_id(self, tmp_path: Path) -> None:
        """Persistent NPC actor_id = npc:{template_npc_id} (no encounter prefix)."""
        persistent_template = EncounterTemplate(
            template_id="enc-001",
            order=0,
            setting="The docks.",
            purpose="Intro.",
            npcs=(
                EncounterNpc(
                    template_npc_id="elara",
                    display_name="Elara",
                    role="herbalist",
                    description="A traveling herbalist.",
                    monster_name=None,
                    stat_source="simple_npc",
                    cr=0.0,
                    persistent=True,
                ),
            ),
            prerequisites=(),
            expected_outcomes=(),
            downstream_dependencies=(),
        )
        orch, _, _, _, _ = self._make_viable_orchestrator(tmp_path, persistent_template)
        result = orch.prepare(
            module=_make_module(
                planned_encounters=(persistent_template,), next_encounter_index=0
            ),
            campaign=_make_campaign(),
            player=_make_player(),
        )
        assert isinstance(result, EncounterReady)
        assert "npc:elara" in result.encounter_state.actor_ids
        assert "npc:module-001-enc-001:elara" not in result.encounter_state.actor_ids

    def test_traveling_actor_retains_original_id(self, tmp_path: Path) -> None:
        """Traveling actor's ID is preserved unchanged — not scoped or renamed."""
        orch, _, _, _, _ = self._make_viable_orchestrator(
            tmp_path, _make_simple_npc_template()
        )
        transition = _make_transition(actor_id="npc:elara", display_name="Elara")
        result = orch.prepare(
            module=_make_module(
                planned_encounters=(_make_simple_npc_template(),),
                next_encounter_index=0,
            ),
            campaign=_make_campaign(),
            player=_make_player(),
            transition=transition,
        )
        assert isinstance(result, EncounterReady)
        assert "npc:elara" in result.encounter_state.actor_ids

    def test_instantiate_writes_actors_to_registry(self, tmp_path: Path) -> None:
        """_instantiate() stages a game state with a registry containing the new NPC."""
        orch, _, game_state, _, module = self._make_viable_orchestrator(tmp_path)
        orch.prepare(module=module, campaign=_make_campaign(), player=_make_player())
        assert game_state.persist.called
        updated_state = game_state.persist.call_args[0][0]
        assert "npc:module-001-enc-001:goblin-a" in updated_state.actor_registry.actors

    def test_instantiate_writes_player_to_registry(self, tmp_path: Path) -> None:
        """_instantiate() includes the player actor in the staged registry."""
        player = _make_player()
        orch, _, game_state, _, module = self._make_viable_orchestrator(tmp_path)
        orch.prepare(module=module, campaign=_make_campaign(), player=player)
        updated_state = game_state.persist.call_args[0][0]
        assert player.actor_id in updated_state.actor_registry.actors

    def test_instantiate_writes_traveling_actor_to_registry(
        self, tmp_path: Path
    ) -> None:
        """Traveling actors are included in the staged registry."""
        orch, _, game_state, _, _ = self._make_viable_orchestrator(
            tmp_path, _make_simple_npc_template()
        )
        transition = _make_transition(actor_id="npc:elara", display_name="Elara")
        orch.prepare(
            module=_make_module(
                planned_encounters=(_make_simple_npc_template(),),
                next_encounter_index=0,
            ),
            campaign=_make_campaign(),
            player=_make_player(),
            transition=transition,
        )
        updated_state = game_state.persist.call_args[0][0]
        assert "npc:elara" in updated_state.actor_registry.actors

    def test_instantiate_staged_state_includes_encounter(self, tmp_path: Path) -> None:
        """Staged game state must include the new encounter so run_encounter() doesn't see None."""
        orch, _, game_state, _, module = self._make_viable_orchestrator(tmp_path)
        result = orch.prepare(
            module=module, campaign=_make_campaign(), player=_make_player()
        )
        assert isinstance(result, EncounterReady)
        updated_state = game_state.persist.call_args[0][0]
        assert updated_state.encounter is not None
        assert (
            updated_state.encounter.encounter_id == result.encounter_state.encounter_id
        )
        assert "npc:module-001-enc-001:goblin-a" in updated_state.actor_registry.actors


# ─── Retry logic ─────────────────────────────────────────────────────────────


class TestTransitionThreading:
    """Tests that verify transition is threaded from prepare() all the way to the encounter."""

    def test_prepare_threads_transition_to_instantiate(self, tmp_path: Path) -> None:
        """prepare() with transition= passes it through to the resulting encounter."""
        orch, narrative, game_state, planner = _make_orchestrator(tmp_path)
        narrative.retrieve_relevant.return_value = []
        game_state.load.return_value = GameState()

        planner.assess_divergence.return_value = DivergenceAssessment(
            status="viable", reason="ok", milestone_achieved=False
        )

        template = _make_simple_npc_template()
        module = _make_module(planned_encounters=(template,), next_encounter_index=0)
        transition = _make_transition(actor_id="npc:elara", display_name="Elara")

        result = orch.prepare(
            module=module,
            campaign=_make_campaign(),
            player=_make_player(),
            transition=transition,
        )

        assert isinstance(result, EncounterReady)
        assert "npc:elara" in result.encounter_state.actor_ids


class TestRetryLogic:
    def test_prepare_retries_on_exception(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """prepare() retries up to 3 times on LLM failure before raising."""
        monkeypatch.setattr(
            "campaignnarrator.orchestrators.encounter_planner_orchestrator.time.sleep",
            lambda _: None,
        )
        orch, narrative, _, planner = _make_orchestrator(tmp_path)
        narrative.retrieve_relevant.return_value = []

        planner.assess_divergence.side_effect = RuntimeError("LLM timeout")

        module = _make_module(
            planned_encounters=(_make_template(),), next_encounter_index=0
        )

        with pytest.raises(RuntimeError, match="LLM timeout"):
            orch.prepare(
                module=module, campaign=_make_campaign(), player=_make_player()
            )

        expected_call_count = 3
        assert planner.assess_divergence.call_count == expected_call_count

    def test_prepare_succeeds_on_second_attempt(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """prepare() succeeds if a later attempt succeeds within 3 tries."""
        monkeypatch.setattr(
            "campaignnarrator.orchestrators.encounter_planner_orchestrator.time.sleep",
            lambda _: None,
        )
        orch, narrative, game_state, planner = _make_orchestrator(tmp_path)
        narrative.retrieve_relevant.return_value = []
        game_state.load.return_value = GameState()

        planner.assess_divergence.side_effect = [
            RuntimeError("transient failure"),
            DivergenceAssessment(
                status="viable", reason="ok", milestone_achieved=False
            ),
        ]

        module = _make_module(
            planned_encounters=(_make_template(),), next_encounter_index=0
        )

        result = orch.prepare(
            module=module, campaign=_make_campaign(), player=_make_player()
        )
        assert isinstance(result, EncounterReady)
        expected_call_count = 2
        assert planner.assess_divergence.call_count == expected_call_count


# ---------------------------------------------------------------------------
# GameStateRepository path in _instantiate
# ---------------------------------------------------------------------------


def _make_gs_repo(initial: GameState | None = None) -> MagicMock:
    if initial is None:
        initial = GameState()
    repo = MagicMock(spec=GameStateRepository)
    cache: list[GameState] = [initial]
    repo.load.side_effect = lambda: cache[-1]
    repo.persist.side_effect = cache.append
    return repo


def _make_viable_planner(templates: tuple) -> MagicMock:
    planner = MagicMock(spec=EncounterPlannerAgent)
    planner.assess_divergence.return_value = DivergenceAssessment(
        status="viable", reason="ok", milestone_achieved=False
    )
    planner.plan_encounters.return_value = templates
    return planner


def test_instantiate_stages_to_game_state_repo_when_set(tmp_path: Path) -> None:
    """_instantiate() must call stage() on the game_state_repo."""
    gs_repo = _make_gs_repo()
    planner = _make_viable_planner((_make_simple_npc_template(),))
    orch, narrative, _, _ = _make_orchestrator(
        tmp_path, game_state=gs_repo, planner=planner
    )
    template = _make_simple_npc_template()
    narrative.retrieve_relevant.return_value = []

    result = orch.prepare(
        module=_make_module(planned_encounters=(template,), next_encounter_index=0),
        campaign=_make_campaign(),
        player=_make_player(),
    )

    assert isinstance(result, EncounterReady)
    gs_repo.persist.assert_called_once()


def test_instantiate_staged_state_contains_encounter_and_actors(
    tmp_path: Path,
) -> None:
    """Staged GameState must include the new encounter and all NPC actors."""
    initial_gs = GameState()
    gs_repo = _make_gs_repo(initial_gs)
    template = _make_simple_npc_template("goblin-scout")
    planner = _make_viable_planner((template,))
    orch, narrative, _, _ = _make_orchestrator(
        tmp_path, game_state=gs_repo, planner=planner
    )
    narrative.retrieve_relevant.return_value = []

    orch.prepare(
        module=_make_module(planned_encounters=(template,), next_encounter_index=0),
        campaign=_make_campaign(),
        player=_make_player(),
    )

    (staged_gs,) = gs_repo.persist.call_args_list[0].args
    assert staged_gs.encounter is not None
    assert any("goblin-scout" in aid for aid in staged_gs.actor_registry.actors)
