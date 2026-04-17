"""Encounter persistence repository."""

from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path

from campaignnarrator.domain.models import (
    ActorState,
    ActorType,
    EncounterPhase,
    EncounterState,
    FeatState,
    InitiativeTurn,
    InventoryItem,
    RecoveryPeriod,
    ResourceState,
    WeaponState,
)


class EncounterRepository:
    """Persist and load the single active encounter to/from a JSON file."""

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)
        self._encounter_path = self._root / "encounters" / "active.json"

    def load_active(self) -> EncounterState | None:
        """Load the active encounter. Returns None if no file exists."""
        if not self._encounter_path.exists():
            return None
        return _encounter_state_from_seed(json.loads(self._encounter_path.read_text()))

    def save(self, state: EncounterState) -> None:
        """Persist the active encounter to disk."""
        self._encounter_path.parent.mkdir(parents=True, exist_ok=True)
        self._encounter_path.write_text(
            json.dumps(_encounter_state_to_json(state), indent=2, sort_keys=True) + "\n"
        )

    def clear(self) -> None:
        """Delete the active encounter file."""
        if self._encounter_path.exists():
            self._encounter_path.unlink()


def _encounter_state_to_json(state: EncounterState) -> dict[str, object]:
    return {
        "encounter_id": state.encounter_id,
        "phase": state.phase.value,
        "setting": state.setting,
        "public_events": list(state.public_events),
        "hidden_facts": dict(state.hidden_facts),
        "combat_turns": [
            {"actor_id": t.actor_id, "initiative_roll": t.initiative_roll}
            for t in state.combat_turns
        ],
        "outcome": state.outcome,
        "scene_tone": state.scene_tone,
        "actors": {
            actor_id: _actor_state_to_json(actor)
            for actor_id, actor in state.actors.items()
        },
    }


def _actor_state_to_json(actor: ActorState) -> dict[str, object]:
    return {
        "actor_id": actor.actor_id,
        "name": actor.name,
        "actor_type": actor.actor_type.value,
        "hp_max": actor.hp_max,
        "hp_current": actor.hp_current,
        "hp_temp": actor.hp_temp,
        "armor_class": actor.armor_class,
        "strength": actor.strength,
        "dexterity": actor.dexterity,
        "constitution": actor.constitution,
        "intelligence": actor.intelligence,
        "wisdom": actor.wisdom,
        "charisma": actor.charisma,
        "proficiency_bonus": actor.proficiency_bonus,
        "initiative_bonus": actor.initiative_bonus,
        "speed": actor.speed,
        "ac_breakdown": list(actor.ac_breakdown),
        "saving_throws": [list(pair) for pair in actor.saving_throws],
        "resources": [_resource_state_to_json(r) for r in actor.resources],
        "inventory": [_inventory_item_to_json(i) for i in actor.inventory],
        "action_options": list(actor.action_options),
        "attacks_per_action": actor.attacks_per_action,
        "bonus_action_options": list(actor.bonus_action_options),
        "reaction_options": list(actor.reaction_options),
        "equipped_weapons": [_weapon_state_to_json(w) for w in actor.equipped_weapons],
        "feats": [_feat_state_to_json(f) for f in actor.feats],
        "damage_resistances": list(actor.damage_resistances),
        "damage_vulnerabilities": list(actor.damage_vulnerabilities),
        "damage_immunities": list(actor.damage_immunities),
        "condition_immunities": list(actor.condition_immunities),
        "conditions": list(actor.conditions),
        "death_save_successes": actor.death_save_successes,
        "death_save_failures": actor.death_save_failures,
        "spell_slots": [list(pair) for pair in actor.spell_slots],
        "spell_slots_max": [list(pair) for pair in actor.spell_slots_max],
        "available_spells": list(actor.available_spells),
        "concentration": actor.concentration,
        "personality": actor.personality,
        "is_visible": actor.is_visible,
    }


def _weapon_state_to_json(weapon: WeaponState) -> dict[str, object]:
    return {
        "name": weapon.name,
        "attack_bonus": weapon.attack_bonus,
        "damage_dice": weapon.damage_dice,
        "damage_bonus": weapon.damage_bonus,
        "damage_type": weapon.damage_type,
        "properties": list(weapon.properties),
    }


def _feat_state_to_json(feat: FeatState) -> dict[str, object]:
    return {
        "name": feat.name,
        "effect_summary": feat.effect_summary,
        "reference": feat.reference,
        "per_turn_uses": feat.per_turn_uses,
    }


def _resource_state_to_json(resource: ResourceState) -> dict[str, object]:
    return {
        "resource": resource.resource,
        "current": resource.current,
        "max": resource.max,
        "recovers_after": resource.recovers_after.value,
        "reference": resource.reference,
    }


