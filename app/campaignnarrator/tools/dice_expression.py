"""Dice expression variable substitution for actor-specific modifiers."""

from __future__ import annotations

import logging
from collections.abc import Callable

from campaignnarrator.domain.models import ActorState, RollRequest

_log = logging.getLogger(__name__)


def _ability_modifier(score: int) -> int:
    """Compute D&D 5e ability modifier from raw score."""
    return (score - 10) // 2


def resolve_dice_expression(expression: str, actor: ActorState) -> str:
    """Replace known {token} placeholders with numeric values from actor.

    Tokens:
        {strength_mod}, {dexterity_mod}, {constitution_mod},
        {intelligence_mod}, {wisdom_mod}, {charisma_mod},
        {proficiency_bonus}, {level}

    Unknown tokens are left in place. Numeric-only expressions pass through
    unchanged. Negative modifiers collapse sign: 1d20+-2 becomes 1d20-2.
    """
    token_map = {
        "{strength_mod}": str(_ability_modifier(actor.strength)),
        "{dexterity_mod}": str(_ability_modifier(actor.dexterity)),
        "{constitution_mod}": str(_ability_modifier(actor.constitution)),
        "{intelligence_mod}": str(_ability_modifier(actor.intelligence)),
        "{wisdom_mod}": str(_ability_modifier(actor.wisdom)),
        "{charisma_mod}": str(_ability_modifier(actor.charisma)),
        "{proficiency_bonus}": str(actor.proficiency_bonus),
        "{level}": str(actor.level),
    }
    result = expression
    for token, value in token_map.items():
        result = result.replace(token, value)
    result = result.replace("+-", "-")
    return result


def format_roll_event(
    roll_request: RollRequest,
    total: int,
    resolved_expression: str | None = None,
) -> str:
    """Format a completed dice roll as a player-facing event string.

    Label priority: purpose (from LLM) → resolved_expression → original expression.
    """
    label = roll_request.purpose or resolved_expression or roll_request.expression
    return f"Roll: {label} = {total}."


def execute_roll(
    roll_request: RollRequest,
    actor: ActorState,
    roll_dice: Callable[[str], int],
) -> str:
    """Resolve token placeholders, roll dice, and return a formatted event string."""
    expression = resolve_dice_expression(roll_request.expression, actor)
    total = roll_dice(expression)
    _log.info(
        "Roll executed: purpose=%r expression=%r resolved=%r total=%d",
        roll_request.purpose,
        roll_request.expression,
        expression,
        total,
    )
    return format_roll_event(roll_request, total, resolved_expression=expression)


def actor_modifiers(actor: ActorState) -> dict[str, int]:
    """Pre-compute the actor modifiers dict for rules adjudication.

    Returns ability modifiers, proficiency bonus, level, and per-class-level
    entries for each entry in actor.class_levels.
    """
    modifiers: dict[str, int] = {
        "strength_mod": _ability_modifier(actor.strength),
        "dexterity_mod": _ability_modifier(actor.dexterity),
        "constitution_mod": _ability_modifier(actor.constitution),
        "intelligence_mod": _ability_modifier(actor.intelligence),
        "wisdom_mod": _ability_modifier(actor.wisdom),
        "charisma_mod": _ability_modifier(actor.charisma),
        "proficiency_bonus": actor.proficiency_bonus,
        "level": actor.level,
    }
    if actor.class_levels:
        for class_name, class_level in actor.class_levels:
            modifiers[f"{class_name.lower()}_level"] = class_level
    return modifiers
