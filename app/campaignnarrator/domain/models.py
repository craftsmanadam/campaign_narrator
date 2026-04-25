"""Domain models for encounter orchestration and narration."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from types import MappingProxyType
from typing import Literal, Protocol, Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from campaignnarrator.tools.dice import roll as _roll


class EncounterPhase(StrEnum):
    """High-level phases for encounter progression."""

    SCENE_OPENING = "scene_opening"
    SOCIAL = "social"
    RULES_RESOLUTION = "rules_resolution"
    COMBAT = "combat"
    ENCOUNTER_COMPLETE = "encounter_complete"


class RollVisibility(StrEnum):
    """Controls who can see a roll request."""

    PUBLIC = "public"
    HIDDEN = "hidden"


class ActorType(StrEnum):
    """Distinguishes player characters, NPCs, and allied NPCs."""

    PC = "pc"
    NPC = "npc"
    ALLY = "ally"


class RecoveryPeriod(StrEnum):
    """When a resource or item charge replenishes."""

    TURN = "turn"  # resets at start of actor's turn
    SHORT_REST = "short_rest"
    LONG_REST = "long_rest"
    DAY = "day"  # items only — "regains charges at dawn"


@dataclass(frozen=True, slots=True)
class Milestone:
    """A campaign story anchor point. Narrator-only — never shown to the player."""

    milestone_id: str
    title: str
    description: str
    completed: bool = False


@dataclass(frozen=True, slots=True)
class CampaignState:
    """Top-level campaign definition.

    Narrator-only fields must never appear in player-facing prompts.
    """

    campaign_id: str
    name: str
    setting: str
    narrator_personality: str
    # --- Narrator-only fields (never send to player-facing prompts) ---
    hidden_goal: str
    bbeg_name: str
    bbeg_description: str
    milestones: tuple[Milestone, ...]
    # --- Progress tracking ---
    current_milestone_index: int
    starting_level: int
    target_level: int
    # --- Player inputs ---
    player_brief: str
    player_actor_id: str
    bbeg_actor_id: str | None = None
    current_module_id: str | None = None


@dataclass(frozen=True, slots=True)
class ModuleState:
    """One story arc within a campaign. Generated lazily as play progresses."""

    module_id: str
    campaign_id: str
    title: str
    summary: str
    guiding_milestone_id: str
    completed_encounter_ids: tuple[str, ...] = ()
    completed_encounter_summaries: tuple[str, ...] = ()
    completed: bool = False
    planned_encounters: tuple[EncounterTemplate, ...] = ()
    next_encounter_index: int = 0


@dataclass(frozen=True, slots=True)
class CampaignEvent:
    """A summarised story event appended to the campaign event log."""

    campaign_id: str
    # encounter_completed | milestone_reached | notable_moment
    # player_downed | npc_death | module_completed
    event_type: str
    summary: str  # narrator-written, 1-3 sentences
    timestamp: str  # ISO 8601
    module_id: str | None = None
    encounter_id: str | None = None


@dataclass(frozen=True, slots=True)
class FeatState:
    """A feat carried by an actor, with LLM-readable effect text."""

    name: str
    effect_summary: str  # Injected verbatim into Rules Agent context
    reference: str | None  # e.g. "DND.SRD.Wiki-0.5.2/Feats.md#Alert"
    per_turn_uses: int | None  # None = passive; int = resource reset each turn

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "effect_summary": self.effect_summary,
            "reference": self.reference,
            "per_turn_uses": self.per_turn_uses,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> FeatState:
        name = data.get("name", "")
        effect_summary = data.get("effect_summary", "")
        reference = data.get("reference")
        per_turn_uses_raw = data.get("per_turn_uses")
        return cls(
            name=str(name),
            effect_summary=str(effect_summary),
            reference=reference if isinstance(reference, str) else None,
            per_turn_uses=(
                int(per_turn_uses_raw) if per_turn_uses_raw is not None else None
            ),
        )


@dataclass(frozen=True, slots=True)
class WeaponState:
    """A weapon with fully pre-computed attack and damage values."""

    name: str
    attack_bonus: int  # proficiency + ability mod (+ magic if any)
    damage_dice: str  # e.g. "1d8", "2d6"
    damage_bonus: int  # ability mod (+ magic if any)
    damage_type: str  # "slashing", "piercing", "bludgeoning", etc.
    properties: tuple[str, ...]  # e.g. ("versatile (1d10)", "finesse")

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "attack_bonus": self.attack_bonus,
            "damage_dice": self.damage_dice,
            "damage_bonus": self.damage_bonus,
            "damage_type": self.damage_type,
            "properties": list(self.properties),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> WeaponState:
        return cls(
            name=str(data.get("name", "")),
            attack_bonus=int(data.get("attack_bonus", 0)),
            damage_dice=str(data.get("damage_dice", "1d4")),
            damage_bonus=int(data.get("damage_bonus", 0)),
            damage_type=str(data.get("damage_type", "bludgeoning")),
            properties=tuple(
                str(p) for p in data.get("properties", ()) if isinstance(p, str)
            ),
        )


@dataclass(frozen=True, slots=True)
class InitiativeTurn:
    """One slot in the initiative order: who acts and what they rolled."""

    actor_id: str
    initiative_roll: int

    def to_dict(self) -> dict[str, object]:
        return {"actor_id": self.actor_id, "initiative_roll": self.initiative_roll}

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> InitiativeTurn:
        actor_id = data.get("actor_id")
        roll = data.get("initiative_roll")
        if not isinstance(actor_id, str):
            raise TypeError("InitiativeTurn: actor_id must be str")  # noqa: TRY003
        if type(roll) is not int:
            raise TypeError("InitiativeTurn: initiative_roll must be int")  # noqa: TRY003
        return cls(actor_id=actor_id, initiative_roll=roll)


class NpcPresenceStatus(StrEnum):
    """Scene presence state for an established NPC.

    PRESENT  - NPC is active in the scene and visible to the player.
    CONCEALED - NPC is in the scene but hidden from the player (e.g. behind a
                screen, in disguise).  The narrator may still reference them
                obliquely; the player has not interacted with them directly.
    DEPARTED - NPC has left the scene.  They must not appear in narrator
               context; the orchestrator filters them out entirely.
    """

    PRESENT = "present"
    CONCEALED = "concealed"
    DEPARTED = "departed"


@dataclass(frozen=True, slots=True)
class NpcPresence:
    """Identity anchor for an NPC established in the encounter scene.

    Prevents the narrator from inventing new named characters mid-scene.
    When name_known=False the narrator uses description; when True it uses
    display_name.
    """

    actor_id: str  # FK to EncounterState.actors
    display_name: str  # Canonical name used when name_known=True
    description: str  # Narrative label used when name_known=False ("the innkeeper")
    name_known: bool  # Has the player learned this NPC's name?
    status: NpcPresenceStatus = NpcPresenceStatus.PRESENT

    def to_dict(self) -> dict[str, object]:
        return {
            "actor_id": self.actor_id,
            "display_name": self.display_name,
            "description": self.description,
            "name_known": self.name_known,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> NpcPresence:
        actor_id = data.get("actor_id")
        display_name = data.get("display_name")
        description = data.get("description")
        name_known = data.get("name_known")
        if not (
            isinstance(actor_id, str)
            and isinstance(display_name, str)
            and isinstance(description, str)
            and isinstance(name_known, bool)
        ):
            raise TypeError("NpcPresence: missing or invalid required fields")  # noqa: TRY003
        # Backward compatibility: old saves use visible: bool.
        # visible=True → PRESENT; visible=False → CONCEALED.
        # DEPARTED had no representation in old saves and cannot appear here.
        raw_status = data.get("status")
        if isinstance(raw_status, str):
            try:
                status = NpcPresenceStatus(raw_status)
            except ValueError as exc:
                msg = f"NpcPresence: invalid status value {raw_status!r}"
                raise TypeError(msg) from exc
        elif "visible" in data:
            status = (
                NpcPresenceStatus.PRESENT
                if data["visible"]
                else NpcPresenceStatus.CONCEALED
            )
        else:
            status = NpcPresenceStatus.PRESENT
        return cls(
            actor_id=actor_id,
            display_name=display_name,
            description=description,
            name_known=name_known,
            status=status,
        )


class EncounterNpc(BaseModel):
    """Planning-time NPC definition.

    Single source of truth for ActorState and NpcPresence.
    Assigned by EncounterPlannerAgent at planning time.
    template_npc_id must be unique within a module (not just within an encounter).
    """

    model_config = ConfigDict(frozen=True)

    template_npc_id: str
    display_name: str
    role: str
    description: str
    monster_name: str | None
    stat_source: Literal["monster_compendium", "simple_npc"]
    cr: float
    name_known: bool = False

    @field_validator("cr", mode="before")
    @classmethod
    def _parse_cr(cls, v: object) -> float:
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            if "/" in v:
                num, den = v.split("/")
                return int(num) / int(den)
            return float(v)
        raise ValueError(f"Cannot parse CR: {v!r}")  # noqa: TRY003


class EncounterTemplate(BaseModel):
    """Narrative skeleton for one planned encounter."""

    model_config = ConfigDict(frozen=True)

    template_id: str
    order: int
    setting: str
    purpose: str
    scene_tone: str | None = None
    npcs: tuple[EncounterNpc, ...]
    prerequisites: tuple[str, ...]
    expected_outcomes: tuple[str, ...]
    downstream_dependencies: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResourceState:
    """A character class resource with current/max tracking and recovery metadata."""

    resource: str  # e.g. "second_wind", "action_surge"
    current: int
    max: int
    recovers_after: RecoveryPeriod
    reference: str | None = None  # e.g. "class_features.json#second-wind"

    def to_dict(self) -> dict[str, object]:
        return {
            "resource": self.resource,
            "current": self.current,
            "max": self.max,
            "recovers_after": self.recovers_after.value,
            "reference": self.reference,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ResourceState:
        recovers_raw = data.get("recovers_after", "long_rest")
        return cls(
            resource=str(data.get("resource", "")),
            current=int(data.get("current", 0)),
            max=int(data.get("max", 0)),
            recovers_after=RecoveryPeriod(recovers_raw),
            reference=(
                data.get("reference")
                if isinstance(data.get("reference"), str)
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class InventoryItem:
    """A physical item carried by an actor."""

    item_id: str  # unique within actor inventory, e.g. "potion-1", "rope-1"
    item: str  # display name
    count: int
    charges: int | None = None  # current charges (e.g. wand)
    max_charges: int | None = None
    recovers_after: RecoveryPeriod | None = None  # None for consumables/mundane items
    reference: str | None = None  # None for narrative-only items

    def to_dict(self) -> dict[str, object]:
        return {
            "item_id": self.item_id,
            "item": self.item,
            "count": self.count,
            "charges": self.charges,
            "max_charges": self.max_charges,
            "recovers_after": (
                self.recovers_after.value if self.recovers_after is not None else None
            ),
            "reference": self.reference,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> InventoryItem:
        recovers_raw = data.get("recovers_after")
        charges_raw = data.get("charges")
        max_charges_raw = data.get("max_charges")
        return cls(
            item_id=str(data.get("item_id", "")),
            item=str(data.get("item", "")),
            count=int(data.get("count", 0)),
            charges=int(charges_raw) if charges_raw is not None else None,
            max_charges=int(max_charges_raw) if max_charges_raw is not None else None,
            recovers_after=(
                RecoveryPeriod(recovers_raw) if isinstance(recovers_raw, str) else None
            ),
            reference=(
                data.get("reference")
                if isinstance(data.get("reference"), str)
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class PlayerInput:
    """Raw player input with normalized access for routing."""

    raw_text: str

    @property
    def normalized(self) -> str:
        """Return lowercased text with collapsed internal whitespace."""

        return " ".join(self.raw_text.lower().split())


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


# HP ratio thresholds for actor narrative summaries
_HP_THRESHOLD_BARELY_STANDING = 0.25
_HP_THRESHOLD_BLOODIED = 0.5
_HP_THRESHOLD_LIGHTLY_WOUNDED = 0.75


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


@dataclass(frozen=True, slots=True)
class EncounterState:
    """Canonical state for an in-progress encounter."""

    encounter_id: str
    phase: EncounterPhase
    setting: str
    actors: Mapping[str, ActorState]
    public_events: tuple[str, ...] = field(default_factory=tuple)
    hidden_facts: Mapping[str, object] = field(default_factory=dict)
    combat_turns: tuple[InitiativeTurn, ...] = field(default_factory=tuple)
    outcome: str | None = None
    scene_tone: str | None = None
    npc_presences: tuple[NpcPresence, ...] = field(default_factory=tuple)
    current_location: str | None = None

    def __post_init__(self) -> None:
        """Snapshot mutable mappings so encounter state cannot be mutated externally."""

        object.__setattr__(self, "actors", MappingProxyType(dict(self.actors)))
        object.__setattr__(
            self, "hidden_facts", MappingProxyType(dict(self.hidden_facts))
        )
        if self.current_location is None:
            object.__setattr__(self, "current_location", self.setting)

    @property
    def player_actor_id(self) -> str:
        """Return the first player character actor in insertion order."""

        for actor in self.actors.values():
            if actor.actor_type == ActorType.PC:
                return actor.actor_id
        raise ValueError("missing player actor")  # noqa: TRY003

    def visible_actor_names(self) -> tuple[str, ...]:
        """Return visible actor names in encounter insertion order."""

        return tuple(actor.name for actor in self.actors.values() if actor.is_visible)

    def public_actor_summaries(self) -> tuple[str, ...]:
        """Return narration-safe summaries for actors visible in the current scene.

        When npc_presences is empty (old encounters or bare test fixtures) all actors
        are included.  When populated, only PCs and non-DEPARTED NPCs appear so the
        narrator never sees actors who have left the scene.
        """
        if not self.npc_presences:
            return tuple(actor.narrative_summary() for actor in self.actors.values())
        present_ids = {
            p.actor_id
            for p in self.npc_presences
            if p.status is not NpcPresenceStatus.DEPARTED
        }
        return tuple(
            actor.narrative_summary()
            for actor in self.actors.values()
            if actor.actor_type == ActorType.PC or actor.actor_id in present_ids
        )

    def with_phase(self, phase: EncounterPhase) -> EncounterState:
        """Return a copy of the state with an updated phase."""

        return replace(self, phase=phase)

    def to_dict(self) -> dict[str, object]:
        return {
            "encounter_id": self.encounter_id,
            "phase": self.phase.value,
            "setting": self.setting,
            "current_location": self.current_location,
            "public_events": list(self.public_events),
            "hidden_facts": dict(self.hidden_facts),
            "combat_turns": [t.to_dict() for t in self.combat_turns],
            "outcome": self.outcome,
            "scene_tone": self.scene_tone,
            "npc_presences": [p.to_dict() for p in self.npc_presences],
            "actors": {
                actor_id: actor.to_dict() for actor_id, actor in self.actors.items()
            },
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> EncounterState:
        encounter_id = data.get("encounter_id")
        if not isinstance(encounter_id, str):
            raise TypeError("EncounterState: encounter_id must be str")  # noqa: TRY003
        phase_raw = data.get("phase")
        if not isinstance(phase_raw, str):
            raise TypeError("EncounterState: phase must be str")  # noqa: TRY003
        setting = data.get("setting")
        if not isinstance(setting, str):
            raise TypeError("EncounterState: setting must be str")  # noqa: TRY003
        actors_raw = data.get("actors", {})
        if not isinstance(actors_raw, Mapping):
            raise TypeError("EncounterState: actors must be a mapping")  # noqa: TRY003
        actors = {
            str(k): ActorState.from_dict(v)
            for k, v in actors_raw.items()
            if isinstance(v, Mapping)
        }
        public_events_raw = data.get("public_events", ())
        public_events: tuple[str, ...] = (
            tuple(str(e) for e in public_events_raw if isinstance(e, str))
            if isinstance(public_events_raw, list | tuple)
            else ()
        )
        hidden_facts_raw = data.get("hidden_facts", {})
        hidden_facts = (
            dict(hidden_facts_raw) if isinstance(hidden_facts_raw, Mapping) else {}
        )
        combat_turns_raw = data.get("combat_turns", ())
        combat_turns: tuple[InitiativeTurn, ...] = (
            tuple(
                InitiativeTurn.from_dict(t)
                for t in combat_turns_raw
                if isinstance(t, Mapping)
            )
            if isinstance(combat_turns_raw, list | tuple)
            else ()
        )
        npc_presences_raw = data.get("npc_presences", ())
        npc_presences: tuple[NpcPresence, ...] = (
            tuple(
                NpcPresence.from_dict(p)
                for p in npc_presences_raw
                if isinstance(p, Mapping)
            )
            if isinstance(npc_presences_raw, list | tuple)
            else ()
        )
        outcome = data.get("outcome")
        scene_tone = data.get("scene_tone")
        current_location = data.get("current_location")
        return cls(
            encounter_id=encounter_id,
            phase=EncounterPhase(phase_raw),
            setting=setting,
            actors=actors,
            public_events=public_events,
            hidden_facts=hidden_facts,
            combat_turns=combat_turns,
            outcome=outcome if isinstance(outcome, str) else None,
            scene_tone=scene_tone if isinstance(scene_tone, str) else None,
            npc_presences=npc_presences,
            current_location=(
                current_location if isinstance(current_location, str) else None
            ),
        )


@dataclass(frozen=True, slots=True)
class GameState:
    """Top-level game state: player + optional campaign/module/encounter."""

    player: ActorState
    campaign: CampaignState | None = None
    module: ModuleState | None = None
    encounter: EncounterState | None = None


class PlayerIO(Protocol):
    """Protocol for all player-facing I/O.

    Lives in models.py so both EncounterOrchestrator and CombatOrchestrator
    can depend on it without circular imports. The terminal implementation is
    created in cli.py and injected downward. Tests inject ScriptedIO.
    """

    def prompt(self, text: str) -> str:
        """Display text and return player input; re-prompts silently on blank."""
        ...

    def prompt_optional(self, text: str) -> str:
        """Display text and return player input; returns blank if the player skips."""
        ...

    def prompt_multiline(self, text: str) -> str:
        """Display text and collect lines until a blank line; returns joined text."""
        ...

    def display(self, text: str) -> None:
        """Display text with no expected input."""
        ...


class CombatStatus(StrEnum):
    """Terminal outcome of a combat encounter from CombatOrchestrator's perspective."""

    COMPLETE = "complete"
    PLAYER_DOWN_NO_ALLIES = "player_down_no_allies"
    SAVED_AND_QUIT = "saved_and_quit"


