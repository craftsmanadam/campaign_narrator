"""Unit tests for actor_summaries helpers."""

from __future__ import annotations

from campaignnarrator.domain.models import ActorState, ActorType
from campaignnarrator.orchestrators.actor_summaries import actor_modifiers


def _actor(**overrides: object) -> ActorState:
    defaults: dict[str, object] = dict(
        actor_id="pc:test",
        name="Test",
        actor_type=ActorType.PC,
        hp_max=10,
        hp_current=10,
        armor_class=12,
        strength=10,
        dexterity=14,
        constitution=10,
        intelligence=10,
        wisdom=16,
        charisma=8,
        proficiency_bonus=3,
        initiative_bonus=2,
        speed=30,
        attacks_per_action=1,
        action_options=("Attack",),
        ac_breakdown=(),
        level=5,
    )
    defaults.update(overrides)
    return ActorState(**defaults)  # type: ignore[arg-type]


def test_actor_modifiers_basic_values() -> None:
    """actor_modifiers returns correct ability mods, proficiency, and level."""
    expected_strength_mod = 2  # (14-10)//2
    expected_dexterity_mod = 0  # (10-10)//2
    expected_constitution_mod = 1  # (12-10)//2
    expected_intelligence_mod = -1  # (8-10)//2
    expected_wisdom_mod = 3  # (16-10)//2
    expected_charisma_mod = -2  # (6-10)//2
    expected_proficiency_bonus = 3
    expected_level = 5
    actor = _actor(
        strength=14,
        dexterity=10,
        constitution=12,
        intelligence=8,
        wisdom=16,
        charisma=6,
        proficiency_bonus=expected_proficiency_bonus,
        level=expected_level,
    )
    result = actor_modifiers(actor)
    assert result["strength_mod"] == expected_strength_mod
    assert result["dexterity_mod"] == expected_dexterity_mod
    assert result["constitution_mod"] == expected_constitution_mod
    assert result["intelligence_mod"] == expected_intelligence_mod
    assert result["wisdom_mod"] == expected_wisdom_mod
    assert result["charisma_mod"] == expected_charisma_mod
    assert result["proficiency_bonus"] == expected_proficiency_bonus
    assert result["level"] == expected_level


def test_actor_modifiers_with_class_levels() -> None:
    """actor_modifiers adds per-class-level entries when class_levels is set."""
    expected_class_level = 9
    actor = ActorState(
        actor_id="pc:multi",
        name="Multi",
        actor_type=ActorType.PC,
        hp_max=20,
        hp_current=20,
        armor_class=14,
        strength=10,
        dexterity=10,
        constitution=10,
        intelligence=10,
        wisdom=10,
        charisma=10,
        proficiency_bonus=4,
        initiative_bonus=0,
        speed=30,
        attacks_per_action=2,
        action_options=("Attack",),
        ac_breakdown=(),
        level=18,
        class_levels=(
            ("Fighter", expected_class_level),
            ("Wizard", expected_class_level),
        ),
    )
    result = actor_modifiers(actor)
    assert result["fighter_level"] == expected_class_level
    assert result["wizard_level"] == expected_class_level


def test_actor_modifiers_negative_ability_modifier() -> None:
    """Strength 8 produces strength_mod of -1."""
    actor = _actor(strength=8)
    result = actor_modifiers(actor)
    assert result["strength_mod"] == -1
