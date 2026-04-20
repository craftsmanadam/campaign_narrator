"""Narrator agent for player-facing output."""

from __future__ import annotations

import json

from pydantic_ai import Agent

from campaignnarrator.adapters.pydantic_ai_adapter import PydanticAIAdapter
from campaignnarrator.domain.models import (
    ActorState,
    CampaignState,
    CombatAssessment,
    CritReview,
    EncounterState,
    Milestone,
    ModuleState,
    Narration,
    NarrationFrame,
    NextEncounterPlan,
    NpcPresence,
    SceneOpeningResponse,
)
from campaignnarrator.repositories.memory_repository import MemoryRepository

_BASE_NARRATE_INSTRUCTIONS = (
    "Write player-facing tabletop RPG narration. "
    "Use only provided public and allowed context. "
    "Do not invent mechanics, rolls, HP changes, inventory changes, "
    "or hidden facts. "
    "For status_response and recap_response, concise status-like output "
    "is allowed.\n\n"
    "HARD RULES — violating any of these is an error:\n"
    "1. Never expose mechanical stats to the player. No HP numbers, no AC, "
    "no modifiers. Use injury states: uninjured, lightly wounded, bloodied, "
    "barely standing, defeated.\n"
    "2. Do not reset or re-describe the opening scene. The scene has already "
    "been established. Advance the story; do not replay the introduction.\n"
    "3. Do not introduce new named characters. Only use names from the "
    "ESTABLISHED NPCs list. Unnamed characters may interact but must not be "
    "given names.\n"
    "4. If name_known is false for an NPC, refer to them only by their "
    "description label. Never use their display_name until the player has "
    "learned it."
)

_SCENE_OPENING_INSTRUCTIONS = (
    "You are opening a new encounter scene. "
    "Write immersive player-facing narration that sets the scene. "
    "Also choose a short scene tone phrase (8 words or fewer) that captures the "
    "emotional register (e.g. 'tense and foreboding', 'warm and welcoming', "
    "'chaotic and urgent'). "
    "Declare all NPCs present in the scene using introduced_npcs. "
    "For each NPC, choose stat_source='monster_compendium' if it is a "
    "recognizable creature (e.g. Goblin, Zombie) and set monster_name to the "
    "SRD creature name. Use stat_source='simple_npc' for human innkeepers, "
    "merchants, quest-givers, and other social characters not expected to fight.\n\n"
    "HARD RULE: The player character appears in public_actor_summaries with a "
    "'(player)' label. Do not assign their name to any NPC or background character."
)

_ASSESS_COMBAT_INSTRUCTIONS = (
    "You are the Narrator for a D&D 5e encounter. "
    "Assess whether combat should continue. "
    "Set combat_active to false only when the encounter is clearly over: "
    "all enemies dead or fled, NPC surrender, or a cinematic story conclusion. "
    "When combat_active is false, populate outcome with a short_description "
    "(compact, for logs) and a full_description (rich prose shown to player)."
)

_CRIT_REVIEW_INSTRUCTIONS = (
    "You are the Narrator for a D&D 5e encounter. "
    "An NPC has rolled a natural 20 against a player. "
    "Decide whether to approve the critical hit or downgrade it to a normal hit. "
    "Approve if the scene calls for dramatic tension. "
    "Downgrade if it would be anti-climactic or unfair. "
    "When downgrading, provide a reason."
)

_SUMMARIZE_INSTRUCTIONS = (
    "You are a dungeon master writing session notes after an encounter. "
    "Write in rich prose, not bullet points. Your notes must include: "
    "physical descriptions of any named NPCs introduced or featured, "
    "sensory and atmospheric details for locations visited, "
    "notable player choices that should create future narrative callbacks, "
    "key dialogue or story beats, "
    "and the encounter outcome in one sentence. "
    "Write as if reminding yourself before the next session — be specific enough "
    "that you could describe the same NPC, location, or event consistently next time."
)

_PLAN_NEXT_INSTRUCTIONS = (
    "You are a dungeon master planning the next encounter for a campaign. "
    "Given the campaign setting, module context, completed encounter summaries, "
    "and current player state, decide: "
    "(1) Has the guiding milestone been narratively achieved? "
    "(2) What is the opening scene description for the next encounter? "
    "Set milestone_achieved=True only when the milestone's narrative goal is clearly "
    "demonstrated by the completed encounters. "
    "The seed is a 2-3 sentence scene description used verbatim as the encounter "
    "opening."
)


