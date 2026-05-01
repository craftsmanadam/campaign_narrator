"""State update helpers for campaign character and encounter changes."""

from __future__ import annotations

import logging

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
    return state.with_phase(_coerce_phase(value)), registry


def _apply_append_public_event(
    state: EncounterState,
    registry: ActorRegistry,
    target: str,
    value: object,
) -> tuple[EncounterState, ActorRegistry]:
    _require_encounter_target(state, target)
    return state.append_public_event(_require_string(value, "public event")), registry


def _apply_set_encounter_outcome(
    state: EncounterState,
    registry: ActorRegistry,
    target: str,
    value: object,
) -> tuple[EncounterState, ActorRegistry]:
    _require_encounter_target(state, target)
    return state.with_outcome(_require_string(value, "encounter outcome")), registry


def _apply_change_hp(
    state: EncounterState,
    registry: ActorRegistry,
    target: str,
    value: object,
) -> tuple[EncounterState, ActorRegistry]:
    actor = _require_actor(registry, target)
    delta = require_int(value, "hp delta")
    return state, registry.with_actor(actor.apply_change_hp(delta))


def _apply_inventory_spent(
    state: EncounterState,
    registry: ActorRegistry,
    target: str,
    value: object,
) -> tuple[EncounterState, ActorRegistry]:
    actor = _require_actor(registry, target)
    item_id = _require_string(value, "inventory item_id")
    return state, registry.with_actor(actor.apply_inventory_spent(item_id))


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
    if not any(p.actor_id == target for p in state.npc_presences):
        _log.warning(
            "set_npc_status: no NpcPresence found for actor_id %r — effect ignored",
            target,
        )
        return state, registry
    return state.with_npc_status(target, new_status), registry


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
