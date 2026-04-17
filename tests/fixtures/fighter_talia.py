"""Talia Ironveil — Level 5 Human Fighter fixture for combat acceptance tests."""

from campaignnarrator.domain.models import (
    ActorState,
    ActorType,
    FeatState,
    InventoryItem,
    RecoveryPeriod,
    ResourceState,
    WeaponState,
)

# Note: Fighter saving throw proficiencies are STR and CON only.
# STR: +4 mod + 3 prof = +7; CON: +3 mod + 3 prof = +6.
# Other saves use ability modifier only.
_SAVING_THROWS: tuple[tuple[str, int], ...] = (
    ("strength", 7),
    ("dexterity", 2),
    ("constitution", 6),
    ("intelligence", 0),
    ("wisdom", 1),
    ("charisma", -1),
)

_ALERT = FeatState(
    name="Alert",
    effect_summary=(
        "You add your Proficiency Bonus to your Initiative. You can't be surprised "
        "while you are conscious. Other creatures don't gain advantage on attack rolls "
        "against you as a result of being unseen by you. This proficiency bonus is "
        "already reflected in this actor's initiative_bonus — do not add it again "
        "when rolling initiative."
    ),
    reference="DND.SRD.Wiki-0.5.2/Feats.md#Alert",
    per_turn_uses=None,
)

_SAVAGE_ATTACKER = FeatState(
    name="Savage Attacker",
    effect_summary=(
        "Once per turn when you roll damage for a melee weapon attack, you can reroll "
        "the weapon's damage dice and use either roll. The 'savage_attacker' resource "
        "tracks remaining uses this turn."
    ),
    reference="DND.SRD.Wiki-0.5.2/Feats.md#Savage Attacker",
    per_turn_uses=1,
)

_LONGSWORD_ONE_HAND = WeaponState(
    name="Longsword (one-hand)",
    attack_bonus=7,  # proficiency +3 + STR mod +4
    damage_dice="1d8",
    damage_bonus=4,  # STR mod
    damage_type="slashing",
    properties=("versatile (1d10)",),
)

_LONGSWORD_TWO_HAND = WeaponState(
    name="Longsword (two-hand via versatile)",
    attack_bonus=7,
    damage_dice="1d10",
    damage_bonus=4,
    damage_type="slashing",
    properties=("versatile",),
)

TALIA = ActorState(
    actor_id="pc:talia",
    name="Talia Ironveil",
    actor_type=ActorType.PC,
    # Ability scores
    strength=18,
    dexterity=14,
    constitution=16,
    intelligence=10,
    wisdom=12,
    charisma=8,
    # Derived stats
    proficiency_bonus=3,
    initiative_bonus=5,  # DEX +2 + Alert proficiency +3
    speed=30,
    armor_class=20,
    ac_breakdown=("Plate: 18", "Shield: +2"),
    # Hit points
    hp_max=44,
    hp_current=44,
    hp_temp=0,
    # Saving throws
    saving_throws=_SAVING_THROWS,
    # Resources
    resources=(
        ResourceState(
            resource="second_wind",
            current=1,
            max=1,
            recovers_after=RecoveryPeriod.SHORT_REST,
            reference="character_options/class_features.json#second-wind",
        ),
        ResourceState(
            resource="action_surge",
            current=1,
            max=1,
            recovers_after=RecoveryPeriod.SHORT_REST,
            reference="character_options/class_features.json#action-surge",
        ),
        ResourceState(
            resource="savage_attacker",
            current=1,
            max=1,
            recovers_after=RecoveryPeriod.TURN,
            reference="character_options/feats.json#savage-attacker",
        ),
    ),
    # Inventory
    inventory=(
        InventoryItem(
            item_id="potion-1",
            item="Potion of Healing",
            count=2,
            reference="equipment/potions.json#potion-of-healing",
        ),
    ),
    # Action economy
    action_options=(
        "Attack",
        "Dodge",
        "Disengage",
        "Dash",
        "Help",
        "Grapple",
        "Shove",
        "Action Surge (expend to take an additional action)",
    ),
    attacks_per_action=2,
    bonus_action_options=("Second Wind (regain 1d10+5 HP, uses Second Wind resource)",),
    reaction_options=("Opportunity Attack (when enemy leaves melee reach)",),
    # Weapons
    equipped_weapons=(_LONGSWORD_ONE_HAND, _LONGSWORD_TWO_HAND),
    # Feats
    feats=(_ALERT, _SAVAGE_ATTACKER),
)
