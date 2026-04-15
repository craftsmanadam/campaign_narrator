"""Goblin Scout NPC fixture factory for combat acceptance tests.

Call make_goblin_scout() to produce each instance with a unique actor_id and name.
All goblins share the same stats — only identity differs.
"""

from campaignnarrator.domain.models import ActorState, ActorType, WeaponState

_SCIMITAR = WeaponState(
    name="Scimitar",
    attack_bonus=4,  # proficiency +2 + DEX mod +2 (finesse)
    damage_dice="1d6",
    damage_bonus=2,  # DEX mod
    damage_type="slashing",
    properties=("light", "finesse"),
)

_SHORTBOW = WeaponState(
    name="Shortbow",
    attack_bonus=4,  # proficiency +2 + DEX mod +2
    damage_dice="1d6",
    damage_bonus=2,
    damage_type="piercing",
    properties=("ammunition (range 80/320)", "two-handed"),
)


def make_goblin_scout(actor_id: str, name: str) -> ActorState:
    """Return a Goblin Scout ActorState with the given identity."""
    return ActorState(
        actor_id=actor_id,
        name=name,
        actor_type=ActorType.NPC,
        # Ability scores
        strength=8,
        dexterity=14,
        constitution=10,
        intelligence=10,
        wisdom=8,
        charisma=8,
        # Derived stats
        proficiency_bonus=2,
        initiative_bonus=2,  # DEX mod only
        speed=30,
        armor_class=15,
        ac_breakdown=("Leather: 11 + DEX mod +2 = 13", "Shield: +2", "Total: 15"),
        # Hit points
        hp_max=7,
        hp_current=7,
        # Action economy
        action_options=(
            "Attack",
            "Dodge",
            "Disengage",
            "Dash",
            "Hide",
            "Nimble Escape (Disengage or Hide as bonus action)",
        ),
        attacks_per_action=1,
        bonus_action_options=(
            "Nimble Escape: Disengage as bonus action",
            "Nimble Escape: Hide as bonus action",
        ),
        reaction_options=(),
        # Weapons
        equipped_weapons=(_SCIMITAR, _SHORTBOW),
        # NPC personality
        personality=(
            "Cowardly and opportunistic. "
            "Will flee when outmatched or when leader falls."
        ),
        is_visible=True,
    )
