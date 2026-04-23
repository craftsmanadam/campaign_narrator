"""Unit tests for EncounterPlannerOrchestrator."""

from __future__ import annotations

import dataclasses
from unittest.mock import MagicMock

import pytest
from campaignnarrator.agents.encounter_planner_agent import EncounterPlannerAgent
from campaignnarrator.domain.models import (
    ActorState,
    ActorType,
    CampaignState,
    DivergenceAssessment,
    EncounterNpc,
    EncounterRecoveryResult,
    EncounterTemplate,
    Milestone,
    MilestoneAchieved,
    ModuleState,
)
from campaignnarrator.orchestrators.encounter_planner_orchestrator import (
    EncounterPlannerOrchestrator,
    EncounterPlannerOrchestratorAgents,
    EncounterPlannerOrchestratorRepositories,
)
from campaignnarrator.repositories.compendium_repository import CompendiumRepository
from campaignnarrator.repositories.encounter_repository import EncounterRepository
from campaignnarrator.repositories.memory_repository import MemoryRepository
from campaignnarrator.repositories.module_repository import ModuleRepository

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


def _make_repos() -> EncounterPlannerOrchestratorRepositories:
    return EncounterPlannerOrchestratorRepositories(
        module=MagicMock(spec=ModuleRepository),
        encounter=MagicMock(spec=EncounterRepository),
        memory=MagicMock(spec=MemoryRepository),
        compendium=MagicMock(spec=CompendiumRepository),
    )


def _make_agents() -> EncounterPlannerOrchestratorAgents:
    return EncounterPlannerOrchestratorAgents(
        planner=MagicMock(spec=EncounterPlannerAgent),
    )


# ─── Constructor / data classes ──────────────────────────────────────────────


class TestDataClasses:
    def test_repositories_is_frozen_dataclass(self) -> None:
        repos = _make_repos()
        assert dataclasses.is_dataclass(repos)

    def test_agents_is_frozen_dataclass(self) -> None:
        agents = _make_agents()
        assert dataclasses.is_dataclass(agents)

    def test_orchestrator_constructs_without_error(self) -> None:
        EncounterPlannerOrchestrator(
            repositories=_make_repos(),
            agents=_make_agents(),
        )


# ─── Empty plan detection ─────────────────────────────────────────────────────