@dataclass(frozen=True, slots=True)
class TurnResources:
    """Action economy remaining for the actor whose turn is currently active."""

    action_available: bool = True
    bonus_action_available: bool = True
    reaction_available: bool = True
    movement_remaining: int = 0  # feet; initialized from ActorState.speed at turn start


@dataclass(frozen=True, slots=True)
class CombatResult:
    """Returned by CombatOrchestrator to EncounterOrchestrator when combat ends."""

    status: CombatStatus
    final_state: EncounterState
    death_saves_remaining: int | None  # None unless status is PLAYER_DOWN_NO_ALLIES


class CombatOutcome(BaseModel):
    """Compact and rich description of how a combat encounter ended."""

    model_config = ConfigDict(frozen=True)
    short_description: str  # compact, for future encounter logs
    full_description: str  # rich prose shown to player


class CombatAssessment(BaseModel):
    """Narrator's assessment of whether combat should continue."""

    model_config = ConfigDict(frozen=True)
    combat_active: bool
    outcome: CombatOutcome | None  # None when combat_active is True


class RollRequest(BaseModel):
    """An explicit request for a dice roll."""

    model_config = ConfigDict(frozen=True)

    owner: str
    visibility: RollVisibility
    expression: str
    purpose: str | None = None
    difficulty_class: int | None = None

    @field_validator("expression")
    @classmethod
    def valid_dice(cls, v: str) -> str:
        # Normalize whitespace around operators (Ollama sometimes adds spaces).
        normalized = re.sub(r"\s*([+-])\s*", r"\1", v.strip())
        # Auto-brace bare known token names (Ollama sometimes omits braces).
        for token in (
            "strength_mod",
            "dexterity_mod",
            "constitution_mod",
            "intelligence_mod",
            "wisdom_mod",
            "charisma_mod",
            "proficiency_bonus",
            "level",
        ):
            normalized = re.sub(
                rf"(?<!\{{){re.escape(token)}(?!\}})", f"{{{token}}}", normalized
            )
        if not re.fullmatch(r"\d+d\d+(k[lh]?\d+)?([+-](\d+|\{[a-z_]+\}))*", normalized):
            raise ValueError(f"invalid dice expression: {v!r}")  # noqa: TRY003
        return normalized

    def _resolve_dice_expression(self, actor: ActorState) -> str:
        """Replace {token} placeholders with actor-specific numeric values."""
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
        result = self.expression
        for token, value in token_map.items():
            result = result.replace(token, value)
        return result.replace("+-", "-")

    def roll(self, actor: ActorState) -> RollResult:
        """Resolve expression tokens, roll the dice, and return a RollResult."""
        resolved = self._resolve_dice_expression(actor)
        total = _roll(resolved)
        return RollResult(
            owner=self.owner,
            visibility=self.visibility,
            resolved_expression=resolved,
            purpose=self.purpose,
            difficulty_class=self.difficulty_class,
            roll_total=total,
        )

    def __str__(self) -> str:
        purpose_part = f", purpose={self.purpose!r}" if self.purpose else ""
        dc_part = (
            f", dc={self.difficulty_class}" if self.difficulty_class is not None else ""
        )
        return (
            f"RollRequest(owner={self.owner!r}, expression={self.expression!r}"
            f"{purpose_part}{dc_part})"
        )


