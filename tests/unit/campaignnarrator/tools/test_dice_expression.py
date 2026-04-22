"""Unit tests for dice_expression resolution."""

from __future__ import annotations

from campaignnarrator.domain.models import (
    ActorState,
    ActorType,
    RollRequest,
    RollVisibility,
)
from campaignnarrator.tools.dice_expression import (
    actor_modifiers,
    execute_roll,
    format_roll_event,
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


def test_format_roll_event_uses_purpose_when_set() -> None:
    """format_roll_event uses the purpose field as label when it is provided."""
    roll = RollRequest(
        owner="player",
        visibility=RollVisibility.PUBLIC,
        expression="1d20+3",
        purpose="Persuasion check",
    )
    result = format_roll_event(roll, 18)
    assert result == "Roll: Persuasion check = 18."


def test_format_roll_event_falls_back_to_expression_when_no_purpose() -> None:
    """format_roll_event uses the expression as label when purpose is absent."""
    roll = RollRequest(
        owner="player",
        visibility=RollVisibility.PUBLIC,
        expression="1d20+3",
    )
    result = format_roll_event(roll, 7)
    assert result == "Roll: 1d20+3 = 7."


def test_execute_roll_resolves_tokens_and_returns_formatted_event() -> None:
    """execute_roll substitutes actor tokens, calls roll_dice, and returns formatted string."""
    actor = _actor(wisdom=16, proficiency_bonus=3)
    roll = RollRequest(
        owner="player",
        visibility=RollVisibility.PUBLIC,
        expression="1d20+{wisdom_mod}+{proficiency_bonus}",
        purpose="Insight check",
    )
    calls: list[str] = []

    def fake_dice(expression: str) -> int:
        calls.append(expression)
        return 14

    result = execute_roll(roll, actor, fake_dice)

    assert calls == ["1d20+3+3"]
    assert result == "Roll: Insight check = 14."


def test_format_roll_event_uses_resolved_expression_over_original_when_no_purpose() -> None:
    """format_roll_event prefers resolved_expression over raw expression as fallback."""
    roll = RollRequest(
        owner="player",
        visibility=RollVisibility.PUBLIC,
        expression="1d20+{wisdom_mod}",
    )
    result = format_roll_event(roll, 15, resolved_expression="1d20+3")
    assert result == "Roll: 1d20+3 = 15."


def test_format_roll_event_purpose_wins_over_resolved_expression() -> None:
    """purpose field takes priority over resolved_expression."""
    roll = RollRequest(
        owner="player",
        visibility=RollVisibility.PUBLIC,
        expression="1d20+{wisdom_mod}",
        purpose="Insight check",
    )
    result = format_roll_event(roll, 15, resolved_expression="1d20+3")
    assert result == "Roll: Insight check = 15."


def test_execute_roll_uses_resolved_expression_as_label_when_purpose_absent() -> None:
    """execute_roll uses resolved expression (tokens substituted) as label, not template."""
    actor = _actor(wisdom=16, proficiency_bonus=3)
    roll = RollRequest(
        owner="player",
        visibility=RollVisibility.PUBLIC,
        expression="1d20+{wisdom_mod}+{proficiency_bonus}",
    )
    result = execute_roll(roll, actor, lambda _: 14)
    assert result == "Roll: 1d20+3+3 = 14."


def test_execute_roll_uses_expression_as_label_when_no_tokens_and_no_purpose() -> None:
    """execute_roll falls back to the (unchanged) expression when it has no tokens."""
    actor = _actor()
    roll = RollRequest(
        owner="player",
        visibility=RollVisibility.PUBLIC,
        expression="2d6+3",
    )

    result = execute_roll(roll, actor, lambda _: 9)

    assert result == "Roll: 2d6+3 = 9."
