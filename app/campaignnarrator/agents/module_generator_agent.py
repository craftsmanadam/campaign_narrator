"""Agent that generates the next story module in a campaign."""

from __future__ import annotations

import json

from pydantic import AliasChoices, BaseModel, Field
from pydantic_ai import Agent

from campaignnarrator.adapters.pydantic_ai_adapter import PydanticAIAdapter

_INSTRUCTIONS = (
    "You are a dungeon master designing the next story module in an ongoing "
    "D&D 5e campaign. "
    "Given the campaign's setting, milestones, and a list of completed "
    "module summaries, "
    "generate a new module that moves the story toward (but does not "
    "necessarily complete) "
    "one of the milestones."
)


class ModuleGenerationResult(BaseModel):
    # Ollama sometimes generates "module_title" instead of "title"; accept both.
    title: str = Field(validation_alias=AliasChoices("title", "module_title"))
    summary: str
    guiding_milestone_id: str


class ModuleGeneratorAgent:
    """Generate the next campaign module lazily, guided by milestones."""

    def __init__(self, *, adapter: PydanticAIAdapter) -> None:
        self._agent: Agent[None, ModuleGenerationResult] = Agent(
            adapter.model,
            output_type=ModuleGenerationResult,
            instructions=_INSTRUCTIONS,
        )

    def generate(
        self,
        *,
        campaign_name: str,
        setting: str,
        milestones: list[dict[str, str]],
        current_milestone_index: int,
        completed_module_summaries: list[str],
    ) -> ModuleGenerationResult:
        """Generate the next module."""
        context = json.dumps(
            {
                "campaign_name": campaign_name,
                "setting": setting,
                "milestones": milestones,
                "current_milestone_index": current_milestone_index,
                "completed_module_summaries": completed_module_summaries,
            }
        )
        return self._agent.run_sync(context).output
