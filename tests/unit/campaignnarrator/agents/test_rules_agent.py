"""Unit tests for the rules agent."""

from __future__ import annotations

import json
import logging
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


def test_adjudicate_includes_encounter_id_in_input() -> None:
    """encounter_id must appear in the serialized input so the LLM can form correct targets."""
    mock_agent = MagicMock()
    mock_agent.run_sync.return_value.output = _canned_adjudication()
    rules_agent = RulesAgent(adapter=MagicMock(), _agent=mock_agent)
    request = _make_request(encounter_id="goblin-camp")
    rules_agent.adjudicate(request)
    call_args = mock_agent.run_sync.call_args[0][0]
    payload = json.loads(call_args)
    assert payload["encounter_id"] == "goblin-camp"


def test_adjudicate_includes_visible_actors_context_in_input() -> None:
    """visible_actors_context must be serialized into the input when present."""
    mock_agent = MagicMock()
    mock_agent.run_sync.return_value.output = _canned_adjudication()
    rules_agent = RulesAgent(adapter=MagicMock(), _agent=mock_agent)
    actors = (
        "Actor pc:talia — Talia (player), AC 18, HP 45/45",
        "Actor npc:goblin-1 — Goblin Scout 1 (npc), AC 15, HP 7/7",
    )
    request = _make_request(visible_actors_context=actors)
    rules_agent.adjudicate(request)
    call_args = mock_agent.run_sync.call_args[0][0]
    payload = json.loads(call_args)
    assert "visible_actors_context" in payload
    assert any("pc:talia" in entry for entry in payload["visible_actors_context"])
    assert any("npc:goblin-1" in entry for entry in payload["visible_actors_context"])


def test_adjudicate_omits_visible_actors_context_when_empty() -> None:
    """visible_actors_context must not appear in the input when the tuple is empty."""
    mock_agent = MagicMock()
    mock_agent.run_sync.return_value.output = _canned_adjudication()
    rules_agent = RulesAgent(adapter=MagicMock(), _agent=mock_agent)
    request = _make_request()
    rules_agent.adjudicate(request)
    call_args = mock_agent.run_sync.call_args[0][0]
    payload = json.loads(call_args)
    assert "visible_actors_context" not in payload


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


def test_adjudicate_skill_check_hint_loads_skill_check_topic() -> None:
    """A recognised D&D 5e skill name as check_hint selects 'skill_check' topic."""
    captured: list[tuple[str, ...]] = []

    class CapturingRepo:
        def load_context_for_topics(self, topics: tuple[str, ...]) -> tuple[str, ...]:
            captured.append(topics)
            return ()

    mock_agent = MagicMock()
    mock_agent.run_sync.return_value.output = _canned_adjudication()
    rules_agent = RulesAgent(
        adapter=MagicMock(), rules_repository=CapturingRepo(), _agent=mock_agent
    )
    rules_agent.adjudicate(_make_request(check_hints=("Persuasion",)))
    assert "skill_check" in captured[0]
    assert "core_resolution" not in captured[0]
    assert "social_interaction" not in captured[0]


def test_adjudicate_no_hint_loads_social_interaction_topic() -> None:
    """No check_hint selects 'social_interaction' base topic."""
    captured: list[tuple[str, ...]] = []

    class CapturingRepo:
        def load_context_for_topics(self, topics: tuple[str, ...]) -> tuple[str, ...]:
            captured.append(topics)
            return ()

    mock_agent = MagicMock()
    mock_agent.run_sync.return_value.output = _canned_adjudication()
    rules_agent = RulesAgent(
        adapter=MagicMock(), rules_repository=CapturingRepo(), _agent=mock_agent
    )
    rules_agent.adjudicate(_make_request())
    assert "social_interaction" in captured[0]
    assert "core_resolution" not in captured[0]


def test_adjudicate_stealth_hint_loads_skill_check_and_stealth_topics() -> None:
    """'Stealth' loads skill_check + stealth extra topic."""
    captured: list[tuple[str, ...]] = []

    class CapturingRepo:
        def load_context_for_topics(self, topics: tuple[str, ...]) -> tuple[str, ...]:
            captured.append(topics)
            return ()

    mock_agent = MagicMock()
    mock_agent.run_sync.return_value.output = _canned_adjudication()
    rules_agent = RulesAgent(
        adapter=MagicMock(), rules_repository=CapturingRepo(), _agent=mock_agent
    )
    rules_agent.adjudicate(_make_request(check_hints=("Stealth",)))
    assert "skill_check" in captured[0]
    assert "stealth" in captured[0]
    assert "core_resolution" not in captured[0]


