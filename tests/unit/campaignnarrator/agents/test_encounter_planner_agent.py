"""Unit tests for EncounterPlannerAgent."""

from __future__ import annotations

from unittest.mock import MagicMock

from campaignnarrator.agents.encounter_planner_agent import EncounterPlannerAgent
from campaignnarrator.domain.models import (
    ActorState,
    ActorType,
    CampaignState,
    DivergenceAssessment,
    EncounterNpc,
    EncounterPlanList,
    EncounterRecoveryResult,
    EncounterTemplate,
    Milestone,
    ModuleState,
)


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


def _make_module() -> ModuleState:
    return ModuleState(
        module_id="module-001",
        campaign_id="c1",
        title="The Dockside Murders",
        summary="Bodies wash ashore nightly.",
        guiding_milestone_id="m1",
    )


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


def _make_template(template_id: str = "enc-001") -> EncounterTemplate:
    return EncounterTemplate(
        template_id=template_id,
        order=0,
        setting="The docks.",
        purpose="Intro.",
        npcs=(_make_npc(),),
        prerequisites=(),
        expected_outcomes=(),
        downstream_dependencies=(),
    )


class TestPlanEncounters:
    def test_plan_encounters_calls_plan_agent_and_returns_tuple(self) -> None:
        """plan_encounters() calls _plan_agent and returns tuple[EncounterTemplate, ...]."""
        plan_output = EncounterPlanList(encounters=(_make_template(),))
        mock_plan_agent = MagicMock()
        mock_plan_agent.run_sync.return_value.output = plan_output

        agent = EncounterPlannerAgent(
            adapter=MagicMock(),
            _plan_agent=mock_plan_agent,
            _assess_agent=MagicMock(),
            _recovery_agent=MagicMock(),
        )

        result = agent.plan_encounters(
            module=_make_module(),
            campaign=_make_campaign(),
            player=_make_player(),
            narrative_context="No prior context.",
        )

        assert mock_plan_agent.run_sync.called
        assert isinstance(result, tuple)
        assert len(result) == 1
        assert result[0].template_id == "enc-001"

    def test_plan_encounters_passes_narrative_only_context(self) -> None:
        """plan_encounters() does NOT include HP, AC, or mechanical player stats."""
        plan_output = EncounterPlanList(encounters=(_make_template(),))
        mock_plan_agent = MagicMock()
        mock_plan_agent.run_sync.return_value.output = plan_output

        agent = EncounterPlannerAgent(
            adapter=MagicMock(),
            _plan_agent=mock_plan_agent,
            _assess_agent=MagicMock(),
            _recovery_agent=MagicMock(),
        )
        agent.plan_encounters(
            module=_make_module(),
            campaign=_make_campaign(),
            player=_make_player(level=3),
            narrative_context="Prior context.",
        )

        call_json = mock_plan_agent.run_sync.call_args[0][0]
        assert "hp_current" not in call_json
        assert "armor_class" not in call_json
        assert "player_level" in call_json or "level" in call_json