def _inventory_item_to_json(item: InventoryItem) -> dict[str, object]:
    return {
        "item_id": item.item_id,
        "item": item.item,
        "count": item.count,
        "charges": item.charges,
        "max_charges": item.max_charges,
        "recovers_after": (
            item.recovers_after.value if item.recovers_after is not None else None
        ),
        "reference": item.reference,
    }


def _encounter_state_from_seed(seed: Mapping[str, object]) -> EncounterState:
    encounter_id = _require_string_seed_value(seed, "encounter_id")
    phase = _require_phase(seed)
    setting = _require_string_seed_value(seed, "setting")
    actors = _encounter_actors_from_seed(seed)
    return EncounterState(
        encounter_id=encounter_id,
        phase=phase,
        setting=setting,
        actors=actors,
        public_events=_string_tuple_from_seed(seed, "public_events"),
        hidden_facts=_mapping_from_seed(seed, "hidden_facts"),
        combat_turns=_combat_turns_from_seed(seed),
        outcome=_optional_string_from_seed(seed, "outcome"),
        scene_tone=_optional_string_from_seed(seed, "scene_tone"),
    )


def _encounter_actors_from_seed(seed: Mapping[str, object]) -> dict[str, ActorState]:
    actors = seed.get("actors")
    if not isinstance(actors, Mapping):
        _raise_seed_actors_must_be_mapping()
    return {
        actor_id: _actor_state_from_seed(actor_seed, actor_id=str(actor_id))
        for actor_id, actor_seed in actors.items()
    }


def _actor_state_from_seed(
    seed: object,
    *,
    actor_id: str = "unknown",
) -> ActorState:
    if not isinstance(seed, Mapping):
        _raise_invalid_actor_seed(actor_id, "actor_id")

    resolved_actor_id = actor_id
    actor_id_value = seed.get("actor_id")
    if not isinstance(actor_id_value, str):
        _raise_invalid_actor_seed(resolved_actor_id, "actor_id")
    resolved_actor_id = actor_id_value

    name = _require_actor_string(seed, resolved_actor_id, "name")
    actor_type = _require_actor_type(seed, resolved_actor_id)
    hp_current = _require_actor_int(seed, resolved_actor_id, "hp_current")
    hp_max = _require_actor_int(seed, resolved_actor_id, "hp_max")
    armor_class = _require_actor_int(seed, resolved_actor_id, "armor_class")

    return ActorState(
        actor_id=resolved_actor_id,
        name=name,
        actor_type=actor_type,
        hp_max=hp_max,
        hp_current=hp_current,
        armor_class=armor_class,
        strength=_require_actor_int(seed, resolved_actor_id, "strength"),
        dexterity=_require_actor_int(seed, resolved_actor_id, "dexterity"),
        constitution=_require_actor_int(seed, resolved_actor_id, "constitution"),
        intelligence=_require_actor_int(seed, resolved_actor_id, "intelligence"),
        wisdom=_require_actor_int(seed, resolved_actor_id, "wisdom"),
        charisma=_require_actor_int(seed, resolved_actor_id, "charisma"),
        proficiency_bonus=_require_actor_int(
            seed, resolved_actor_id, "proficiency_bonus"
        ),
        initiative_bonus=_require_actor_int(
            seed, resolved_actor_id, "initiative_bonus"
        ),
        speed=_require_actor_int(seed, resolved_actor_id, "speed"),
        attacks_per_action=_require_actor_int(
            seed, resolved_actor_id, "attacks_per_action"
        ),
        action_options=_string_tuple_field_from_seed(
            seed, resolved_actor_id, "action_options"
        ),
        ac_breakdown=_string_tuple_field_from_seed(
            seed, resolved_actor_id, "ac_breakdown"
        ),
        hp_temp=_optional_int_from_seed(seed, "hp_temp", default=0),
        saving_throws=_int_pair_tuple_from_seed(seed, "saving_throws"),
        resources=_resources_from_seed(seed),
        inventory=_inventory_from_seed(seed),
        bonus_action_options=_string_tuple_field_from_seed(
            seed, resolved_actor_id, "bonus_action_options"
        ),
        reaction_options=_string_tuple_field_from_seed(
            seed, resolved_actor_id, "reaction_options"
        ),
        equipped_weapons=_weapons_from_seed(seed),
        feats=_feats_from_seed(seed),
        damage_resistances=_string_tuple_field_from_seed(
            seed, resolved_actor_id, "damage_resistances"
        ),
        damage_vulnerabilities=_string_tuple_field_from_seed(
            seed, resolved_actor_id, "damage_vulnerabilities"
        ),
        damage_immunities=_string_tuple_field_from_seed(
            seed, resolved_actor_id, "damage_immunities"
        ),
        condition_immunities=_string_tuple_field_from_seed(
            seed, resolved_actor_id, "condition_immunities"
        ),
        conditions=_string_tuple_field_from_seed(seed, resolved_actor_id, "conditions"),
        death_save_successes=_optional_int_from_seed(
            seed, "death_save_successes", default=0
        ),
        death_save_failures=_optional_int_from_seed(
            seed, "death_save_failures", default=0
        ),
        spell_slots=_int_pair_tuple_from_seed(seed, "spell_slots"),
        spell_slots_max=_int_pair_tuple_from_seed(seed, "spell_slots_max"),
        available_spells=_string_tuple_field_from_seed(
            seed, resolved_actor_id, "available_spells"
        ),
        concentration=_optional_string_from_seed(seed, "concentration"),
        personality=_optional_string_from_seed(seed, "personality"),
        is_visible=_bool_field_from_seed(seed, resolved_actor_id, "is_visible"),
    )


