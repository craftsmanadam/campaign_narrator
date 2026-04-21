"""Unit tests for ModuleGeneratorAgent."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from campaignnarrator.agents.module_generator_agent import (
    ModuleGenerationResult,
    ModuleGeneratorAgent,
)
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

_SAMPLE_RESULT = {
    "title": "The Dockside Murders",
    "summary": "Bodies wash ashore nightly. The city guard is bribed to silence.",
    "guiding_milestone_id": "m1",
    "opening_encounter_seed": (
        "You arrive at the fog-shrouded docks of Darkholm at dusk. "
        "A sailor's corpse bobs in the black water. "
        "A hooded figure watches from the shadows."
    ),
}


_MILESTONE_M1 = {
    "milestone_id": "m1",
    "title": "First Blood",
    "description": "Survive.",
}


def _make_agent() -> ModuleGeneratorAgent:
    def fn(messages: list, info: AgentInfo) -> ModelResponse:
        payload = json.dumps(_SAMPLE_RESULT)
        return ModelResponse(parts=[ToolCallPart("final_result", payload)])

    mock_adapter = MagicMock()
    mock_adapter.model = FunctionModel(fn)
    return ModuleGeneratorAgent(adapter=mock_adapter)


def test_generate_returns_module_result() -> None:
    agent = _make_agent()
    result = agent.generate(
        campaign_name="The Cursed Coast",
        setting="A fog-draped coastal city.",
        milestones=[_MILESTONE_M1],
        current_milestone_index=0,
        completed_module_summaries=[],
    )
    assert isinstance(result, ModuleGenerationResult)
    assert result.title == "The Dockside Murders"
    assert result.guiding_milestone_id == "m1"
    assert "docks" in result.opening_encounter_seed.lower()


def test_generate_accepts_module_title_alias() -> None:
    """Ollama sometimes outputs 'module_title' instead of 'title'; both must work."""
    aliased_result = {**_SAMPLE_RESULT, "module_title": _SAMPLE_RESULT["title"]}
    del aliased_result["title"]

    def fn(messages: list, info: AgentInfo) -> ModelResponse:
        return ModelResponse(
            parts=[ToolCallPart("final_result", json.dumps(aliased_result))]
        )

    mock_adapter = MagicMock()
    mock_adapter.model = FunctionModel(fn)
    agent = ModuleGeneratorAgent(adapter=mock_adapter)
    result = agent.generate(
        campaign_name="Test",
        setting="Test.",
        milestones=[_MILESTONE_M1],
        current_milestone_index=0,
        completed_module_summaries=[],
    )
    assert result.title == "The Dockside Murders"


def test_generate_includes_completed_summaries_in_context() -> None:
    """Verify the agent receives completed module summaries in its input."""
    received: list[str] = []

    def fn(messages: list, info: AgentInfo) -> ModelResponse:
        received.append(messages[0].parts[0].content)
        payload = json.dumps(_SAMPLE_RESULT)
        return ModelResponse(parts=[ToolCallPart("final_result", payload)])

    mock_adapter = MagicMock()
    mock_adapter.model = FunctionModel(fn)
    agent = ModuleGeneratorAgent(adapter=mock_adapter)
    agent.generate(
        campaign_name="Test",
        setting="Test setting.",
        milestones=[],
        current_milestone_index=0,
        completed_module_summaries=["Module 1: The players defeated the bandits."],
    )
    assert "Module 1" in received[0]