class TestAssessDivergence:
    def test_assess_divergence_returns_viable(self) -> None:
        """assess_divergence() calls _assess_agent and returns DivergenceAssessment."""
        assessment = DivergenceAssessment(
            status="viable",
            reason="prerequisites met",
            milestone_achieved=False,
        )
        mock_assess_agent = MagicMock()
        mock_assess_agent.run_sync.return_value.output = assessment

        agent = EncounterPlannerAgent(
            adapter=MagicMock(),
            _plan_agent=MagicMock(),
            _assess_agent=mock_assess_agent,
            _recovery_agent=MagicMock(),
        )
        milestone = Milestone(
            milestone_id="m1",
            title="First Blood",
            description="Enter city.",
        )

        result = agent.assess_divergence(
            template=_make_template(),
            module=_make_module(),
            milestone=milestone,
            narrative_context="No prior events.",
            player=_make_player(),
        )

        assert mock_assess_agent.run_sync.called
        assert result.status == "viable"
        assert result.milestone_achieved is False

    def test_assess_divergence_none_template_for_milestone_only_check(
        self,
    ) -> None:
        """None template signals milestone-only check (no encounter prerequisites)."""
        assessment = DivergenceAssessment(
            status="milestone_achieved",
            reason="Milestone complete.",
            milestone_achieved=True,
        )
        mock_assess_agent = MagicMock()
        mock_assess_agent.run_sync.return_value.output = assessment

        agent = EncounterPlannerAgent(
            adapter=MagicMock(),
            _plan_agent=MagicMock(),
            _assess_agent=mock_assess_agent,
            _recovery_agent=MagicMock(),
        )
        milestone = Milestone(
            milestone_id="m1",
            title="First Blood",
            description="Enter city.",
        )

        result = agent.assess_divergence(
            template=None,
            module=_make_module(),
            milestone=milestone,
            narrative_context="Milestone narrative complete.",
            player=_make_player(),
        )

        assert result.milestone_achieved is True
        call_json = mock_assess_agent.run_sync.call_args[0][0]
        assert "next_template" in call_json or "null" in call_json

    def test_assess_divergence_includes_player_state_in_context(self) -> None:
        """assess_divergence() must include hp and conditions so the LLM can judge viability."""
        mock_assess_agent = MagicMock()
        mock_assess_agent.run_sync.return_value.output = DivergenceAssessment(
            status="viable", reason="ok", milestone_achieved=False
        )
        agent = EncounterPlannerAgent(
            adapter=MagicMock(),
            _plan_agent=MagicMock(),
            _assess_agent=mock_assess_agent,
            _recovery_agent=MagicMock(),
        )
        milestone = Milestone(milestone_id="m1", title="T", description="D")

        agent.assess_divergence(
            template=_make_template(),
            module=_make_module(),
            milestone=milestone,
            narrative_context="ctx",
            player=_make_player(),
        )

        call_json = mock_assess_agent.run_sync.call_args[0][0]
        assert "hp_current" in call_json
        assert "conditions" in call_json
        assert "proficiency_bonus" in call_json


class TestRecoverEncounters:
    def test_recover_returns_updated_templates(self) -> None:
        """recover_encounters() calls _recovery_agent and returns updated templates."""
        new_template = _make_template("enc-bridge")
        recovery = EncounterRecoveryResult(
            updated_templates=(new_template,),
            recovery_type="bridge_inserted",
        )
        mock_recovery_agent = MagicMock()
        mock_recovery_agent.run_sync.return_value.output = recovery

        agent = EncounterPlannerAgent(
            adapter=MagicMock(),
            _plan_agent=MagicMock(),
            _assess_agent=MagicMock(),
            _recovery_agent=mock_recovery_agent,
        )

        result = agent.recover_encounters(
            divergence_reason="Key NPC died early.",
            recovery_type="bridge_inserted",
            current_index=1,
            remaining_templates=(_make_template("enc-002"),),
            module=_make_module(),
            campaign=_make_campaign(),
            narrative_context="Grizznak is dead.",
            player=_make_player(),
        )

        assert mock_recovery_agent.run_sync.called
        assert result.recovery_type == "bridge_inserted"
        assert result.updated_templates[0].template_id == "enc-bridge"

    def test_recover_encounters_includes_player_state_in_context(self) -> None:
        """recover_encounters() must include player hp so the LLM can calibrate recovery difficulty."""
        new_template = _make_template("enc-bridge")
        mock_recovery_agent = MagicMock()
        mock_recovery_agent.run_sync.return_value.output = EncounterRecoveryResult(
            updated_templates=(new_template,),
            recovery_type="bridge_inserted",
        )
        agent = EncounterPlannerAgent(
            adapter=MagicMock(),
            _plan_agent=MagicMock(),
            _assess_agent=MagicMock(),
            _recovery_agent=mock_recovery_agent,
        )

        agent.recover_encounters(
            divergence_reason="NPC dead.",
            recovery_type="bridge_inserted",
            current_index=0,
            remaining_templates=(_make_template(),),
            module=_make_module(),
            campaign=_make_campaign(),
            narrative_context="ctx",
            player=_make_player(),
        )

        call_json = mock_recovery_agent.run_sync.call_args[0][0]
        assert "hp_current" in call_json
        assert "conditions" in call_json
        assert "proficiency_bonus" in call_json
