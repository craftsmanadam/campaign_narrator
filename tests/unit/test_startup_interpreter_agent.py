"""Unit tests for StartupInterpreterAgent."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from campaignnarrator.agents.startup_interpreter_agent import StartupInterpreterAgent
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel


def _make_agent(intent: str) -> StartupInterpreterAgent:
    def fn(messages: list, info: AgentInfo) -> ModelResponse:
        payload = json.dumps({"intent": intent})
        return ModelResponse(parts=[ToolCallPart("final_result", payload)])

    mock_adapter = MagicMock()
    mock_adapter.model = FunctionModel(fn)
    return StartupInterpreterAgent(adapter=mock_adapter)


def test_interpret_load_campaign() -> None:
    agent = _make_agent("load_campaign")
    assert agent.interpret("yes load it", has_campaign=True) == "load_campaign"


def test_interpret_new_campaign() -> None:
    agent = _make_agent("new_campaign")
    assert agent.interpret("start a new one", has_campaign=True) == "new_campaign"


def test_interpret_confirm_destroy() -> None:
    agent = _make_agent("confirm_destroy")
    assert agent.interpret("discard", has_campaign=True) == "confirm_destroy"


def test_interpret_abort() -> None:
    agent = _make_agent("abort")
    assert agent.interpret("never mind", has_campaign=True) == "abort"
