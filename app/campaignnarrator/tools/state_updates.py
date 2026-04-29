"""State update helpers for campaign character and encounter changes."""

from __future__ import annotations

import logging
from copy import deepcopy
from dataclasses import replace

from campaignnarrator.domain.models import (
    ActorRegistry,
    ActorState,
    EncounterPhase,
    EncounterState,
    NpcPresenceStatus,
    StateEffect,
)

_log = logging.getLogger(__name__)


def apply_state_effects(
    state: EncounterState,
    registry: ActorRegistry,
    effects: tuple[StateEffect, ...],
) -> tuple[EncounterState, ActorRegistry]:
    """Apply structured state effects without mutating input state or registry."""
    updated_state = state
    updated_registry = registry
    for effect in effects:
        updated_state, updated_registry = _apply_state_effect(
            updated_state, updated_registry, effect
        )
    return updated_state, updated_registry


def _apply_set_phase(
    state: EncounterState,
    registry: ActorRegistry,
    target: str,
    value: object,
) -> tuple[EncounterState, ActorRegistry]:
    _require_encounter_target(state, target)
    return _copy_state_with(state, phase=_coerce_phase(value)), registry


def _apply_append_public_event(
    state: EncounterState,
    registry: ActorRegistry,
    target: str,
    value: object,
) -> tuple[EncounterState, ActorRegistry]:
    _require_encounter_target(state, target)
    return (
        replace(
            state,
            public_events=(
                *state.public_events,
                _require_string(value, "public event"),
            ),
            hidden_facts=_copy_hidden_facts(state),
        ),
        registry,
    )


def _apply_set_encounter_outcome(
    state: EncounterState,
    registry: ActorRegistry,
    target: str,
    value: object,
) -> tuple[EncounterState, ActorRegistry]:
    _require_encounter_target(state, target)
    return (
        replace(
            state,
            hidden_facts=_copy_hidden_facts(state),
            outcome=_require_string(value, "encounter outcome"),
        ),
        registry,
    )


def _apply_change_hp(
    state: EncounterState,
    registry: ActorRegistry,
    target: str,
    value: object,
) -> tuple[EncounterState, ActorRegistry]:
    actor = _require_actor(registry, target)
    delta = require_int(value, "hp delta")
    updated_actor = replace(
        actor,
        hp_current=max(0, min(actor.hp_max, actor.hp_current + delta)),
    )
    return state, registry.with_actor(updated_actor)


def _apply_inventory_spent(
    state: EncounterState,
    registry: ActorRegistry,
    target: str,
    value: object,
) -> tuple[EncounterState, ActorRegistry]:
    actor = _require_actor(registry, target)
    item_id = _require_string(value, "inventory item_id")
    inventory = list(actor.inventory)
    for i, inv_item in enumerate(inventory):
        if inv_item.item_id == item_id:
            if inv_item.count > 1:
                inventory[i] = replace(inv_item, count=inv_item.count - 1)
            else:
                inventory.pop(i)
            updated_actor = replace(actor, inventory=tuple(inventory))
            return state, registry.with_actor(updated_actor)
    msg = f"actor {actor.actor_id} does not have item with item_id: {item_id}"
    raise ValueError(msg)


def _apply_add_condition(
    state: EncounterState,
    registry: ActorRegistry,
    target: str,
    value: object,
) -> tuple[EncounterState, ActorRegistry]:
    actor = _require_actor(registry, target)
    condition = _require_string(value, "condition")
    return state, registry.with_actor(actor.with_condition(condition))


def _apply_remove_condition(
    state: EncounterState,
    registry: ActorRegistry,
    target: str,
    value: object,
) -> tuple[EncounterState, ActorRegistry]:
    actor = _require_actor(registry, target)
    condition = _require_string(value, "condition")
    return state, registry.with_actor(actor.without_condition(condition))


def _apply_set_npc_status(
    state: EncounterState,
    registry: ActorRegistry,
    target: str,
    value: object,
) -> tuple[EncounterState, ActorRegistry]:
    raw = _require_string(value, "npc status")
    try:
        new_status = NpcPresenceStatus(raw)
    except ValueError as exc:
        msg = f"set_npc_status: invalid status {raw!r}"
        raise TypeError(msg) from exc
    presences = list(state.npc_presences)
    for i, presence in enumerate(presences):
        if presence.actor_id == target:
            presences[i] = replace(presence, status=new_status)
            return (
                replace(
                    state,
                    npc_presences=tuple(presences),
                    hidden_facts=_copy_hidden_facts(state),
                ),
                registry,
            )
    _log.warning(
        "set_npc_status: no NpcPresence found for actor_id %r — effect ignored",
        target,
    )
    return state, registry


_EFFECT_HANDLERS = {
    "set_phase": _apply_set_phase,
    "append_public_event": _apply_append_public_event,
    "set_encounter_outcome": _apply_set_encounter_outcome,
    "change_hp": _apply_change_hp,
    "inventory_spent": _apply_inventory_spent,
    "add_condition": _apply_add_condition,
    "remove_condition": _apply_remove_condition,
    "set_npc_status": _apply_set_npc_status,
}


def _apply_state_effect(
    state: EncounterState,
    registry: ActorRegistry,
    effect: StateEffect,
) -> tuple[EncounterState, ActorRegistry]:
    handler = _EFFECT_HANDLERS.get(effect.effect_type)
    if handler is None:
        _log.warning("Skipping unsupported state effect type: %s", effect.effect_type)
        return state, registry
    return handler(state, registry, effect.target, effect.value)


def _require_actor(registry: ActorRegistry, actor_id: str) -> ActorState:
    actor = registry.actors.get(actor_id)
    if actor is None:
        msg = f"unknown actor: {actor_id}"
        raise ValueError(msg)
    return actor


def _require_encounter_target(state: EncounterState, target: str) -> None:
    expected = f"encounter:{state.encounter_id}"
    if target == expected:
        return
    if target.startswith("encounter:"):
        msg = f"state effect target mismatch: {target}"
        raise ValueError(msg)
    _log.warning(
        "Malformed encounter target %r (expected %r) — applying to current encounter",
        target,
        expected,
    )


def _coerce_phase(value: object) -> EncounterPhase:
    if isinstance(value, EncounterPhase):
        return value
    if isinstance(value, str):
        return EncounterPhase(value)
    msg = f"invalid encounter phase: {value}"
    raise TypeError(msg)


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str):
        msg = f"invalid {label}: {value}"
        raise TypeError(msg)
    return value


def require_int(value: object, label: str) -> int:
    if not isinstance(value, int):
        msg = f"invalid {label}: {value}"
        raise TypeError(msg)
    return value


def _copy_hidden_facts(state: EncounterState) -> dict[str, object]:
    return deepcopy(dict(state.hidden_facts))


def _copy_state_with(
    state: EncounterState,
    **changes: object,
) -> EncounterState:
    if "hidden_facts" not in changes:
        changes["hidden_facts"] = _copy_hidden_facts(state)
    return replace(state, **changes)
