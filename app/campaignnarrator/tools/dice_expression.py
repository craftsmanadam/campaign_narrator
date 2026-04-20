"""Dice expression variable substitution for actor-specific modifiers."""

from __future__ import annotations

from campaignnarrator.domain.models import ActorState


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