def _require_string_seed_value(seed: Mapping[str, object], key: str) -> str:
    value = seed.get(key)
    if not isinstance(value, str):
        _raise_invalid_encounter_seed(key)
    return value


def _require_phase(seed: Mapping[str, object]) -> EncounterPhase:
    phase_value = seed.get("phase")
    if not isinstance(phase_value, str):
        _raise_invalid_encounter_seed("phase")
    try:
        return EncounterPhase(phase_value)
    except ValueError:
        _raise_invalid_encounter_phase(phase_value)


def _mapping_from_seed(seed: Mapping[str, object], key: str) -> dict[str, object]:
    value = seed.get(key, {})
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        _raise_invalid_encounter_seed(key)
    return deepcopy(dict(value))


def _optional_string_from_seed(
    seed: Mapping[str, object],
    key: str,
) -> str | None:
    value = seed.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        _raise_invalid_encounter_seed(key)
    return value


def _string_tuple_from_seed(
    seed: Mapping[str, object],
    key: str,
) -> tuple[str, ...]:
    value = seed.get(key, ())
    return _string_tuple_value(value, key, "invalid encounter seed")


def _string_tuple_field_from_seed(
    seed: Mapping[str, object],
    actor_id: str,
    key: str,
) -> tuple[str, ...]:
    value = seed.get(key, ())
    return _string_tuple_value(value, key, f"invalid actor seed: {actor_id}")


def _string_tuple_value(
    value: object,
    key: str,
    error_prefix: str,
) -> tuple[str, ...]:
    if not isinstance(value, tuple | list):
        _raise_seed_list_value_error(error_prefix, key)
    if not all(isinstance(item, str) for item in value):
        _raise_seed_list_value_error(error_prefix, key)
    return tuple(value)


def _require_actor_string(
    seed: Mapping[str, object],
    actor_id: str,
    key: str,
) -> str:
    value = seed.get(key)
    if not isinstance(value, str):
        _raise_invalid_actor_seed(actor_id, key)
    return value


def _require_actor_int(
    seed: Mapping[str, object],
    actor_id: str,
    key: str,
) -> int:
    value = seed.get(key)
    if type(value) is not int:
        _raise_invalid_actor_seed(actor_id, key)
    return value


def _require_actor_type(seed: Mapping[str, object], actor_id: str) -> ActorType:
    value = seed.get("actor_type")
    if not isinstance(value, str):
        _raise_invalid_actor_seed(actor_id, "actor_type")
    try:
        return ActorType(value)
    except ValueError:
        _raise_invalid_actor_seed(actor_id, "actor_type")


def _optional_int_from_seed(
    seed: Mapping[str, object],
    key: str,
    *,
    default: int,
) -> int:
    value = seed.get(key, default)
    if type(value) is not int:
        return default
    return value


def _int_pair_tuple_from_seed(
    seed: Mapping[str, object],
    key: str,
) -> tuple[tuple[str, int], ...]:
    value = seed.get(key, ())
    if not isinstance(value, list | tuple):
        return ()
    pairs = []
    for item in value:
        if isinstance(item, list | tuple) and len(item) == 2:  # noqa: PLR2004
            k, v = item
            if isinstance(k, str) and type(v) is int:
                pairs.append((k, v))
    return tuple(pairs)


