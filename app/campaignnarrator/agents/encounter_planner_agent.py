"""Agent that plans, assesses, and recovers encounter sequences for a module."""

from __future__ import annotations

import json
import logging
from typing import Literal

from pydantic_ai import Agent

from campaignnarrator.adapters.pydantic_ai_adapter import PydanticAIAdapter
from campaignnarrator.domain.models import (
    ActorState,
    CampaignState,
    DivergenceAssessment,
    EncounterPlanList,
    EncounterRecoveryResult,
    EncounterTemplate,
    Milestone,
    ModuleState,
)

_log = logging.getLogger(__name__)

_PLAN_INSTRUCTIONS = (
    "You are a dungeon master designing encounters for a D&D 5e campaign module. "
    "Given the module summary, campaign context, and player information, generate "
    "a list of 3 to 5 encounter templates that move the story toward the guiding "
    "milestone. "
    "Each encounter must have: a unique template_id ('enc-001', 'enc-002', ...), "
    "order (0-based integer), setting description, one-sentence narrative purpose, "
    "NPC roster, prerequisites (natural language), expected outcomes, and downstream "
    "dependencies. "
    "Assign unique template_npc_id values across the ENTIRE module (not just per "
    "encounter). "
    "template_npc_id must be a lowercase-hyphenated slug ('grizznak', "
    "'innkeeper-mira', 'goblin-scout-a'). "
    "display_name must be a properly capitalised, human-readable name suitable for "
    "prose narration ('Grizznak', 'Innkeeper Mira', 'Goblin Scout A'). "
    "Use positional suffixes for anonymous enemies in both fields "
    "(template_npc_id: 'goblin-scout-a', display_name: 'Goblin Scout A'). "
    "Do NOT include player HP, AC, or other mechanical stats — narrative context "
    "only. "
    "CR must be a float (0.25, 0.5, 1.0, etc.)."
)

_ASSESS_INSTRUCTIONS = (
    "You are evaluating whether a planned D&D 5e encounter is still viable. "
    "Given the encounter template (or null for milestone-only check), "
    "narrative memory, guiding milestone, and current player state, return a "
    "DivergenceAssessment. "
    "Use player_state (hp, conditions) to judge viability — a player at low HP or "
    "under severe conditions may need a recovery encounter before a hard fight. "
    "status must be one of: viable, needs_bridge, needs_rebuild, "
    "needs_full_replan, milestone_achieved. "
    "milestone_achieved: set to true whenever the module milestone goal is "
    "narratively complete, even mid-module — do not wait for all encounters to run. "
    "viable: prerequisites met, proceed as planned. "
    "needs_bridge: a key prerequisite NPC is dead or missing — insert 1-2 bridge "
    "encounters. "
    "needs_rebuild: encounter premise is broken by narrative events — replace this "
    "encounter. "
    "needs_full_replan: narrative has diverged too far — regenerate all remaining "
    "encounters. "
    "Always populate reason with a one-sentence explanation."
)

_RECOVERY_INSTRUCTIONS = (
    "You are a dungeon master recovering a diverged D&D 5e encounter plan. "
    "Given the recovery type, current narrative state, and player state, return "
    "updated encounter templates. "
    "Use player_state (hp, conditions) to calibrate recovery encounters — do not "
    "send a depleted player into a hard fight without a rest or lighter bridge first. "
    "bridge_inserted: insert 1-2 new encounters at the front of the remaining list. "
    "template_replaced: return a single replacement for the broken encounter. "
    "full_replan: return 3-5 new encounters that complete the module from this point. "
    "Reuse template_npc_id values for NPCs that still exist in the narrative. "
    "Assign new unique template_npc_id values for any new NPCs. "
    "Set template_id as 'enc-bridge-001', 'enc-bridge-002' for bridges; "
    "preserve existing IDs for unchanged templates."
)


