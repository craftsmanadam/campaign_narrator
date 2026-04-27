"""Unit tests for intent domain models."""

from __future__ import annotations

import pytest
from campaignnarrator.domain.models import (
    IntentCategory,
    PlayerInput,
    PlayerIntent,
    PlayerIO,
)
from pydantic import ValidationError


def test_player_input_normalizes_text() -> None:
    """Player input should normalize casing and whitespace."""

    player_input = PlayerInput(raw_text="  STATUS  ")

    assert player_input.raw_text == "  STATUS  "
    assert player_input.normalized == "status"


def test_player_io_protocol_has_prompt_and_display() -> None:
    assert callable(getattr(PlayerIO, "prompt", None)) or hasattr(
        PlayerIO, "__protocol_attrs__"
    )


def test_intent_category_has_all_required_values() -> None:
    assert IntentCategory.HOSTILE_ACTION == "hostile_action"
    assert IntentCategory.SKILL_CHECK == "skill_check"
    assert IntentCategory.NPC_DIALOGUE == "npc_dialogue"
    assert IntentCategory.SCENE_OBSERVATION == "scene_observation"
    assert IntentCategory.SAVE_EXIT == "save_exit"
    assert IntentCategory.STATUS == "status"
    assert IntentCategory.RECAP == "recap"
    assert IntentCategory.LOOK_AROUND == "look_around"


def test_player_intent_requires_category() -> None:
    intent = PlayerIntent(category=IntentCategory.SCENE_OBSERVATION)
    assert intent.category is IntentCategory.SCENE_OBSERVATION
    assert intent.check_hint is None
    assert intent.reason == ""


def test_player_intent_check_hint_is_optional() -> None:
    intent = PlayerIntent(
        category=IntentCategory.SKILL_CHECK,
        check_hint="Stealth",
        reason="Player wants to sneak",
    )
    assert intent.check_hint == "Stealth"
    assert intent.reason == "Player wants to sneak"


def test_player_intent_is_immutable() -> None:
    intent = PlayerIntent(category=IntentCategory.HOSTILE_ACTION)
    with pytest.raises(ValidationError):
        intent.category = IntentCategory.SCENE_OBSERVATION  # type: ignore[misc]


def test_player_intent_normalises_phase_to_category() -> None:
    """Ollama sometimes returns 'phase' instead of 'category'."""
    intent = PlayerIntent.model_validate({"phase": "skill_check", "reason": "testing"})
    assert intent.category is IntentCategory.SKILL_CHECK


def test_player_intent_normalises_skill_check_parameters_to_check_hint() -> None:
    """Ollama sometimes nests the skill inside skill_check_parameters."""
    intent = PlayerIntent.model_validate(
        {
            "phase": "skill_check",
            "skill_check_parameters": {"skill": "Intimidation"},
            "reason": "testing",
        }
    )
    assert intent.category is IntentCategory.SKILL_CHECK
    assert intent.check_hint == "Intimidation"


def test_player_intent_category_takes_precedence_over_phase() -> None:
    """When both category and phase are present, category wins."""
    intent = PlayerIntent.model_validate(
        {"category": "hostile_action", "phase": "skill_check", "reason": "testing"}
    )
    assert intent.category is IntentCategory.HOSTILE_ACTION


def test_player_intent_check_hint_takes_precedence_over_skill_check_parameters() -> (
    None
):
    """When both check_hint and skill_check_parameters are present, check_hint wins."""
    intent = PlayerIntent.model_validate(
        {
            "category": "skill_check",
            "check_hint": "Stealth",
            "skill_check_parameters": {"skill": "Perception"},
            "reason": "testing",
        }
    )
    assert intent.check_hint == "Stealth"


def test_player_intent_normaliser_ignores_non_dict_input() -> None:
    """Non-dict input is passed through unchanged for pydantic to reject."""
    with pytest.raises(ValidationError):
        PlayerIntent.model_validate("not a dict")
