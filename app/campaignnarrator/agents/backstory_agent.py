"""Agent that drafts a character backstory from player-provided fragments."""

from __future__ import annotations

import json

from campaignnarrator.adapters.pydantic_ai_adapter import PydanticAIAdapter

_INSTRUCTIONS = (
    "You are a storyteller crafting a D&D character backstory. "
    "Write a single paragraph (150-300 words) in second person present tense "
    "('You grew up...') that weaves the player's fragments into a vivid, "
    "cohesive backstory. Be specific and atmospheric. "
    "Do not invent mechanics or game stats."
)


class BackstoryAgent:
    """Draft a character backstory from player fragments on request."""

    def __init__(self, *, adapter: PydanticAIAdapter) -> None:
        self._adapter = adapter

    def draft(
        self,
        *,
        fragments: str,
        character_name: str,
        race: str,
        class_name: str,
    ) -> str:
        """Return a drafted backstory paragraph.

        Raises ValueError if the model returns an empty response.
        """
        context = json.dumps(
            {
                "character_name": character_name,
                "race": race,
                "class": class_name,
                "player_fragments": fragments,
            }
        )
        text = self._adapter.generate_text(
            instructions=_INSTRUCTIONS,
            input_text=context,
        )
        if not text.strip():
            raise ValueError("empty backstory")  # noqa: TRY003
        return text
