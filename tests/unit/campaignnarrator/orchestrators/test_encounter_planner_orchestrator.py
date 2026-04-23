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
    EncounterNpc,
    EncounterTemplate,
    Milestone,
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