class TestEmptyPlanDetection:
    def test_empty_planned_encounters_triggers_plan_call(self) -> None:
        """When planned_encounters is empty, prepare() calls plan_encounters()."""
        templates = (_make_template("enc-001"), _make_template("enc-002", order=1))
        repos = _make_repos()
        agents = _make_agents()
        agents.planner.plan_encounters.return_value = templates
        agents.planner.assess_divergence.return_value = MagicMock(
            status="viable",
            milestone_achieved=False,
        )
        repos.memory.retrieve_relevant.return_value = []
        repos.compendium.monster_index_path.return_value = None

        orchestrator = EncounterPlannerOrchestrator(repositories=repos, agents=agents)

        module = _make_module()
        assert module.planned_encounters == ()

        with pytest.raises(NotImplementedError):
            orchestrator.prepare(
                module=module,
                campaign=_make_campaign(),
                player=_make_player(),
            )

        agents.planner.plan_encounters.assert_called_once()

    def test_empty_plan_saves_module_before_divergence_check(self) -> None:
        """After planning, the updated module is saved before proceeding."""
        templates = (_make_template(),)
        repos = _make_repos()
        agents = _make_agents()
        agents.planner.plan_encounters.return_value = templates
        agents.planner.assess_divergence.return_value = DivergenceAssessment(
            status="viable", reason="ok", milestone_achieved=False
        )
        repos.memory.retrieve_relevant.return_value = []
        repos.compendium.monster_index_path.return_value = None

        orchestrator = EncounterPlannerOrchestrator(repositories=repos, agents=agents)

        with pytest.raises(NotImplementedError):
            orchestrator.prepare(
                module=_make_module(),
                campaign=_make_campaign(),
                player=_make_player(),
            )

        repos.module.save.assert_called_once()
        saved_module = repos.module.save.call_args[0][0]
        assert len(saved_module.planned_encounters) == 1
        assert saved_module.next_encounter_index == 0

    def test_plan_encounters_receives_narrative_context_from_memory(self) -> None:
        """plan_encounters() receives narrative context from MemoryRepository."""
        templates = (_make_template(),)
        repos = _make_repos()
        agents = _make_agents()
        agents.planner.plan_encounters.return_value = templates
        agents.planner.assess_divergence.return_value = DivergenceAssessment(
            status="viable", reason="ok", milestone_achieved=False
        )
        repos.memory.retrieve_relevant.return_value = ["A prior narrative entry."]
        repos.compendium.monster_index_path.return_value = None

        orchestrator = EncounterPlannerOrchestrator(repositories=repos, agents=agents)

        with pytest.raises(NotImplementedError):
            orchestrator.prepare(
                module=_make_module(),
                campaign=_make_campaign(),
                player=_make_player(),
            )

        call_kwargs = agents.planner.plan_encounters.call_args[1]
        assert "A prior narrative entry." in call_kwargs["narrative_context"]

    def test_non_empty_plan_does_not_call_plan_encounters(self) -> None:
        """When planned_encounters is populated, plan_encounters() is NOT called."""
        repos = _make_repos()
        agents = _make_agents()
        agents.planner.assess_divergence.return_value = DivergenceAssessment(
            status="viable", reason="ok", milestone_achieved=False
        )
        repos.memory.retrieve_relevant.return_value = []
        repos.compendium.monster_index_path.return_value = None

        orchestrator = EncounterPlannerOrchestrator(repositories=repos, agents=agents)

        module = _make_module(
            planned_encounters=(_make_template(),),
            next_encounter_index=0,
        )

        with pytest.raises(NotImplementedError):
            orchestrator.prepare(
                module=module,
                campaign=_make_campaign(),
                player=_make_player(),
            )

        agents.planner.plan_encounters.assert_not_called()


# ─── Out-of-bounds index ──────────────────────────────────────────────────────


class TestOutOfBoundsIndex:
    def test_index_at_end_of_list_triggers_milestone_only_check(self) -> None:
        """When next_encounter_index >= len(planned_encounters), run milestone check."""
        repos = _make_repos()
        agents = _make_agents()
        repos.memory.retrieve_relevant.return_value = []
        repos.compendium.monster_index_path.return_value = None

        milestone_assessment = DivergenceAssessment(
            status="milestone_achieved",
            reason="Module complete.",
            milestone_achieved=True,
        )
        agents.planner.assess_divergence.return_value = milestone_assessment

        orchestrator = EncounterPlannerOrchestrator(repositories=repos, agents=agents)
        module = _make_module(
            planned_encounters=(_make_template(),),
            next_encounter_index=1,  # out of bounds (only 1 template at index 0)
        )

        result = orchestrator.prepare(
            module=module,
            campaign=_make_campaign(),
            player=_make_player(),
        )

        assert isinstance(result, MilestoneAchieved)
        # assess_divergence must be called with template=None (milestone-only check)
        call_kwargs = agents.planner.assess_divergence.call_args[1]
        assert call_kwargs["template"] is None

    def test_index_at_end_viable_status_falls_through_to_instantiation(
        self,
    ) -> None:
        """Out-of-bounds index + viable status → instantiation (NotImplementedError in 3c)."""
        repos = _make_repos()
        agents = _make_agents()
        repos.memory.retrieve_relevant.return_value = []
        repos.compendium.monster_index_path.return_value = None

        agents.planner.assess_divergence.return_value = DivergenceAssessment(
            status="viable",
            reason="ok",
            milestone_achieved=False,
        )

        orchestrator = EncounterPlannerOrchestrator(repositories=repos, agents=agents)
        module = _make_module(
            planned_encounters=(_make_template(),),
            next_encounter_index=1,
        )

        with pytest.raises(NotImplementedError):
            orchestrator.prepare(
                module=module,
                campaign=_make_campaign(),
                player=_make_player(),
            )


