"""Narrator agent for player-facing output."""

from __future__ import annotations

import json

from pydantic_ai import Agent

from campaignnarrator.adapters.pydantic_ai_adapter import PydanticAIAdapter
from campaignnarrator.domain.models import (
    CombatAssessment,
    CritReview,
    Narration,
    NarrationFrame,
    SceneOpeningResponse,
)

_BASE_NARRATE_INSTRUCTIONS = (
    "Write player-facing tabletop RPG narration. "
    "Use only provided public and allowed context. "
    "Do not invent mechanics, rolls, HP changes, inventory changes, "
    "or hidden facts. "
    "For status_response and recap_response, concise status-like output "
    "is allowed."
)

_SCENE_OPENING_INSTRUCTIONS = (
    "You are opening a new encounter scene. "
    "Write immersive player-facing narration that sets the scene. "
    "Also choose a short scene tone phrase (8 words or fewer) that captures the "
    "emotional register (e.g. 'tense and foreboding', 'warm and welcoming', "
    "'chaotic and urgent')."
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


class NarratorAgent:
    """Convert public encounter frames into short player-facing narration."""

    def __init__(
        self,
        *,
        adapter: PydanticAIAdapter,
        personality: str = "",
        _scene_agent: object | None = None,
        _assess_agent: object | None = None,
        _crit_agent: object | None = None,
    ) -> None:
        self._adapter = adapter
        self._personality = personality
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

    def _instructions(self, base: str) -> str:
        return f"{self._personality}\n\n{base}" if self._personality else base

    def narrate(self, frame: NarrationFrame) -> Narration:
        """Render narration for the supplied public frame."""
        frame_dict = {
            "purpose": frame.purpose,
            "phase": frame.phase.value,
            "setting": frame.setting,
            "public_actor_summaries": list(frame.public_actor_summaries),
            "visible_npc_summaries": list(frame.visible_npc_summaries),
            "recent_public_events": list(frame.recent_public_events),
            "resolved_outcomes": list(frame.resolved_outcomes),
            "allowed_disclosures": list(frame.allowed_disclosures),
            "tone_guidance": frame.tone_guidance,
        }
        frame_json = json.dumps(frame_dict, indent=2, sort_keys=True)

        if frame.purpose == "scene_opening":
            result = self._scene_agent.run_sync(frame_json).output
            if not result.text.strip():
                raise ValueError("empty narration output")  # noqa: TRY003
            return Narration(
                text=result.text,
                audience="player",
                scene_tone=result.scene_tone,
            )

        text = self._adapter.generate_text(
            instructions=self._instructions(_BASE_NARRATE_INSTRUCTIONS),
            input_text=frame_json,
        )
        if not text.strip():
            raise ValueError("empty narration output")  # noqa: TRY003
        return Narration(text=text, audience="player")

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
