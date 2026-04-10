"""Narrator agent for player-facing output."""

from __future__ import annotations

import json

from campaignnarrator.adapters.openai_adapter import OpenAIAdapter
from campaignnarrator.domain.models import (
    Adjudication,
    Narration,
    PotionOfHealingResolution,
)


class NarratorAgent:
    """Convert adjudications into short player-facing narration."""

    def __init__(self, *, adapter: OpenAIAdapter) -> None:
        self._adapter = adapter

    def narrate(
        self,
        adjudication: Adjudication,
        resolution: PotionOfHealingResolution,
    ) -> Narration:
        """Render a narration for the supplied adjudication."""

        text = self._adapter.generate_text(
            instructions=(
                "You write concise player-facing narration for a tabletop RPG. "
                "Mention the resolved healing amount and the updated hit points. "
            ),
            input_text=json.dumps(
                {
                    "actor": adjudication.action.actor,
                    "action": adjudication.action.summary,
                    "resolution": {
                        "roll_total": resolution.roll_total,
                        "healing_amount": resolution.healing_amount,
                        "hp_before": resolution.hp_before,
                        "hp_after": resolution.hp_after,
                    },
                },
                indent=2,
                sort_keys=True,
            ),
        )
        if not text.strip():
            raise ValueError("empty output")  # noqa: TRY003
        return Narration(text=text, audience="player")
