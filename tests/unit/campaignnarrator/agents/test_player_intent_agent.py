"""Unit tests for PlayerIntentAgent."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from campaignnarrator.agents.player_intent_agent import PlayerIntentAgent
from campaignnarrator.agents.prompts import PLAYER_INTENT_INSTRUCTIONS
from campaignnarrator.domain.models import EncounterPhase, IntentCategory, PlayerIntent


def test_player_intent_instructions_cover_all_categories() -> None:
    for value in (
        "hostile_action",
        "skill_check",
        "npc_dialogue",
        "scene_observation",
        "save_exit",
        "status",
        "recap",
        "look_around",
    ):
        assert value in PLAYER_INTENT_INSTRUCTIONS.lower(), f"Missing category: {value}"


def test_player_intent_instructions_include_check_hint_rule() -> None:
    assert "check_hint" in PLAYER_INTENT_INSTRUCTIONS
    assert "skill_check" in PLAYER_INTENT_INSTRUCTIONS.lower()


def test_player_intent_instructions_include_present_tense_rule() -> None:
    assert "present" in PLAYER_INTENT_INSTRUCTIONS.lower()


def _make_agent(intent: PlayerIntent) -> PlayerIntentAgent:
    mock_agent = MagicMock()
    mock_agent.run_sync.return_value.output = intent
    return PlayerIntentAgent(adapter=MagicMock(), _agent=mock_agent)


def test_classify_returns_player_intent() -> None:
    expected = PlayerIntent(
        category=IntentCategory.SKILL_CHECK,
        check_hint="Stealth",
        reason="Player wants to sneak",
    )
    agent = _make_agent(expected)
    result = agent.classify(
        "I try to sneak past the guards",
        phase=EncounterPhase.SOCIAL,
        setting="A castle courtyard",
        recent_events=(),
        actor_summaries=(),
    )
    assert result.category is IntentCategory.SKILL_CHECK
    assert result.check_hint == "Stealth"


def test_classify_passes_serialized_context_to_agent() -> None:
    mock_agent = MagicMock()
    mock_agent.run_sync.return_value.output = PlayerIntent(
        category=IntentCategory.SCENE_OBSERVATION
    )
    agent = PlayerIntentAgent(adapter=MagicMock(), _agent=mock_agent)
    agent.classify(
        "I look around",
        phase=EncounterPhase.SOCIAL,
        setting="A castle courtyard",
        recent_events=("A goblin appeared",),
        actor_summaries=("Talia (player)",),
    )
    call_args = mock_agent.run_sync.call_args[0][0]
    payload = json.loads(call_args)
    assert payload["player_input"] == "I look around"
    assert payload["setting"] == "A castle courtyard"
    assert "A goblin appeared" in payload["recent_events"]
    assert "Talia (player)" in payload["actor_summaries"]


def test_classify_includes_phase_in_context() -> None:
    mock_agent = MagicMock()
    mock_agent.run_sync.return_value.output = PlayerIntent(
        category=IntentCategory.SCENE_OBSERVATION
    )
    agent = PlayerIntentAgent(adapter=MagicMock(), _agent=mock_agent)
    agent.classify(
        "I move forward",
        phase=EncounterPhase.SOCIAL,
        setting="Roadside camp",
        recent_events=(),
        actor_summaries=(),
    )
    payload = json.loads(mock_agent.run_sync.call_args[0][0])
    assert payload["phase"] == "social"


def test_classify_non_skill_check_has_no_check_hint() -> None:
    expected = PlayerIntent(category=IntentCategory.NPC_DIALOGUE, check_hint=None)
    agent = _make_agent(expected)
    result = agent.classify(
        "I ask the merchant about the map",
        phase=EncounterPhase.SOCIAL,
        setting="Market",
        recent_events=(),
        actor_summaries=(),
    )
    assert result.check_hint is None