class EncounterPlannerAgent:
    """Plan, assess divergence, and recover encounter sequences for a module.

    _plan_agent: generates the initial 3-5 encounter list for a module.
    _assess_agent: checks divergence and milestone status before each encounter.
    _recovery_agent: generates bridge/rebuild/replan templates when needed.

    All three agents take JSON input and return structured Pydantic model output.
    """

    def __init__(
        self,
        *,
        adapter: PydanticAIAdapter,
        _plan_agent: object | None = None,
        _assess_agent: object | None = None,
        _recovery_agent: object | None = None,
    ) -> None:
        self._adapter = adapter
        self._plan_agent: object = (
            _plan_agent
            if _plan_agent is not None
            else Agent(
                adapter.model,
                output_type=EncounterPlanList,
                instructions=_PLAN_INSTRUCTIONS,
            )
        )
        self._assess_agent: object = (
            _assess_agent
            if _assess_agent is not None
            else Agent(
                adapter.model,
                output_type=DivergenceAssessment,
                instructions=_ASSESS_INSTRUCTIONS,
            )
        )
        self._recovery_agent: object = (
            _recovery_agent
            if _recovery_agent is not None
            else Agent(
                adapter.model,
                output_type=EncounterRecoveryResult,
                instructions=_RECOVERY_INSTRUCTIONS,
            )
        )

    def plan_encounters(
        self,
        *,
        module: ModuleState,
        campaign: CampaignState,
        player: ActorState,
        narrative_context: str,
    ) -> tuple[EncounterTemplate, ...]:
        """Generate the initial encounter list for a module.

        Narrative context only — no mechanical player stats (HP, AC, etc.).
        Returns tuple[EncounterTemplate, ...] from EncounterPlanList.encounters.
        """
        context = json.dumps(
            {
                "campaign_name": campaign.name,
                "campaign_setting": campaign.setting,
                "module_title": module.title,
                "module_summary": module.summary,
                "guiding_milestone_id": module.guiding_milestone_id,
                "player_name": player.name,
                "player_race": player.race,
                "player_level": player.level,
                "completed_encounter_summaries": list(
                    module.completed_encounter_summaries
                ),
                "narrative_context": narrative_context,
            },
            indent=2,
            sort_keys=True,
        )
        _log.info("Planning encounters for module %s", module.module_id)
        result: EncounterPlanList = self._plan_agent.run_sync(context).output  # type: ignore[union-attr]
        return result.encounters

    def assess_divergence(
        self,
        *,
        template: EncounterTemplate | None,
        module: ModuleState,
        milestone: Milestone,
        narrative_context: str,
        player: ActorState,
    ) -> DivergenceAssessment:
        """Check whether the next planned encounter is still viable.

        template=None signals a milestone-only check (used when planned_encounters
        is empty).
        """
        context = json.dumps(
            {
                "next_template": (
                    template.model_dump() if template is not None else None
                ),
                "module_title": module.title,
                "guiding_milestone": {
                    "milestone_id": milestone.milestone_id,
                    "title": milestone.title,
                    "description": milestone.description,
                },
                "completed_encounter_summaries": list(
                    module.completed_encounter_summaries
                ),
                "narrative_context": narrative_context,
                "player_state": {
                    "name": player.name,
                    "hp_current": player.hp_current,
                    "hp_max": player.hp_max,
                    "conditions": list(player.conditions),
                    "proficiency_bonus": player.proficiency_bonus,
                },
            },
            indent=2,
            sort_keys=True,
        )
        _log.info(
            "Assessing divergence for module %s, encounter index %d",
            module.module_id,
            module.next_encounter_index,
        )
        return self._assess_agent.run_sync(context).output  # type: ignore[union-attr]

    def recover_encounters(
        self,
        *,
        divergence_reason: str,
        recovery_type: Literal["bridge_inserted", "template_replaced", "full_replan"],
        current_index: int,
        remaining_templates: tuple[EncounterTemplate, ...],
        module: ModuleState,
        campaign: CampaignState,
        narrative_context: str,
        player: ActorState,
    ) -> EncounterRecoveryResult:
        """Generate recovery templates for a diverged encounter plan."""
        context = json.dumps(
            {
                "recovery_type": recovery_type,
                "divergence_reason": divergence_reason,
                "current_index": current_index,
                "remaining_templates": [t.model_dump() for t in remaining_templates],
                "module_title": module.title,
                "module_summary": module.summary,
                "guiding_milestone_id": module.guiding_milestone_id,
                "campaign_name": campaign.name,
                "campaign_setting": campaign.setting,
                "completed_encounter_summaries": list(
                    module.completed_encounter_summaries
                ),
                "narrative_context": narrative_context,
                "player_state": {
                    "name": player.name,
                    "hp_current": player.hp_current,
                    "hp_max": player.hp_max,
                    "conditions": list(player.conditions),
                    "proficiency_bonus": player.proficiency_bonus,
                },
            },
            indent=2,
            sort_keys=True,
        )
        _log.info(
            "Recovering %s for module %s at index %d",
            recovery_type,
            module.module_id,
            current_index,
        )
        return self._recovery_agent.run_sync(context).output  # type: ignore[union-attr]