class RollResult(BaseModel):
    """The outcome of executing a RollRequest against an ActorState."""

    model_config = ConfigDict(frozen=True)

    owner: str
    visibility: RollVisibility
    resolved_expression: str
    purpose: str | None
    difficulty_class: int | None
    roll_total: int

    def evaluate(self) -> bool:
        """Return True if the roll meets or exceeds the difficulty class.

        Raises ValueError when difficulty_class is not set.
        """
        if self.difficulty_class is None:
            raise ValueError("evaluate() requires difficulty_class to be set")  # noqa: TRY003
        return self.roll_total >= self.difficulty_class

    def __str__(self) -> str:
        label = self.purpose or self.resolved_expression
        base = f"Roll: {label} = {self.roll_total}"
        if self.difficulty_class is not None:
            outcome = (
                "Succeeded" if self.roll_total >= self.difficulty_class else "Failed"
            )
            return f"{base} — {outcome} (DC {self.difficulty_class})"
        return base


class StateEffect(BaseModel):
    """A structured state mutation produced by rules adjudication."""

    model_config = ConfigDict(frozen=True)

    effect_type: str
    target: str
    value: object = None
    apply_on: Literal["always", "success", "failure"] = "always"


@dataclass(frozen=True, slots=True)
class RulesAdjudicationRequest:
    """Structured request for adjudicating a generic encounter action."""

    actor_id: str
    intent: str
    phase: EncounterPhase
    allowed_outcomes: tuple[str, ...]
    encounter_id: str = ""
    check_hints: tuple[str, ...] = field(default_factory=tuple)
    compendium_context: tuple[str, ...] = field(default_factory=tuple)
    actor_modifiers: Mapping[str, int] = field(default_factory=dict)
    visible_actors_context: tuple[str, ...] = field(default_factory=tuple)


