"""Unit tests for CampaignGeneratorAgent."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from campaignnarrator.agents.campaign_generator_agent import (
    CampaignGenerationResult,
    CampaignGeneratorAgent,
)
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

_SAMPLE_RESULT = {
    "name": "The Cursed Coast",
    "setting": "A fog-draped coastal city where the dead walk at low tide.",
    "narrator_personality": "Grim and theatrical, with a taste for irony.",
    "hidden_goal": "Awaken the drowned god Malachar to unmake the living world.",
    "bbeg_name": "Malachar",
    "bbeg_description": "A lich bound to the tides, patient as the ocean.",
    "milestones": [
        {
            "milestone_id": "m1",
            "title": "First Blood",
            "description": "Survive the docks.",
        },
        {
            "milestone_id": "m2",
            "title": "The Cult",
            "description": "Unmask the sea cult.",
        },
        {"milestone_id": "m3", "title": "Reckoning", "description": "Face Malachar."},
    ],
    "target_level": 5,
}


_EXPECTED_MILESTONE_COUNT = 3
_EXPECTED_TARGET_LEVEL = 5


def _make_agent() -> CampaignGeneratorAgent:
    def fn(messages: list, info: AgentInfo) -> ModelResponse:
        payload = json.dumps(_SAMPLE_RESULT)
        return ModelResponse(parts=[ToolCallPart("final_result", payload)])

    mock_adapter = MagicMock()
    mock_adapter.model = FunctionModel(fn)
    return CampaignGeneratorAgent(adapter=mock_adapter)


def test_generate_returns_campaign_result() -> None:
    agent = _make_agent()
    result = agent.generate(
        player_brief="Dark coastal horror with undead.",
        character_name="Aldric",
        race="Human",
        class_name="fighter",
        background="Former soldier.",
    )
    assert isinstance(result, CampaignGenerationResult)
    assert result.name == "The Cursed Coast"
    assert result.bbeg_name == "Malachar"
    assert len(result.milestones) == _EXPECTED_MILESTONE_COUNT
    assert result.target_level == _EXPECTED_TARGET_LEVEL


def test_generate_milestones_have_correct_fields() -> None:
    agent = _make_agent()
    result = agent.generate(
        player_brief="anything",
        character_name="X",
        race="Human",
        class_name="fighter",
        background="",
    )
    assert result.milestones[0].milestone_id == "m1"
    assert result.milestones[0].title == "First Blood"
