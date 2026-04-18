"""Agent that interprets player intent at the game startup decision point."""

from __future__ import annotations

import json

from pydantic import BaseModel
from pydantic_ai import Agent

from campaignnarrator.adapters.pydantic_ai_adapter import PydanticAIAdapter

_INSTRUCTIONS = (
    "You are interpreting a player's response at a D&D game startup screen. "
    "Classify their intent as exactly one of: "
    "'load_campaign' (they want to resume their saved campaign), "
    "'new_campaign' (they want to start a brand new campaign), "
    "'confirm_destroy' (they are explicitly confirming they want to "
    "destroy the old campaign), "
    "'abort' (they want to do nothing or are unsure). "
    "When in doubt, prefer 'abort' over 'confirm_destroy'."
)


class _IntentResponse(BaseModel):
    intent: str  # one of the four values above


class StartupInterpreterAgent:
    """Classify a player's free-form startup response into a structured intent."""

    def __init__(self, *, adapter: PydanticAIAdapter) -> None:
        self._agent: Agent[None, _IntentResponse] = Agent(
            adapter.model,
            output_type=_IntentResponse,
            instructions=_INSTRUCTIONS,
        )

    def interpret(self, player_text: str, *, has_campaign: bool) -> str:
        """Return one of: 'load_campaign', 'new_campaign', 'confirm_destroy', 'abort'."""  # noqa: E501
        context = json.dumps({"player_text": player_text, "has_campaign": has_campaign})
        result = self._agent.run_sync(context).output
        return result.intent
