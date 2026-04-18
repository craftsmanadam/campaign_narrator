"""Agent that generates a full campaign skeleton from the player's brief."""

from __future__ import annotations

import json

from pydantic import BaseModel
from pydantic_ai import Agent

from campaignnarrator.adapters.pydantic_ai_adapter import PydanticAIAdapter

_INSTRUCTIONS = (
    "You are a master dungeon master designing a D&D 5e campaign. "
    "Given a player's brief describing the kind of campaign they want, "
    "generate a complete campaign skeleton. "
    "The hidden_goal, bbeg_name, bbeg_description, and milestones are "
    "NARRATOR-ONLY — the player will never see them. "
    "Generate exactly 3 to 5 milestones that anchor the story arc. "
    "target_level must be between 5 and 7 "
    "(the campaign covers 4-6 levels of gain from level 1). "
    "Make the campaign feel personal to the player's brief."
)


class MilestoneResult(BaseModel):
    milestone_id: str
    title: str
    description: str


class CampaignGenerationResult(BaseModel):
    name: str
    setting: str
    narrator_personality: str
    hidden_goal: str
    bbeg_name: str
    bbeg_description: str
    milestones: list[MilestoneResult]
    target_level: int


class CampaignGeneratorAgent:
    """Generate a complete campaign skeleton from the player's brief."""

    def __init__(self, *, adapter: PydanticAIAdapter) -> None:
        self._agent: Agent[None, CampaignGenerationResult] = Agent(
            adapter.model,
            output_type=CampaignGenerationResult,
            instructions=_INSTRUCTIONS,
        )

    def generate(
        self,
        *,
        player_brief: str,
        character_name: str,
        race: str,
        class_name: str,
        background: str,
    ) -> CampaignGenerationResult:
        """Generate the campaign skeleton. All fields are narrator-internal."""
        context = json.dumps(
            {
                "player_brief": player_brief,
                "character_name": character_name,
                "race": race,
                "class": class_name,
                "background": background,
            }
        )
        return self._agent.run_sync(context).output
