"""Unit tests for CharacterInterpreterAgent."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from campaignnarrator.agents.character_interpreter_agent import (
    CharacterIntake,
    CharacterInterpreterAgent,
)
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel


def _make_agent(
    class_name: str,
    *,
    name: str | None = None,
    race: str | None = None,
) -> CharacterInterpreterAgent:
    def fn(messages: list, info: AgentInfo) -> ModelResponse:
        payload = json.dumps({"class_name": class_name, "name": name, "race": race})
        return ModelResponse(parts=[ToolCallPart("final_result", payload)])

    mock_adapter = MagicMock()
    mock_adapter.model = FunctionModel(fn)
    return CharacterInterpreterAgent(adapter=mock_adapter)


def test_interpret_fighter() -> None:
    agent = _make_agent("fighter")
    assert agent.interpret("I want to be a warrior").class_name == "fighter"


def test_interpret_rogue() -> None:
    agent = _make_agent("rogue")
    assert agent.interpret("I prefer stealth and shadows").class_name == "rogue"


def test_interpret_extracts_name_when_present() -> None:
    """Name mentioned in the initial text should be returned in the intake."""
    agent = _make_agent("fighter", name="Gareth of Halsforth")
    result = agent.interpret("I am a warrior named Gareth of Halsforth")
    assert result.name == "Gareth of Halsforth"


def test_interpret_extracts_race_when_present() -> None:
    """Race mentioned in the initial text should be returned in the intake."""
    agent = _make_agent("fighter", race="Human")
    result = agent.interpret("I'm a human warrior")
    assert result.race == "Human"


def test_interpret_name_is_none_when_not_mentioned() -> None:
    agent = _make_agent("fighter")
    assert agent.interpret("I want to be a warrior").name is None


def test_interpret_race_is_none_when_not_mentioned() -> None:
    agent = _make_agent("fighter")
    assert agent.interpret("I want to be a warrior").race is None


def test_interpret_returns_character_intake() -> None:
    agent = _make_agent("fighter", name="Aldric", race="Human")
    result = agent.interpret("I am Aldric, a human fighter")
    assert result == CharacterIntake(class_name="fighter", name="Aldric", race="Human")
