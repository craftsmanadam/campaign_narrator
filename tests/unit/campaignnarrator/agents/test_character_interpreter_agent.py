"""Unit tests for CharacterInterpreterAgent."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from campaignnarrator.agents.character_interpreter_agent import (
    CharacterInterpreterAgent,
)
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel


def _make_agent(class_name: str) -> CharacterInterpreterAgent:
    def fn(messages: list, info: AgentInfo) -> ModelResponse:
        payload = json.dumps({"class_name": class_name})
        return ModelResponse(parts=[ToolCallPart("final_result", payload)])

    mock_adapter = MagicMock()
    mock_adapter.model = FunctionModel(fn)
    return CharacterInterpreterAgent(adapter=mock_adapter)


def test_interpret_fighter() -> None:
    agent = _make_agent("fighter")
    assert agent.interpret("I want to be a warrior") == "fighter"


def test_interpret_rogue() -> None:
    agent = _make_agent("rogue")
    assert agent.interpret("I prefer stealth and shadows") == "rogue"