def _weapons_from_seed(seed: Mapping[str, object]) -> tuple[WeaponState, ...]:
    value = seed.get("equipped_weapons", ())
    if not isinstance(value, list | tuple):
        return ()
    weapons = []
    for w in value:
        if not isinstance(w, Mapping):
            continue
        try:
            weapons.append(
                WeaponState(
                    name=str(w.get("name", "")),
                    attack_bonus=int(w.get("attack_bonus", 0)),
                    damage_dice=str(w.get("damage_dice", "1d4")),
                    damage_bonus=int(w.get("damage_bonus", 0)),
                    damage_type=str(w.get("damage_type", "bludgeoning")),
                    properties=tuple(str(p) for p in w.get("properties", ())),
                )
            )
        except TypeError, ValueError:
            continue
    return tuple(weapons)


def _feats_from_seed(seed: Mapping[str, object]) -> tuple[FeatState, ...]:
    value = seed.get("feats", ())
    if not isinstance(value, list | tuple):
        return ()
    feats = []
    for f in value:
        if not isinstance(f, Mapping):
            continue
        try:
            feats.append(
                FeatState(
                    name=str(f.get("name", "")),
                    effect_summary=str(f.get("effect_summary", "")),
                    reference=(
                        f.get("reference")
                        if isinstance(f.get("reference"), str)
                        else None
                    ),
                    per_turn_uses=(
                        int(f["per_turn_uses"])
                        if f.get("per_turn_uses") is not None
                        else None
                    ),
                )
            )
        except TypeError, ValueError, KeyError:
            continue
    return tuple(feats)


def _combat_turns_from_seed(
    seed: Mapping[str, object],
) -> tuple[InitiativeTurn, ...]:
    value = seed.get("combat_turns", ())
    if not isinstance(value, list | tuple):
        return ()
    turns = []
    for item in value:
        if isinstance(item, Mapping):
            actor_id = item.get("actor_id")
            roll = item.get("initiative_roll")
            if isinstance(actor_id, str) and type(roll) is int:
                turns.append(InitiativeTurn(actor_id=actor_id, initiative_roll=roll))
    return tuple(turns)


def _resources_from_seed(seed: Mapping[str, object]) -> tuple[ResourceState, ...]:
    value = seed.get("resources", ())
    if not isinstance(value, list | tuple):
        return ()
    resources = []
    for r in value:
        if not isinstance(r, Mapping):
            continue
        try:
            resources.append(
                ResourceState(
                    resource=str(r.get("resource", "")),
                    current=int(r.get("current", 0)),
                    max=int(r.get("max", 0)),
                    recovers_after=RecoveryPeriod(r.get("recovers_after", "long_rest")),
                    reference=(
                        r.get("reference")
                        if isinstance(r.get("reference"), str)
                        else None
                    ),
                )
            )
        except TypeError, ValueError, KeyError:
            continue
    return tuple(resources)


def _inventory_from_seed(seed: Mapping[str, object]) -> tuple[InventoryItem, ...]:
    value = seed.get("inventory", ())
    if not isinstance(value, list | tuple):
        return ()
    items = []
    for i in value:
        if not isinstance(i, Mapping):
            continue
        try:
            recovers_raw = i.get("recovers_after")
            recovers_after = (
                RecoveryPeriod(recovers_raw) if isinstance(recovers_raw, str) else None
            )
            items.append(
                InventoryItem(
                    item_id=str(i.get("item_id", "")),
                    item=str(i.get("item", "")),
                    count=int(i.get("count", 0)),
                    charges=int(i["charges"]) if i.get("charges") is not None else None,
                    max_charges=(
                        int(i["max_charges"])
                        if i.get("max_charges") is not None
                        else None
                    ),
                    recovers_after=recovers_after,
                    reference=(
                        i.get("reference")
                        if isinstance(i.get("reference"), str)
                        else None
                    ),
                )
            )
        except TypeError, ValueError, KeyError:
            continue
    return tuple(items)


def _bool_field_from_seed(
    seed: Mapping[str, object],
    actor_id: str,
    key: str,
) -> bool:
    value = seed.get(key, True)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        if value == "true":
            return True
        if value == "false":
            return False
    _raise_invalid_actor_seed(actor_id, key)


def _raise_seed_actors_must_be_mapping() -> None:
    raise ValueError("seed actors must be a mapping")  # noqa: TRY003


def _raise_invalid_encounter_seed(key: str) -> None:
    raise ValueError(f"invalid encounter seed: {key}")  # noqa: TRY003


def _raise_invalid_encounter_phase(value: object) -> None:
    raise ValueError(f"invalid encounter phase: {value}")  # noqa: TRY003


def _raise_seed_list_value_error(error_prefix: str, key: str) -> None:
    raise ValueError(f"{error_prefix}: {key}")  # noqa: TRY003


def _raise_invalid_actor_seed(actor_id: str, key: str) -> None:
    raise ValueError(f"invalid actor seed: {actor_id}.{key}")  # noqa: TRY003
