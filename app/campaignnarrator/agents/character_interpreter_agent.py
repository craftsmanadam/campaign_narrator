"""Agent that interprets the player's class choice from free-form text."""

from __future__ import annotations

from pydantic import BaseModel
from pydantic_ai import Agent

from campaignnarrator.adapters.pydantic_ai_adapter import PydanticAIAdapter

_INSTRUCTIONS = (
    "You are helping a player choose their D&D character class. "
    "Based on their description, classify their choice as exactly one of: "
    "'fighter' (warriors, soldiers, knights, paladins, berserkers, any martial class), "
    "'rogue' (thieves, assassins, scouts, rangers, shadows, any stealthy class). "
    "Return the single closest match."
)


class _ClassChoiceResponse(BaseModel):
    class_name: str  # "fighter" or "rogue"


class CharacterInterpreterAgent:
    """Classify a player's class description into a supported template name."""

    def __init__(self, *, adapter: PydanticAIAdapter) -> None:
        self._agent: Agent[None, _ClassChoiceResponse] = Agent(
            adapter.model,
            output_type=_ClassChoiceResponse,
            instructions=_INSTRUCTIONS,
        )

    def interpret(self, player_text: str) -> str:
        """Return 'fighter' or 'rogue'."""
        result = self._agent.run_sync(player_text).output
        return result.class_name
