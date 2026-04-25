"""State update helpers for campaign character and encounter changes."""

from __future__ import annotations

import logging
from copy import deepcopy
from dataclasses import replace

from campaignnarrator.domain.models import (
    ActorState,
    EncounterPhase,
    EncounterState,
    NpcPresence,
    NpcPresenceStatus,
    StateEffect,
)

_log = logging.getLogger(__name__)


def apply_state_effects(
    state: EncounterState,
    effects: tuple[StateEffect, ...],
) -> EncounterState:
    """Apply structured encounter state effects without mutating the input state."""

    updated_state = state
    for effect in effects:
        updated_state = _apply_state_effect(updated_state, effect)
    return updated_state


def _apply_set_phase(
    state: EncounterState,
    target: str,
    value: object,
) -> EncounterState:
    _require_encounter_target(state, target)
    return _copy_state_with(state, phase=_coerce_phase(value))


def _apply_append_public_event(
    state: EncounterState,
    target: str,
    value: object,
) -> EncounterState:
    _require_encounter_target(state, target)
    return replace(
        state,
        public_events=(*state.public_events, _require_string(value, "public event")),
        hidden_facts=_copy_hidden_facts(state),
    )


def _apply_set_encounter_outcome(
    state: EncounterState,
    target: str,
    value: object,
) -> EncounterState:
    _require_encounter_target(state, target)
    return replace(
        state,
        hidden_facts=_copy_hidden_facts(state),
        outcome=_require_string(value, "encounter outcome"),
    )


def _apply_change_hp(
    state: EncounterState,
    target: str,
    value: object,
) -> EncounterState:
    actor = _require_actor(state, target)
    delta = require_int(value, "hp delta")
    updated_actor = replace(
        actor,
        hp_current=max(0, min(actor.hp_max, actor.hp_current + delta)),
    )
    return _replace_actor(state, updated_actor)


def _apply_inventory_spent(
    state: EncounterState,
    target: str,
    value: object,
) -> EncounterState:
    actor = _require_actor(state, target)
    item_id = _require_string(value, "inventory item_id")
    inventory = list(actor.inventory)
    for i, inv_item in enumerate(inventory):
        if inv_item.item_id == item_id:
            if inv_item.count > 1:
                inventory[i] = replace(inv_item, count=inv_item.count - 1)
            else:
                inventory.pop(i)
            updated_actor = replace(actor, inventory=tuple(inventory))
            return _replace_actor(state, updated_actor)
    raise ValueError(  # noqa: TRY003
        f"actor {actor.actor_id} does not have item with item_id: {item_id}"
    )


def _apply_add_condition(
    state: EncounterState,
    target: str,
    value: object,
) -> EncounterState:
    actor = _require_actor(state, target)
    return _replace_actor(
        state, actor.with_condition(_require_string(value, "condition"))
    )


def _apply_remove_condition(
    state: EncounterState,
    target: str,
    value: object,
) -> EncounterState:
    actor = _require_actor(state, target)
    return _replace_actor(
        state, actor.without_condition(_require_string(value, "condition"))
    )


def _apply_set_npc_status(
    state: EncounterState,
    target: str,
    value: object,
) -> EncounterState:
    raw = _require_string(value, "npc status")
    try:
        new_status = NpcPresenceStatus(raw)
    except ValueError as exc:
        raise TypeError(f"set_npc_status: invalid status {raw!r}") from exc  # noqa: TRY003
    presences = list(state.npc_presences)
    for i, presence in enumerate(presences):
        if presence.actor_id == target:
            presences[i] = NpcPresence(
                actor_id=presence.actor_id,
                display_name=presence.display_name,
                description=presence.description,
                name_known=presence.name_known,
                status=new_status,
            )
            return replace(
                state,
                npc_presences=tuple(presences),
                hidden_facts=_copy_hidden_facts(state),
            )
    _log.warning(
        "set_npc_status: no NpcPresence found for actor_id %r — effect ignored",
        target,
    )
    return state


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


def _apply_state_effect(state: EncounterState, effect: StateEffect) -> EncounterState:
    handler = _EFFECT_HANDLERS.get(effect.effect_type)
    if handler is None:
        _log.warning("Skipping unsupported state effect type: %s", effect.effect_type)
        return state
    return handler(state, effect.target, effect.value)


def _replace_actor(state: EncounterState, actor: ActorState) -> EncounterState:
    updated_actors = dict(state.actors)
    updated_actors[actor.actor_id] = actor
    return _copy_state_with(state, actors=updated_actors)


def _require_actor(state: EncounterState, actor_id: str) -> ActorState:
    try:
        return state.actors[actor_id]
    except KeyError as error:
        raise ValueError(f"unknown actor: {actor_id}") from error  # noqa: TRY003


def _require_encounter_target(state: EncounterState, target: str) -> None:
    expected = f"encounter:{state.encounter_id}"
    if target == expected:
        return
    if target.startswith("encounter:"):
        # Properly formatted but wrong encounter ID — genuine state mismatch.
        raise ValueError(f"state effect target mismatch: {target}")  # noqa: TRY003
    # Malformed target (LLM did not use encounter:{id} format) — log and continue.
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
    raise TypeError(f"invalid encounter phase: {value}")  # noqa: TRY003


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"invalid {label}: {value}")  # noqa: TRY003
    return value


def require_int(value: object, label: str) -> int:
    if not isinstance(value, int):
        raise TypeError(f"invalid {label}: {value}")  # noqa: TRY003
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