# ─── Viable path ─────────────────────────────────────────────────────────────


class TestViablePath:
    def test_viable_path_calls_instantiate(self) -> None:
        """Viable assessment → proceed directly to instantiation (NotImplementedError 3c)."""
        repos = _make_repos()
        agents = _make_agents()
        repos.memory.retrieve_relevant.return_value = []
        repos.compendium.monster_index_path.return_value = None

        agents.planner.assess_divergence.return_value = DivergenceAssessment(
            status="viable",
            reason="ok",
            milestone_achieved=False,
        )

        orchestrator = EncounterPlannerOrchestrator(repositories=repos, agents=agents)
        module = _make_module(
            planned_encounters=(_make_template(),),
            next_encounter_index=0,
        )

        with pytest.raises(NotImplementedError):
            orchestrator.prepare(
                module=module,
                campaign=_make_campaign(),
                player=_make_player(),
            )

        agents.planner.recover_encounters.assert_not_called()

    def test_milestone_achieved_returns_milestone_achieved_object(self) -> None:
        repos = _make_repos()
        agents = _make_agents()
        repos.memory.retrieve_relevant.return_value = []

        agents.planner.assess_divergence.return_value = DivergenceAssessment(
            status="milestone_achieved",
            reason="Cult leader defeated.",
            milestone_achieved=True,
        )

        orchestrator = EncounterPlannerOrchestrator(repositories=repos, agents=agents)
        module = _make_module(
            planned_encounters=(_make_template(),),
            next_encounter_index=0,
        )

        result = orchestrator.prepare(
            module=module,
            campaign=_make_campaign(),
            player=_make_player(),
        )
        assert isinstance(result, MilestoneAchieved)


# ─── Recovery branches ────────────────────────────────────────────────────────


