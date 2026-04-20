"""Unit tests for dice_expression resolution."""

from __future__ import annotations

from campaignnarrator.domain.models import ActorState, ActorType
from campaignnarrator.tools.dice_expression import (
    actor_modifiers,
    resolve_dice_expression,
)


def _actor(**overrides: int) -> ActorState:
    defaults = dict(
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
    return ActorState(**defaults)


def test_resolve_wisdom_mod() -> None:
    """Wisdom 16 → modifier +3."""
    actor = _actor(wisdom=16)
    result = resolve_dice_expression("1d20+{wisdom_mod}", actor)
    assert result == "1d20+3"


def test_resolve_dexterity_mod() -> None:
    """Dexterity 14 → modifier +2."""
    actor = _actor(dexterity=14)
    result = resolve_dice_expression("1d20+{dexterity_mod}", actor)
    assert result == "1d20+2"


def test_resolve_proficiency_bonus() -> None:
    actor = _actor(proficiency_bonus=3)
    result = resolve_dice_expression("1d20+{proficiency_bonus}", actor)
    assert result == "1d20+3"


def test_resolve_level() -> None:
    actor = _actor(level=5)
    result = resolve_dice_expression("1d6+{level}", actor)
    assert result == "1d6+5"


def test_resolve_multiple_tokens() -> None:
    """Multiple tokens in one expression are all replaced."""
    actor = _actor(wisdom=16, proficiency_bonus=3)
    result = resolve_dice_expression("1d20+{wisdom_mod}+{proficiency_bonus}", actor)
    assert result == "1d20+3+3"


def test_resolve_negative_modifier() -> None:
    """Negative modifiers collapse the sign: 1d20+{mod} with mod=-2 → 1d20-2."""
    actor = _actor(charisma=6)
    result = resolve_dice_expression("1d20+{charisma_mod}", actor)
    assert result == "1d20-2"


def test_resolve_negative_modifier_at_start_of_modifier_chain() -> None:
    """Negative modifier on its own (no preceding operator) produces -N."""
    actor = _actor(charisma=6)
    result = resolve_dice_expression("1d20+{proficiency_bonus}+{charisma_mod}", actor)
    assert result == "1d20+3-2"


def test_resolve_no_tokens_unchanged() -> None:
    """Expressions with no tokens pass through unchanged."""
    actor = _actor()
    result = resolve_dice_expression("2d6+3", actor)
    assert result == "2d6+3"


def test_resolve_unknown_token_unchanged() -> None:
    """Unknown tokens are left in the expression (validation handles them)."""
    actor = _actor()
    result = resolve_dice_expression("1d20+{unknown_token}", actor)
    assert result == "1d20+{unknown_token}"


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
