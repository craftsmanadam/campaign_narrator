"""Narrator agent for player-facing output."""

from __future__ import annotations

import json

from pydantic_ai import Agent

from campaignnarrator.adapters.pydantic_ai_adapter import PydanticAIAdapter
from campaignnarrator.domain.models import (
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


class NarratorAgent:
    """Convert public encounter frames into short player-facing narration."""

    def __init__(
        self,
        *,
        adapter: PydanticAIAdapter,
        personality: str,
        _scene_agent: object | None = None,
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
