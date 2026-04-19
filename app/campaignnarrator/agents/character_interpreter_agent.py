"""Agent that interprets the player's class choice from free-form text."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel
from pydantic_ai import Agent

from campaignnarrator.adapters.pydantic_ai_adapter import PydanticAIAdapter

_INSTRUCTIONS = (
    "You are interpreting a D&D player's initial character description. "
    "From their free-form text:\n"
    "1. Classify their class as exactly one of: "
    "'fighter' (warrior, soldier, knight, paladin, berserker, or any martial class), "
    "'rogue' (thief, assassin, scout, ranger, shadow, or any stealthy class).\n"
    "2. Extract their character name if they mention one (null if not mentioned).\n"
    "3. Extract their race/heritage if they mention one (null if not mentioned). "
    "Recognized races: Human, Elf, Dwarf, Halfling, Half-Elf, Half-Orc, Gnome, "
    "Dragonborn, Tiefling."
)


@dataclass(frozen=True)
class CharacterIntake:
    """Parsed intake from a player's initial character description."""

    class_name: str  # "fighter" or "rogue"
    name: str | None = None
    race: str | None = None


class _ClassChoiceResponse(BaseModel):
    class_name: str
    name: str | None = None
    race: str | None = None


class CharacterInterpreterAgent:
    """Classify a player's class and extract any name/race already provided."""

    def __init__(self, *, adapter: PydanticAIAdapter) -> None:
        self._agent: Agent[None, _ClassChoiceResponse] = Agent(
            adapter.model,
            output_type=_ClassChoiceResponse,
            instructions=_INSTRUCTIONS,
        )

    def interpret(self, player_text: str) -> CharacterIntake:
        """Return class plus any name/race already mentioned by the player."""
        result = self._agent.run_sync(player_text).output
        return CharacterIntake(
            class_name=result.class_name,
            name=result.name or None,
            race=result.race or None,
        )
