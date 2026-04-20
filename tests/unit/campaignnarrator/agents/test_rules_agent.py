"""Unit tests for the rules agent."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from campaignnarrator.agents.prompts import RULES_INSTRUCTIONS
from campaignnarrator.agents.rules_agent import RulesAgent
from campaignnarrator.domain.models import (
    EncounterPhase,
    RollRequest,
    RollVisibility,
    RulesAdjudication,
    RulesAdjudicationRequest,
    StateEffect,
)


def _canned_adjudication(**overrides: object) -> RulesAdjudication:
    defaults: dict[str, object] = {
        "is_legal": True,
        "action_type": "social_check",
        "summary": "The goblins back away.",
        "reasoning_summary": "The check succeeds.",
        "roll_requests": (),
        "state_effects": (),
        "rule_references": (),
    }
    defaults.update(overrides)
    return RulesAdjudication(**defaults)


def _make_agent(adjudication: RulesAdjudication) -> RulesAgent:
    """Construct RulesAgent with a scripted _agent mock."""
    mock_agent = MagicMock()
    mock_agent.run_sync.return_value.output = adjudication
    return RulesAgent(adapter=MagicMock(), _agent=mock_agent)


def _make_request(**kwargs: object) -> RulesAdjudicationRequest:
    defaults: dict[str, object] = {
        "actor_id": "pc:talia",
        "intent": "I try to calm them down.",
        "phase": EncounterPhase.SOCIAL,
        "allowed_outcomes": ("de-escalated", "combat"),
    }
    defaults.update(kwargs)
    return RulesAdjudicationRequest(**defaults)


def test_adjudicate_returns_output_from_agent() -> None:
    adj = _canned_adjudication(
        roll_requests=(
            RollRequest(
                owner="player",
                visibility=RollVisibility.PUBLIC,
                expression="1d20+2",
                purpose="Persuasion check",
            ),
        ),
        state_effects=(
            StateEffect(
                effect_type="set_encounter_outcome",
                target="encounter:goblin-camp",
                value="de-escalated",
            ),
        ),
        rule_references=("source/rules/social.md",),
    )
    agent = _make_agent(adj)
    result = agent.adjudicate(_make_request())
    assert result.is_legal is True
    assert result.action_type == "social_check"
    assert len(result.roll_requests) == 1
    assert result.roll_requests[0].expression == "1d20+2"
    assert len(result.state_effects) == 1
    assert result.rule_references == ("source/rules/social.md",)


def test_adjudicate_passes_serialized_request_to_agent() -> None:
    mock_agent = MagicMock()
    mock_agent.run_sync.return_value.output = _canned_adjudication()
    rules_agent = RulesAgent(adapter=MagicMock(), _agent=mock_agent)
    request = _make_request(
        intent="calm the goblin camp",
        compendium_context=("goblin camp lore",),
    )
    rules_agent.adjudicate(request)
    call_args = mock_agent.run_sync.call_args[0][0]
    payload = json.loads(call_args)
    assert payload["intent"] == "calm the goblin camp"
    assert "goblin camp lore" in payload["compendium_context"]


def test_adjudicate_roll_request_without_purpose_produces_none() -> None:
    adj = _canned_adjudication(
        roll_requests=(
            RollRequest(
                owner="player",
                visibility=RollVisibility.PUBLIC,
                expression="1d20+3",
            ),
        )
    )
    agent = _make_agent(adj)
    result = agent.adjudicate(_make_request())
    assert result.roll_requests[0].purpose is None


class FakeRulesRepository:
    def __init__(self, content_by_topic: dict[str, str]) -> None:
        self._content = content_by_topic

    def load_context_for_topics(self, topics: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(
            self._content.get(topic, f"Missing rules context: {topic}")
            for topic in topics
        )


def test_adjudicate_social_phase_injects_loaded_rule_text() -> None:
    repo = FakeRulesRepository(
        {
            "core_resolution": "CORE RESOLUTION RULES",
            "social_interaction": "SOCIAL INTERACTION RULES",
        }
    )
    mock_agent = MagicMock()
    mock_agent.run_sync.return_value.output = _canned_adjudication()
    rules_agent = RulesAgent(
        adapter=MagicMock(), rules_repository=repo, _agent=mock_agent
    )
    rules_agent.adjudicate(_make_request(phase=EncounterPhase.SOCIAL))
    call_args = mock_agent.run_sync.call_args[0][0]
    assert "CORE RESOLUTION RULES" in call_args
    assert "SOCIAL INTERACTION RULES" in call_args


def test_adjudicate_combat_phase_injects_loaded_rule_text() -> None:
    repo = FakeRulesRepository(
        {"core_resolution": "CORE RESOLUTION RULES", "combat": "COMBAT RULES"}
    )
    mock_agent = MagicMock()
    mock_agent.run_sync.return_value.output = _canned_adjudication()
    rules_agent = RulesAgent(
        adapter=MagicMock(), rules_repository=repo, _agent=mock_agent
    )
    rules_agent.adjudicate(_make_request(phase=EncounterPhase.COMBAT))
    call_args = mock_agent.run_sync.call_args[0][0]
    assert "CORE RESOLUTION RULES" in call_args
    assert "COMBAT RULES" in call_args


def test_adjudicate_without_rules_repository_passes_empty_context() -> None:
    mock_agent = MagicMock()
    mock_agent.run_sync.return_value.output = _canned_adjudication()
    rules_agent = RulesAgent(
        adapter=MagicMock(), rules_repository=None, _agent=mock_agent
    )
    rules_agent.adjudicate(_make_request())
    call_args = mock_agent.run_sync.call_args[0][0]
    payload = json.loads(call_args)
    assert payload["rules_context"] == []


def test_stealth_hint_loads_stealth_topic_in_addition_to_social_topics() -> None:
    captured: list[tuple[str, ...]] = []

    class CapturingRulesRepository:
        def load_context_for_topics(self, topics: tuple[str, ...]) -> tuple[str, ...]:
            captured.append(topics)
            return ()

    mock_agent = MagicMock()
    mock_agent.run_sync.return_value.output = _canned_adjudication()
    rules_agent = RulesAgent(
        adapter=MagicMock(),
        rules_repository=CapturingRulesRepository(),
        _agent=mock_agent,
    )
    rules_agent.adjudicate(_make_request(check_hints=("Stealth",)))
    assert "stealth" in captured[0]
    assert "core_resolution" in captured[0]


def test_hide_hint_also_loads_stealth_topic() -> None:
    captured: list[tuple[str, ...]] = []

    class CapturingRulesRepository:
        def load_context_for_topics(self, topics: tuple[str, ...]) -> tuple[str, ...]:
            captured.append(topics)
            return ()

    mock_agent = MagicMock()
    mock_agent.run_sync.return_value.output = _canned_adjudication()
    rules_agent = RulesAgent(
        adapter=MagicMock(),
        rules_repository=CapturingRulesRepository(),
        _agent=mock_agent,
    )
    rules_agent.adjudicate(_make_request(check_hints=("hide",)))
    assert "stealth" in captured[0]


def test_unknown_hint_does_not_expand_topics() -> None:
    captured: list[tuple[str, ...]] = []

    class CapturingRulesRepository:
        def load_context_for_topics(self, topics: tuple[str, ...]) -> tuple[str, ...]:
            captured.append(topics)
            return ()

    mock_agent = MagicMock()
    mock_agent.run_sync.return_value.output = _canned_adjudication()
    rules_agent = RulesAgent(
        adapter=MagicMock(),
        rules_repository=CapturingRulesRepository(),
        _agent=mock_agent,
    )
    rules_agent.adjudicate(_make_request(check_hints=("UnrecognisedHint",)))
    assert "stealth" not in captured[0]


def test_init_raises_type_error_when_adapter_is_not_pydantic_ai_adapter() -> None:
    """RulesAgent without _agent must reject non-PydanticAIAdapter adapters."""
    with pytest.raises(TypeError, match="adapter must be a PydanticAIAdapter"):
        RulesAgent(adapter=object())


def test_rules_instructions_enumerate_valid_effect_types() -> None:
    """All valid state effect types must be named explicitly in the prompt."""
    valid_types = [
        "set_phase",
        "append_public_event",
        "set_encounter_outcome",
        "change_hp",
        "inventory_spent",
    ]
    for effect_type in valid_types:
        assert effect_type in RULES_INSTRUCTIONS, f"Missing effect type: {effect_type}"


def test_rules_instructions_guide_empty_state_effects_for_knowledge_checks() -> None:
    """Prompt must instruct LLM to leave state_effects empty for knowledge/skill checks."""
    assert "state_effects" in RULES_INSTRUCTIONS
    assert (
        "empty" in RULES_INSTRUCTIONS.lower()
        or "no state" in RULES_INSTRUCTIONS.lower()
        or "leave" in RULES_INSTRUCTIONS.lower()
    )