class RulesAdjudication(BaseModel):
    """Structured result from rules resolution."""

    model_config = ConfigDict(frozen=True)

    is_legal: bool
    action_type: str
    summary: str
    reasoning_summary: str = ""
    roll_requests: tuple[RollRequest, ...] = ()
    state_effects: tuple[StateEffect, ...] = ()
    rule_references: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class NarrationFrame:
    """Public context that can be narrated to the player."""

    purpose: str
    phase: EncounterPhase
    setting: str
    public_actor_summaries: tuple[str, ...]
    recent_public_events: tuple[str, ...]
    resolved_outcomes: tuple[str, ...]
    allowed_disclosures: tuple[str, ...]
    tone_guidance: str | None = None
    player_action: str | None = None
    prior_narrative_context: str = ""
    compendium_context: tuple[str, ...] = field(default_factory=tuple)
    npc_presences: tuple[NpcPresence, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class Narration:
    """The text that should be spoken to the user."""

    text: str
    audience: str | None = None
    scene_tone: str | None = None
    current_location: str | None = None
    encounter_complete: bool = False
    completion_reason: str | None = None
    next_location_hint: str | None = None


@dataclass(frozen=True, slots=True)
class RuleReference:
    """Reference to a rule source or excerpt."""

    path: str
    title: str | None = None
    excerpt: str | None = None


@dataclass(frozen=True, slots=True)
class Action:
    """A narrated action taken by an actor."""

    actor: str
    summary: str
    rule_references: tuple[RuleReference, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class Adjudication:
    """A decision produced from an action and its supporting rules."""

    action: Action
    outcome: str
    roll_request: RollRequest | None = None
    rule_references: tuple[RuleReference, ...] = field(default_factory=tuple)


class DivergenceAssessment(BaseModel):
    """Output of EncounterPlannerAgent._assess_agent."""

    model_config = ConfigDict(frozen=True)

    status: Literal[
        "viable",
        "needs_bridge",
        "needs_rebuild",
        "needs_full_replan",
        "milestone_achieved",
    ]
    reason: str
    milestone_achieved: bool


class EncounterPlanList(BaseModel):
    """Output of EncounterPlannerAgent._plan_agent."""

    model_config = ConfigDict(frozen=True)

    encounters: tuple[EncounterTemplate, ...]


class EncounterRecoveryResult(BaseModel):
    """Output of EncounterPlannerAgent._recovery_agent."""

    model_config = ConfigDict(frozen=True)

    updated_templates: tuple[EncounterTemplate, ...]
    recovery_type: Literal["bridge_inserted", "template_replaced", "full_replan"]


@dataclass(frozen=True)
class EncounterReady:
    """Returned by EncounterPlannerOrchestrator.prepare() on success.

    module may differ from the input module if recovery occurred.
    Callers must use EncounterReady.module, not their local reference.
    """

    encounter_state: EncounterState
    module: ModuleState


@dataclass(frozen=True)
class MilestoneAchieved:
    """Returned by EncounterPlannerOrchestrator.prepare() when milestone is complete.

    Signals ModuleOrchestrator to advance to the next module.
    """


class NarrationResponse(BaseModel):
    """Structured LLM output for all non-scene-opening narrations."""

    model_config = ConfigDict(frozen=True)

    text: str
    current_location: str
    encounter_complete: bool = False
    completion_reason: str | None = None
    next_location_hint: str | None = None

    @model_validator(mode="after")
    def _validate_completion_fields(self) -> Self:
        if self.encounter_complete and not self.next_location_hint:
            raise ValueError("next_location_hint required when encounter_complete=True")
        if self.encounter_complete and not self.completion_reason:
            raise ValueError("completion_reason required when encounter_complete=True")
        return self


class SceneOpeningResponse(BaseModel):
    """Structured LLM output for scene opening narration."""

    model_config = ConfigDict(frozen=True)

    text: str
    scene_tone: str


class CombatIntent(BaseModel):
    """Structured LLM output for a player's declared combat intent."""

    model_config = ConfigDict(frozen=True)

    intent: Literal["end_turn", "query_status", "exit_session", "combat_action"]


class IntentCategory(StrEnum):
    """Player intent categories used by PlayerIntentAgent."""

    HOSTILE_ACTION = "hostile_action"
    SKILL_CHECK = "skill_check"
    NPC_DIALOGUE = "npc_dialogue"
    SCENE_OBSERVATION = "scene_observation"
    SAVE_EXIT = "save_exit"
    STATUS = "status"
    RECAP = "recap"
    LOOK_AROUND = "look_around"


class PlayerIntent(BaseModel):
    """Structured output from PlayerIntentAgent."""

    model_config = ConfigDict(frozen=True)

    category: IntentCategory
    check_hint: str | None = None
    reason: str = ""

    @model_validator(mode="before")
    @classmethod
    def _normalise_ollama_drift(cls, data: object) -> object:
        """Remap field names that local LLMs use instead of the schema fields.

        Ollama models sometimes return the input context echoed back with
        ``phase`` instead of ``category``, and embed the skill name inside
        ``skill_check_parameters.skill`` instead of ``check_hint``.
        """
        if not isinstance(data, dict):
            return data
        # Map 'phase' → 'category' when 'category' is absent.
        if "category" not in data and "phase" in data:
            data = {**data, "category": data["phase"]}
        # Extract nested skill name → check_hint when check_hint is absent.
        if "check_hint" not in data:
            params = data.get("skill_check_parameters")
            if isinstance(params, dict) and "skill" in params:
                data = {**data, "check_hint": params["skill"]}
        return data


__all__ = [
    "Action",
    "ActorState",
    "ActorType",
    "Adjudication",
    "CampaignEvent",
    "CampaignState",
    "CombatAssessment",
    "CombatIntent",
    "CombatOutcome",
    "CombatResult",
    "CombatStatus",
    "DivergenceAssessment",
    "EncounterNpc",
    "EncounterPhase",
    "EncounterPlanList",
    "EncounterReady",
    "EncounterRecoveryResult",
    "EncounterState",
    "EncounterTemplate",
    "FeatState",
    "GameState",
    "InitiativeTurn",
    "IntentCategory",
    "InventoryItem",
    "Milestone",
    "MilestoneAchieved",
    "ModuleState",
    "Narration",
    "NarrationFrame",
    "NarrationResponse",
    "NpcPresence",
    "NpcPresenceStatus",
    "PlayerIO",
    "PlayerInput",
    "PlayerIntent",
    "RecoveryPeriod",
    "ResourceState",
    "RollRequest",
    "RollResult",
    "RollVisibility",
    "RuleReference",
    "RulesAdjudication",
    "RulesAdjudicationRequest",
    "SceneOpeningResponse",
    "StateEffect",
    "TurnResources",
    "WeaponState",
]