class TestRecovery:
    def _setup_recovery(
        self,
        status: str,
        recovery_type: str,
        updated_templates: tuple[EncounterTemplate, ...],
    ) -> tuple[
        EncounterPlannerOrchestratorRepositories, EncounterPlannerOrchestratorAgents
    ]:
        repos = _make_repos()
        agents = _make_agents()
        repos.memory.retrieve_relevant.return_value = []
        repos.compendium.monster_index_path.return_value = None

        agents.planner.assess_divergence.return_value = DivergenceAssessment(
            status=status,
            reason="NPC is dead.",
            milestone_achieved=False,
        )
        agents.planner.recover_encounters.return_value = EncounterRecoveryResult(
            updated_templates=updated_templates,
            recovery_type=recovery_type,
        )
        return repos, agents

    def test_needs_bridge_calls_recover_and_saves_updated_module(self) -> None:
        bridge = _make_template("enc-bridge")
        original = _make_template("enc-001")
        repos, agents = self._setup_recovery(
            "needs_bridge",
            "bridge_inserted",
            (bridge, original),
        )
        orchestrator = EncounterPlannerOrchestrator(repositories=repos, agents=agents)
        module = _make_module(
            planned_encounters=(original,),
            next_encounter_index=0,
        )

        with pytest.raises(NotImplementedError):
            orchestrator.prepare(
                module=module,
                campaign=_make_campaign(),
                player=_make_player(),
            )

        agents.planner.recover_encounters.assert_called_once()
        call_kwargs = agents.planner.recover_encounters.call_args[1]
        assert call_kwargs["recovery_type"] == "bridge_inserted"
        repos.module.save.assert_called()

    def test_needs_bridge_updated_module_has_new_templates(self) -> None:
        bridge = _make_template("enc-bridge")
        original = _make_template("enc-001")
        repos, agents = self._setup_recovery(
            "needs_bridge",
            "bridge_inserted",
            (bridge, original),
        )
        orchestrator = EncounterPlannerOrchestrator(repositories=repos, agents=agents)
        module = _make_module(
            planned_encounters=(original,),
            next_encounter_index=0,
        )

        with pytest.raises(NotImplementedError):
            orchestrator.prepare(
                module=module,
                campaign=_make_campaign(),
                player=_make_player(),
            )

        last_save = repos.module.save.call_args[0][0]
        expected_count = 2
        assert len(last_save.planned_encounters) == expected_count
        assert last_save.planned_encounters[0].template_id == "enc-bridge"

    def test_needs_rebuild_replaces_current_template(self) -> None:
        replacement = _make_template("enc-001-rebuilt")
        original = _make_template("enc-001")
        repos, agents = self._setup_recovery(
            "needs_rebuild",
            "template_replaced",
            (replacement,),
        )
        orchestrator = EncounterPlannerOrchestrator(repositories=repos, agents=agents)
        module = _make_module(
            planned_encounters=(original,),
            next_encounter_index=0,
        )

        with pytest.raises(NotImplementedError):
            orchestrator.prepare(
                module=module,
                campaign=_make_campaign(),
                player=_make_player(),
            )

        last_save = repos.module.save.call_args[0][0]
        assert last_save.planned_encounters[0].template_id == "enc-001-rebuilt"

    def test_needs_full_replan_replaces_all_remaining_templates(self) -> None:
        new1 = _make_template("enc-new-001")
        new2 = _make_template("enc-new-002", order=1)
        existing_done = _make_template("enc-done")
        repos, agents = self._setup_recovery(
            "needs_full_replan",
            "full_replan",
            (new1, new2),
        )
        orchestrator = EncounterPlannerOrchestrator(repositories=repos, agents=agents)
        # Two templates; first is done (index=1), second needs replan
        module = _make_module(
            planned_encounters=(existing_done, _make_template("enc-002", order=1)),
            next_encounter_index=1,
        )

        with pytest.raises(NotImplementedError):
            orchestrator.prepare(
                module=module,
                campaign=_make_campaign(),
                player=_make_player(),
            )

        last_save = repos.module.save.call_args[0][0]
        assert existing_done in last_save.planned_encounters
        assert new1 in last_save.planned_encounters
        assert new2 in last_save.planned_encounters

    def test_recovery_empty_result_escalates_to_full_replan(self) -> None:
        """Empty updated_templates triggers fallback to full module replan."""
        repos = _make_repos()
        agents = _make_agents()
        repos.memory.retrieve_relevant.return_value = []
        repos.compendium.monster_index_path.return_value = None

        agents.planner.assess_divergence.return_value = DivergenceAssessment(
            status="needs_rebuild",
            reason="Broken.",
            milestone_achieved=False,
        )
        # First recovery returns empty; second returns valid template
        fallback_template = _make_template("enc-fallback")
        agents.planner.recover_encounters.side_effect = [
            EncounterRecoveryResult(
                updated_templates=(),
                recovery_type="template_replaced",
            ),
            EncounterRecoveryResult(
                updated_templates=(fallback_template,),
                recovery_type="full_replan",
            ),
        ]

        orchestrator = EncounterPlannerOrchestrator(repositories=repos, agents=agents)
        module = _make_module(
            planned_encounters=(_make_template(),),
            next_encounter_index=0,
        )

        with pytest.raises(NotImplementedError):
            orchestrator.prepare(
                module=module,
                campaign=_make_campaign(),
                player=_make_player(),
            )

        # recover_encounters called twice (first empty, then fallback)
        expected_call_count = 2
        assert agents.planner.recover_encounters.call_count == expected_call_count
        second_call_kwargs = agents.planner.recover_encounters.call_args_list[1][1]
        assert second_call_kwargs["recovery_type"] == "full_replan"