def test_hide_hint_also_loads_stealth_topic() -> None:
    """'hide' is not a skill name — falls back to social_interaction + stealth extra."""
    captured: list[tuple[str, ...]] = []

    class CapturingRepo:
        def load_context_for_topics(self, topics: tuple[str, ...]) -> tuple[str, ...]:
            captured.append(topics)
            return ()

    mock_agent = MagicMock()
    mock_agent.run_sync.return_value.output = _canned_adjudication()
    rules_agent = RulesAgent(
        adapter=MagicMock(),
        rules_repository=CapturingRepo(),
        _agent=mock_agent,
    )
    rules_agent.adjudicate(_make_request(check_hints=("hide",)))
    assert "stealth" in captured[0]
    assert "core_resolution" not in captured[0]


def test_unknown_hint_does_not_expand_topics() -> None:
    """An unrecognised hint falls back to social_interaction with no extra topics."""
    captured: list[tuple[str, ...]] = []

    class CapturingRepo:
        def load_context_for_topics(self, topics: tuple[str, ...]) -> tuple[str, ...]:
            captured.append(topics)
            return ()

    mock_agent = MagicMock()
    mock_agent.run_sync.return_value.output = _canned_adjudication()
    rules_agent = RulesAgent(
        adapter=MagicMock(),
        rules_repository=CapturingRepo(),
        _agent=mock_agent,
    )
    rules_agent.adjudicate(_make_request(check_hints=("UnrecognisedHint",)))
    assert "stealth" not in captured[0]
    assert "skill_check" not in captured[0]
    assert "social_interaction" in captured[0]


def test_adjudicate_combat_phase_no_hint_loads_attack_resolution_topic() -> None:
    """phase=COMBAT with no check_hint selects 'attack_resolution', not 'social_interaction'."""
    captured: list[tuple[str, ...]] = []

    class CapturingRepo:
        def load_context_for_topics(self, topics: tuple[str, ...]) -> tuple[str, ...]:
            captured.append(topics)
            return ()

    mock_agent = MagicMock()
    mock_agent.run_sync.return_value.output = _canned_adjudication()
    rules_agent = RulesAgent(
        adapter=MagicMock(), rules_repository=CapturingRepo(), _agent=mock_agent
    )
    rules_agent.adjudicate(_make_request(phase=EncounterPhase.COMBAT))
    assert "attack_resolution" in captured[0]
    assert "social_interaction" not in captured[0]
    assert "core_resolution" not in captured[0]


def test_adjudicate_logs_error_when_context_exceeds_size_threshold(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """adjudicate() logs an error when total rule context chars exceed the threshold."""
    large_text = "x" * 3501

    class LargeRulesRepo:
        def load_context_for_topics(self, topics: tuple[str, ...]) -> tuple[str, ...]:
            return (large_text,)

    mock_agent = MagicMock()
    mock_agent.run_sync.return_value.output = _canned_adjudication()
    rules_agent = RulesAgent(
        adapter=MagicMock(), rules_repository=LargeRulesRepo(), _agent=mock_agent
    )
    with caplog.at_level(logging.ERROR, logger="campaignnarrator.agents.rules_agent"):
        rules_agent.adjudicate(_make_request())

    assert any("exceeds threshold" in r.message for r in caplog.records)
    mock_agent.run_sync.assert_called_once()


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


def test_rules_instructions_document_target_format() -> None:
    """Prompt must tell the LLM the correct target format for encounter-level effects."""
    assert "encounter:{encounter_id}" in RULES_INSTRUCTIONS
    assert "TARGETING RULES" in RULES_INSTRUCTIONS


def test_rules_instructions_guide_empty_state_effects_for_knowledge_checks() -> None:
    """Prompt must instruct LLM to leave state_effects empty for knowledge/skill checks."""
    assert "state_effects" in RULES_INSTRUCTIONS
    assert (
        "empty" in RULES_INSTRUCTIONS.lower()
        or "no state" in RULES_INSTRUCTIONS.lower()
        or "leave" in RULES_INSTRUCTIONS.lower()
    )


def test_rules_instructions_include_skill_ability_mapping() -> None:
    """RULES_INSTRUCTIONS must have an authoritative skill→ability table."""
    assert "Stealth" in RULES_INSTRUCTIONS
    assert "Dexterity" in RULES_INSTRUCTIONS
    assert "Athletics" in RULES_INSTRUCTIONS
    assert "Strength" in RULES_INSTRUCTIONS
    assert "Perception" in RULES_INSTRUCTIONS
    assert "Wisdom" in RULES_INSTRUCTIONS
    assert "Persuasion" in RULES_INSTRUCTIONS
    assert "Charisma" in RULES_INSTRUCTIONS