def _serialize_npc_presences(presences: tuple[NpcPresence, ...]) -> str:
    """Serialize NPC presences as a structured block for the narrator LLM."""
    if not presences:
        return ""
    lines = ["ESTABLISHED NPCs IN SCENE:"]
    for p in presences:
        name_state = "named" if p.name_known else "unnamed"
        visibility = "visible" if p.visible else "not visible"
        label = p.display_name if p.name_known else p.description
        lines.append(
            f"- {label} [{name_state}] ({visibility}) — actor_id: {p.actor_id}"
        )
    return "\n".join(lines)


class NarratorAgent:
    """Convert public encounter frames into short player-facing narration."""

    def __init__(
        self,
        *,
        adapter: PydanticAIAdapter,
        personality: str = "",
        memory_repository: MemoryRepository | None = None,
        _scene_agent: object | None = None,
        _assess_agent: object | None = None,
        _crit_agent: object | None = None,
        _plan_agent: object | None = None,
    ) -> None:
        self._adapter = adapter
        self._personality = personality
        self._memory_repository = memory_repository
        self._scene_instructions = self._instructions(_SCENE_OPENING_INSTRUCTIONS)

        if _scene_agent is not None:
            self._scene_agent: object = _scene_agent
        else:
            self._scene_agent = Agent(
                adapter.model,
                output_type=SceneOpeningResponse,
                instructions=self._scene_instructions,
            )
        self._assess_agent = (
            _assess_agent
            if _assess_agent is not None
            else Agent(
                adapter.model,
                output_type=CombatAssessment,
                instructions=_ASSESS_COMBAT_INSTRUCTIONS,
            )
        )
        self._crit_agent = (
            _crit_agent
            if _crit_agent is not None
            else Agent(
                adapter.model,
                output_type=CritReview,
                instructions=_CRIT_REVIEW_INSTRUCTIONS,
            )
        )
        self._plan_agent = (
            _plan_agent
            if _plan_agent is not None
            else Agent(
                adapter.model,
                output_type=NextEncounterPlan,
                instructions=_PLAN_NEXT_INSTRUCTIONS,
            )
        )

    @property
    def adapter(self) -> PydanticAIAdapter:
        """Return the underlying adapter."""
        return self._adapter

    def _instructions(self, base: str) -> str:
        return f"{self._personality}\n\n{base}" if self._personality else base

    def narrate(self, frame: NarrationFrame) -> Narration:
        """Render narration for the supplied public frame."""
        npc_block = _serialize_npc_presences(frame.npc_presences)
        frame_dict: dict[str, object] = {
            "purpose": frame.purpose,
            "phase": frame.phase.value,
            "setting": frame.setting,
            "public_actor_summaries": list(frame.public_actor_summaries),
            "recent_public_events": list(frame.recent_public_events),
            "resolved_outcomes": list(frame.resolved_outcomes),
            "allowed_disclosures": list(frame.allowed_disclosures),
            "tone_guidance": frame.tone_guidance,
        }
        if npc_block:
            frame_dict["npc_presences"] = npc_block
        if frame.purpose == "scene_opening":
            frame_dict["prior_narrative_context"] = self.retrieve_memory(
                frame.setting or ""
            )
            frame_json = json.dumps(frame_dict, indent=2, sort_keys=True)
            result = self._scene_agent.run_sync(frame_json).output
            if not result.text.strip():
                raise ValueError("empty narration output")  # noqa: TRY003
            return Narration(
                text=result.text,
                audience="player",
                scene_tone=result.scene_tone,
            )

        frame_json = json.dumps(frame_dict, indent=2, sort_keys=True)
        text = self._adapter.generate_text(
            instructions=self._instructions(_BASE_NARRATE_INSTRUCTIONS),
            input_text=frame_json,
        )
        if not text.strip():
            raise ValueError("empty narration output")  # noqa: TRY003
        return Narration(text=text, audience="player")

    def open_scene(self, frame: NarrationFrame) -> SceneOpeningResponse:
        """Return the raw SceneOpeningResponse for a scene opening frame.

        Unlike narrate(), returns the structured response directly so callers
        can inspect introduced_npcs before the encounter loop begins.
        Raises ValueError if the narration text is blank.
        """
        frame_dict: dict[str, object] = {
            "purpose": frame.purpose,
            "phase": frame.phase.value,
            "setting": frame.setting,
            "public_actor_summaries": list(frame.public_actor_summaries),
            "recent_public_events": list(frame.recent_public_events),
            "resolved_outcomes": list(frame.resolved_outcomes),
            "allowed_disclosures": list(frame.allowed_disclosures),
            "tone_guidance": frame.tone_guidance,
            "prior_narrative_context": self.retrieve_memory(frame.setting or ""),
        }
        frame_json = json.dumps(frame_dict, indent=2, sort_keys=True)
        result: SceneOpeningResponse = self._scene_agent.run_sync(frame_json).output
        if not result.text.strip():
            raise ValueError("empty narration output")  # noqa: TRY003
        return result

    def declare_npc_intent_from_json(self, context_json: str) -> str:
        """Declare this NPC's combat intent in prose for the current turn.

        Uses adapter.generate_text (prose, not structured output).
        Raises ValueError if the result is blank.
        """
        text = self._adapter.generate_text(
            instructions=(
                "You are the Narrator for a D&D 5e encounter. "
                "In one to three sentences, declare this NPC's combat intent "
                "for the current turn. Describe their goal and intended action "
                "in prose only. Be specific: name the target, describe the "
                "action, hint at motivation."
            ),
            input_text=context_json,
        )
        if not text.strip():
            raise ValueError("empty npc intent")  # noqa: TRY003
        return text

    def assess_combat_from_json(self, state_json: str) -> CombatAssessment:
        """Assess whether combat should continue based on the current encounter state.

        Uses self._assess_agent (Agent[CombatAssessment]). Raises ValueError if
        combat_active=False but no outcome is provided (semantic validation).
        """
        assessment = self._assess_agent.run_sync(state_json).output
        if not assessment.combat_active and assessment.outcome is None:
            raise ValueError("combat_active=False but no outcome provided")  # noqa: TRY003
        return assessment

    def review_crit_from_json(self, context_json: str) -> CritReview:
        """Decide whether to approve or downgrade an NPC critical hit against a PC.

        Uses self._crit_agent (Agent[CritReview]). Schema validation is handled
        by pydantic-ai.
        """
        return self._crit_agent.run_sync(context_json).output

    def retrieve_memory(self, query: str) -> str:
        """Return relevant prior narrative entries for the given query.

        Designed for future pydantic-ai tool registration; call signature is stable.
        Returns a sentinel string when no records match so callers never receive None.
        """
        if self._memory_repository is None:
            return "No prior records found."
        results = self._memory_repository.retrieve_relevant(query, limit=5)
        return "\n---\n".join(results) if results else "No prior records found."

    def summarize_encounter(
        self,
        encounter: EncounterState,
        module: ModuleState,
        campaign: CampaignState,
    ) -> str:
        """Write session-notes-style summary of a completed encounter.

        Called by ModuleOrchestrator after natural encounter completion. The summary
        is stored in both ModuleState.completed_encounter_summaries and
        MemoryRepository. Rich summaries are essential for cross-encounter narrative
        consistency.
        """
        context = {
            "encounter_id": encounter.encounter_id,
            "setting": encounter.setting,
            "public_events": list(encounter.public_events),
            "outcome": encounter.outcome,
            "module_title": module.title,
            "campaign_setting": campaign.setting,
        }
        return self._adapter.generate_text(
            instructions=self._instructions(_SUMMARIZE_INSTRUCTIONS),
            input_text=json.dumps(context, indent=2, sort_keys=True),
        )

    def plan_next_encounter(
        self,
        campaign: CampaignState,
        module: ModuleState,
        milestone: Milestone,
        player: ActorState,
        last_outcome: str,
    ) -> NextEncounterPlan:
        """Plan the next encounter after archiving the completed one.

        The guiding Milestone is narrator-internal context for planning judgment.
        It must not be emitted verbatim in player-facing output.
        """
        context = {
            "campaign_setting": campaign.setting,
            "narrator_personality": campaign.narrator_personality,
            "module_title": module.title,
            "module_summary": module.summary,
            "guiding_milestone": {
                "title": milestone.title,
                "description": milestone.description,
            },
            "completed_encounter_summaries": list(module.completed_encounter_summaries),
            "player_name": player.name,
            "player_race": player.race,
            "player_hp_current": player.hp_current,
            "player_hp_max": player.hp_max,
            "last_outcome": last_outcome,
            "prior_narrative_context": self.retrieve_memory(
                f"{module.title} {milestone.title}"
            ),
        }
        result = self._plan_agent.run_sync(  # type: ignore[union-attr]
            json.dumps(context, indent=2, sort_keys=True)
        )
        return result.output
