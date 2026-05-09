"""ActorState and supporting types."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum

from .actor_components import (
    FeatState,
    InventoryItem,
    RecoveryPeriod,
    ResourceState,
    WeaponState,
)

# HP ratio thresholds for actor narrative summaries
_HP_THRESHOLD_BARELY_STANDING = 0.25

# Death saving throw thresholds
_DEATH_SAVE_NAT_ONE = 1
_DEATH_SAVE_NAT_TWENTY = 20
_DEATH_SAVE_MIN_SUCCESS_ROLL = 10
_DEATH_SAVE_SUCCESS_THRESHOLD = 3
_DEATH_SAVE_FAILURE_THRESHOLD = 3
_HP_THRESHOLD_BLOODIED = 0.5
_HP_THRESHOLD_LIGHTLY_WOUNDED = 0.75


class ActorType(StrEnum):
    """Distinguishes player characters, NPCs, and allied NPCs."""

    PC = "pc"
    NPC = "npc"
    ALLY = "ally"


def _int_pair_tuple_from_data(
    data: Mapping[str, object], key: str
) -> tuple[tuple[str, int], ...]:
    """Extract a tuple of (str, int) pairs from a serialized mapping."""
    v = data.get(key, ())
    if not isinstance(v, list | tuple):
        return ()
    result = []
    for item in v:
        if isinstance(item, list | tuple) and len(item) == 2:  # noqa: PLR2004
            k, val = item
            if isinstance(k, str) and type(val) is int:
                result.append((k, val))
    return tuple(result)


def _ability_modifier(score: int) -> int:
    """Compute D&D 5e ability modifier from raw score."""
    return (score - 10) // 2


@dataclass(frozen=True, slots=True)
class ActorState:
    """Full D&D 2024 character-sheet-equivalent actor state for an encounter."""

    # --- Identity ---
    actor_id: str
    name: str
    actor_type: ActorType

    # --- Core combat stats ---
    hp_max: int
    hp_current: int
    armor_class: int

    # --- Ability scores ---
    strength: int
    dexterity: int
    constitution: int
    intelligence: int
    wisdom: int
    charisma: int

    # --- Derived stats ---
    proficiency_bonus: int
    initiative_bonus: int  # DEX mod + feat bonuses (e.g. Alert); pre-computed
    speed: int  # feet per turn
    attacks_per_action: int

    # --- Action economy options ---
    action_options: tuple[str, ...]

    # --- AC breakdown ---
    ac_breakdown: tuple[str, ...]

    # --- Saving throws: tuple of (ability_name, total_bonus) ---
    saving_throws: tuple[tuple[str, int], ...] = field(default_factory=tuple)

    # --- Temporary HP ---
    hp_temp: int = 0

    # --- Resources: structured per-character ability tracking ---
    resources: tuple[ResourceState, ...] = field(default_factory=tuple)

    # --- Inventory: physical items carried ---
    inventory: tuple[InventoryItem, ...] = field(default_factory=tuple)

    # --- Bonus and reaction action economy ---
    bonus_action_options: tuple[str, ...] = field(default_factory=tuple)
    reaction_options: tuple[str, ...] = field(default_factory=tuple)

    # --- Weapons and feats ---
    equipped_weapons: tuple[WeaponState, ...] = field(default_factory=tuple)
    feats: tuple[FeatState, ...] = field(default_factory=tuple)

    # --- Defenses ---
    damage_resistances: tuple[str, ...] = field(default_factory=tuple)
    damage_vulnerabilities: tuple[str, ...] = field(default_factory=tuple)
    damage_immunities: tuple[str, ...] = field(default_factory=tuple)
    condition_immunities: tuple[str, ...] = field(default_factory=tuple)

    # --- Current conditions ---
    conditions: tuple[str, ...] = field(default_factory=tuple)

    # --- Death saves (dynamic during encounter) ---
    death_save_successes: int = 0
    death_save_failures: int = 0

    # --- Spellcasting (empty for non-casters) ---
    spell_slots: tuple[tuple[str, int], ...] = field(default_factory=tuple)
    spell_slots_max: tuple[tuple[str, int], ...] = field(default_factory=tuple)
    available_spells: tuple[str, ...] = field(default_factory=tuple)
    concentration: str | None = None

    # --- NPC personality (None for PCs) ---
    personality: str | None = None

    # --- Visibility ---
    is_visible: bool = True

    # --- Progression ---
    level: int = 1
    class_levels: tuple[tuple[str, int], ...] = field(default_factory=tuple)
    xp: int = 0

    # --- Character creation fields (persisted) ---
    race: str | None = None
    description: str | None = None  # physical appearance
    background: str | None = None  # backstory text

    # --- Compendium references (transient — populated at load time, not persisted) ---
    references: tuple[str, ...] = field(default_factory=tuple)

    # --- Compendium text (transient — populated at load time, not persisted) ---
    compendium_text: str | None = None

    def has_condition(self, name: str) -> bool:
        """Return True if the condition is currently active."""
        return name in self.conditions

    def with_references(self, refs: tuple[str, ...]) -> ActorState:
        """Return a copy with references replaced."""
        return replace(self, references=refs)

    def with_condition(self, name: str) -> ActorState:
        """Return a copy with condition added. No-op if already present."""
        if name in self.conditions:
            return self
        return replace(self, conditions=(*self.conditions, name))

    def without_condition(self, name: str) -> ActorState:
        """Return a copy with condition removed. No-op if not present."""
        if name not in self.conditions:
            return self
        return replace(self, conditions=tuple(c for c in self.conditions if c != name))

    def with_actor_id(self, actor_id: str) -> ActorState:
        """Return a copy with actor_id replaced."""
        return replace(self, actor_id=actor_id)

    def with_name(self, name: str) -> ActorState:
        """Return a copy with name replaced."""
        return replace(self, name=name)

    def with_actor_type(self, actor_type: ActorType) -> ActorState:
        """Return a copy with actor_type replaced."""
        return replace(self, actor_type=actor_type)

    def with_race(self, race: str) -> ActorState:
        """Return a copy with race replaced."""
        return replace(self, race=race)

    def with_background(self, background: str) -> ActorState:
        """Return a copy with background replaced."""
        return replace(self, background=background)

    def with_description(self, description: str | None) -> ActorState:
        """Return a copy with description replaced."""
        return replace(self, description=description)

    def apply_death_save_roll(self, roll_result: int) -> ActorState:
        """Apply a death saving throw result and return the updated actor.

        - Natural 1: +2 failures
        - Natural 20: +2 successes
        - 10-19: +1 success
        - 2-9: +1 failure
        - 3+ successes: actor gains 'stable', loses 'unconscious'
        - 3+ failures: actor gains 'dead', loses 'unconscious'
        """
        successes = self.death_save_successes
        failures = self.death_save_failures

        if roll_result == _DEATH_SAVE_NAT_ONE:
            failures += 2
        elif roll_result == _DEATH_SAVE_NAT_TWENTY:
            successes += 2
        elif roll_result >= _DEATH_SAVE_MIN_SUCCESS_ROLL:
            successes += 1
        else:
            failures += 1

        if successes >= _DEATH_SAVE_SUCCESS_THRESHOLD:
            return replace(
                self,
                death_save_successes=_DEATH_SAVE_SUCCESS_THRESHOLD,
                death_save_failures=failures,
                conditions=(
                    *(c for c in self.conditions if c != "unconscious"),
                    "stable",
                ),
            )
        if failures >= _DEATH_SAVE_FAILURE_THRESHOLD:
            return replace(
                self,
                death_save_successes=successes,
                death_save_failures=_DEATH_SAVE_FAILURE_THRESHOLD,
                conditions=(
                    *(c for c in self.conditions if c != "unconscious"),
                    "dead",
                ),
            )
        return replace(
            self, death_save_successes=successes, death_save_failures=failures
        )

    def apply_change_hp(self, delta: int) -> ActorState:
        """Return a copy with hp_current adjusted by delta, clamped to [0, hp_max]."""
        new_hp = max(0, min(self.hp_max, self.hp_current + delta))
        return replace(self, hp_current=new_hp)

    def apply_inventory_spent(self, item_id: str) -> ActorState:
        """Return a copy with one unit of item_id consumed.

        Raises ValueError if the item is not found in inventory.
        """
        inventory = list(self.inventory)
        for i, item in enumerate(inventory):
            if item.item_id == item_id:
                if item.count > 1:
                    inventory[i] = replace(item, count=item.count - 1)
                else:
                    inventory.pop(i)
                return replace(self, inventory=tuple(inventory))
        msg = f"actor {self.actor_id} does not have item with item_id: {item_id}"
        raise ValueError(msg)

    def get_turn_resources(self) -> TurnResources:
        """Return fresh TurnResources for this actor at the start of their turn."""
        return TurnResources(
            action_available=True,
            bonus_action_available=True,
            reaction_available=True,
            movement_remaining=self.speed,
        )

    def reset_turn_resources(self) -> ActorState:
        """Return a copy with per-turn ResourceState entries reset to max."""
        updated = tuple(
            replace(r, current=r.max) if r.recovers_after == RecoveryPeriod.TURN else r
            for r in self.resources
        )
        return replace(self, resources=updated)

    def narrative_summary(self) -> str:
        """Return a narration-safe actor summary using injury labels instead of numbers.

        The player character is tagged ``(player)`` so the narrator can distinguish
        them from NPCs and never assign the player's name to a background figure.
        """
        ratio = self.hp_current / self.hp_max if self.hp_max > 0 else 0.0
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

        if self.actor_type is ActorType.PC:
            parts = [self.name, f"(player, {injury})"]
        else:
            parts = [self.name, f"({injury})"]

        if self.conditions:
            parts.append(f"[{', '.join(self.conditions)}]")
        if self.description:
            parts.append(f"— {self.description}")
        return " ".join(parts)

    def as_modifiers(self) -> dict[str, int]:
        """Pre-compute the modifiers dict for rules adjudication.

        Returns ability modifiers, proficiency bonus, level, and per-class-level
        entries for each entry in class_levels.
        """
        modifiers: dict[str, int] = {
            "strength_mod": _ability_modifier(self.strength),
            "dexterity_mod": _ability_modifier(self.dexterity),
            "constitution_mod": _ability_modifier(self.constitution),
            "intelligence_mod": _ability_modifier(self.intelligence),
            "wisdom_mod": _ability_modifier(self.wisdom),
            "charisma_mod": _ability_modifier(self.charisma),
            "proficiency_bonus": self.proficiency_bonus,
            "level": self.level,
        }
        if self.class_levels:
            for class_name, class_level in self.class_levels:
                modifiers[f"{class_name.lower()}_level"] = class_level
        return modifiers

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-compatible dict. Excludes transient fields."""
        return {
            "actor_id": self.actor_id,
            "name": self.name,
            "actor_type": self.actor_type.value,
            "hp_max": self.hp_max,
            "hp_current": self.hp_current,
            "hp_temp": self.hp_temp,
            "armor_class": self.armor_class,
            "strength": self.strength,
            "dexterity": self.dexterity,
            "constitution": self.constitution,
            "intelligence": self.intelligence,
            "wisdom": self.wisdom,
            "charisma": self.charisma,
            "proficiency_bonus": self.proficiency_bonus,
            "initiative_bonus": self.initiative_bonus,
            "speed": self.speed,
            "attacks_per_action": self.attacks_per_action,
            "action_options": list(self.action_options),
            "ac_breakdown": list(self.ac_breakdown),
            "saving_throws": [list(pair) for pair in self.saving_throws],
            "resources": [r.to_dict() for r in self.resources],
            "inventory": [i.to_dict() for i in self.inventory],
            "bonus_action_options": list(self.bonus_action_options),
            "reaction_options": list(self.reaction_options),
            "equipped_weapons": [w.to_dict() for w in self.equipped_weapons],
            "feats": [f.to_dict() for f in self.feats],
            "damage_resistances": list(self.damage_resistances),
            "damage_vulnerabilities": list(self.damage_vulnerabilities),
            "damage_immunities": list(self.damage_immunities),
            "condition_immunities": list(self.condition_immunities),
            "conditions": list(self.conditions),
            "death_save_successes": self.death_save_successes,
            "death_save_failures": self.death_save_failures,
            "spell_slots": [list(pair) for pair in self.spell_slots],
            "spell_slots_max": [list(pair) for pair in self.spell_slots_max],
            "available_spells": list(self.available_spells),
            "concentration": self.concentration,
            "personality": self.personality,
            "is_visible": self.is_visible,
            "level": self.level,
            "class_levels": [list(pair) for pair in self.class_levels],
            "xp": self.xp,
            "race": self.race,
            "description": self.description,
            "background": self.background,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ActorState:
        """Restore from to_dict(). Missing optional fields use defaults."""

        def _req_str(key: str) -> str:
            v = data.get(key)
            if not isinstance(v, str):
                raise TypeError(f"ActorState: {key} must be str")  # noqa: TRY003
            return v

        def _req_int(key: str) -> int:
            v = data.get(key)
            if type(v) is not int:
                raise TypeError(f"ActorState: {key} must be int")  # noqa: TRY003
            return v

        def _opt_int(key: str, default: int = 0) -> int:
            v = data.get(key, default)
            return v if type(v) is int else default

        def _opt_str(key: str) -> str | None:
            v = data.get(key)
            return v if isinstance(v, str) else None

        def _str_tuple(key: str) -> tuple[str, ...]:
            v = data.get(key, ())
            if not isinstance(v, list | tuple):
                return ()
            return tuple(i for i in v if isinstance(i, str))

        actor_type_raw = data.get("actor_type")
        if not isinstance(actor_type_raw, str):
            raise TypeError("ActorState: actor_type must be str")  # noqa: TRY003
        is_visible_raw = data.get("is_visible", True)
        return cls(
            actor_id=_req_str("actor_id"),
            name=_req_str("name"),
            actor_type=ActorType(actor_type_raw),
            hp_max=_req_int("hp_max"),
            hp_current=_req_int("hp_current"),
            armor_class=_req_int("armor_class"),
            strength=_req_int("strength"),
            dexterity=_req_int("dexterity"),
            constitution=_req_int("constitution"),
            intelligence=_req_int("intelligence"),
            wisdom=_req_int("wisdom"),
            charisma=_req_int("charisma"),
            proficiency_bonus=_req_int("proficiency_bonus"),
            initiative_bonus=_req_int("initiative_bonus"),
            speed=_req_int("speed"),
            attacks_per_action=_req_int("attacks_per_action"),
            action_options=_str_tuple("action_options"),
            ac_breakdown=_str_tuple("ac_breakdown"),
            hp_temp=_opt_int("hp_temp", 0),
            saving_throws=_int_pair_tuple_from_data(data, "saving_throws"),
            resources=tuple(
                ResourceState.from_dict(r)
                for r in data.get("resources", ())
                if isinstance(r, Mapping)
            ),
            inventory=tuple(
                InventoryItem.from_dict(i)
                for i in data.get("inventory", ())
                if isinstance(i, Mapping)
            ),
            bonus_action_options=_str_tuple("bonus_action_options"),
            reaction_options=_str_tuple("reaction_options"),
            equipped_weapons=tuple(
                WeaponState.from_dict(w)
                for w in data.get("equipped_weapons", ())
                if isinstance(w, Mapping)
            ),
            feats=tuple(
                FeatState.from_dict(f)
                for f in data.get("feats", ())
                if isinstance(f, Mapping)
            ),
            damage_resistances=_str_tuple("damage_resistances"),
            damage_vulnerabilities=_str_tuple("damage_vulnerabilities"),
            damage_immunities=_str_tuple("damage_immunities"),
            condition_immunities=_str_tuple("condition_immunities"),
            conditions=_str_tuple("conditions"),
            death_save_successes=_opt_int("death_save_successes", 0),
            death_save_failures=_opt_int("death_save_failures", 0),
            spell_slots=_int_pair_tuple_from_data(data, "spell_slots"),
            spell_slots_max=_int_pair_tuple_from_data(data, "spell_slots_max"),
            available_spells=_str_tuple("available_spells"),
            concentration=_opt_str("concentration"),
            personality=_opt_str("personality"),
            is_visible=is_visible_raw if isinstance(is_visible_raw, bool) else True,
            level=_opt_int("level", 1),
            class_levels=_int_pair_tuple_from_data(data, "class_levels"),
            xp=_opt_int("xp", 0),
            race=_opt_str("race"),
            description=_opt_str("description"),
            background=_opt_str("background"),
        )


class ResourceUnavailableError(ValueError):
    """Raised when a turn resource cannot be deducted because it is exhausted."""


@dataclass(frozen=True, slots=True)
class TurnResources:
    """Action economy remaining for the actor whose turn is currently active."""

    action_available: bool = True
    bonus_action_available: bool = True
    reaction_available: bool = True
    movement_remaining: int = 0  # feet; initialized from ActorState.speed at turn start

    def deduct(self, resource_type: str, amount: int = 1) -> TurnResources:
        """Return a copy with resource_type reduced by amount.

        Raises ResourceUnavailableError if exhausted.
        Valid resource_type: "action", "bonus_action", "reaction", "movement".
        For "movement", amount is feet.
        """
        if resource_type == "action":
            if not self.action_available:
                msg = "action is already spent this turn"
                raise ResourceUnavailableError(msg)
            return replace(self, action_available=False)
        if resource_type == "bonus_action":
            if not self.bonus_action_available:
                msg = "bonus_action is already spent this turn"
                raise ResourceUnavailableError(msg)
            return replace(self, bonus_action_available=False)
        if resource_type == "reaction":
            if not self.reaction_available:
                msg = "reaction is already spent this turn"
                raise ResourceUnavailableError(msg)
            return replace(self, reaction_available=False)
        if resource_type == "movement":
            if amount > self.movement_remaining:
                msg = (
                    f"movement: requested {amount}ft but only "
                    f"{self.movement_remaining}ft remaining"
                )
                raise ResourceUnavailableError(msg)
            return replace(self, movement_remaining=self.movement_remaining - amount)
        msg = f"unknown resource_type: {resource_type!r}"
        raise ValueError(msg)
