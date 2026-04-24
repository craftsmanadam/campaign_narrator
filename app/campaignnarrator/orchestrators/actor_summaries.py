"""Shared actor narrative summary helpers used by encounter and combat orchestrators."""

from __future__ import annotations

from campaignnarrator.domain.models import ActorState, ActorType

# HP ratio thresholds for actor narrative summaries
_HP_THRESHOLD_BARELY_STANDING = 0.25
_HP_THRESHOLD_BLOODIED = 0.5
_HP_THRESHOLD_LIGHTLY_WOUNDED = 0.75


def _ability_modifier(score: int) -> int:
    """Compute D&D 5e ability modifier from raw score."""
    return (score - 10) // 2


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


def actor_narrative_summary(actor: ActorState) -> str:
    """Return a narration-safe actor summary using injury labels instead of numbers.

    The player character is tagged ``(player)`` so the narrator can distinguish
    them from NPCs and never assign the player's name to a background figure.
    """
    ratio = actor.hp_current / actor.hp_max if actor.hp_max > 0 else 0.0
    if ratio <= 0:
        injury = "defeated"
    elif ratio <= _HP_THRESHOLD_BARELY_STANDING:
        injury = "barely standing"
    elif ratio <= _HP_THRESHOLD_BLOODIED:
        injury = "bloodied"
    elif ratio <= _HP_THRESHOLD_LIGHTLY_WOUNDED:
        injury = "lightly wounded"
    else:
        injury = "uninjured"

    if actor.actor_type is ActorType.PC:
        role_tag = "player"
        parts = [actor.name, f"({role_tag}, {injury})"]
    else:
        parts = [actor.name, f"({injury})"]

    if actor.conditions:
        parts.append(f"[{', '.join(actor.conditions)}]")
    if actor.description:
        parts.append(f"— {actor.description}")
    return " ".join(parts)
