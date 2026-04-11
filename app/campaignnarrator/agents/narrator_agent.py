"""Narrator agent for player-facing output."""

from __future__ import annotations

import json

from campaignnarrator.adapters.openai_adapter import OpenAIAdapter
from campaignnarrator.domain.models import Narration, NarrationFrame


class NarratorAgent:
    """Convert public encounter frames into short player-facing narration."""

    def __init__(self, *, adapter: OpenAIAdapter) -> None:
        self._adapter = adapter

    def narrate(self, frame: NarrationFrame) -> Narration:
        """Render narration for the supplied public frame."""

        text = self._adapter.generate_text(
            instructions=(
                "Write player-facing tabletop RPG narration. "
                "Use only provided public and allowed context. "
                "Do not invent mechanics, rolls, HP changes, inventory changes, "
                "or hidden facts. "
                "For status_response and recap_response, concise status-like output "
                "is allowed."
            ),
            input_text=json.dumps(
                {
                    "purpose": frame.purpose,
                    "phase": frame.phase.value,
                    "setting": frame.setting,
                    "public_actor_summaries": frame.public_actor_summaries,
                    "visible_npc_summaries": frame.visible_npc_summaries,
                    "recent_public_events": frame.recent_public_events,
                    "resolved_outcomes": frame.resolved_outcomes,
                    "allowed_disclosures": frame.allowed_disclosures,
                    "tone_guidance": frame.tone_guidance,
                },
                indent=2,
                sort_keys=True,
            ),
        )
        if not text.strip():
            raise ValueError("empty narration output")  # noqa: TRY003
        return Narration(text=text, audience="player")
