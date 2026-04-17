"""State update helpers for campaign character and encounter changes."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

from campaignnarrator.domain.models import (
    ActorState,
    EncounterPhase,
    EncounterState,
    StateEffect,
)


def apply_state_effects(
    state: EncounterState,
    effects: tuple[StateEffect, ...],
) -> EncounterState:
    """Apply structured encounter state effects without mutating the input state."""

    updated_state = state
    for effect in effects:
        updated_state = _apply_state_effect(updated_state, effect)
    return updated_state


def _apply_state_effect(state: EncounterState, effect: StateEffect) -> EncounterState:
    if effect.effect_type == "set_phase":
        return _apply_set_phase(state, effect.target, effect.value)
    if effect.effect_type == "append_public_event":
        return _apply_append_public_event(state, effect.target, effect.value)
    if effect.effect_type == "set_encounter_outcome":
        return _apply_set_encounter_outcome(state, effect.target, effect.value)
    if effect.effect_type == "change_hp":
        return _apply_change_hp(state, effect.target, effect.value)
    raise ValueError(  # noqa: TRY003
        f"unsupported state effect: {effect.effect_type}"
    )


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
    return EncounterState(
        encounter_id=state.encounter_id,
        phase=state.phase,
        setting=state.setting,
        actors=state.actors,
        public_events=(*state.public_events, _require_string(value, "public event")),
        hidden_facts=_copy_hidden_facts(state),
        combat_turns=state.combat_turns,
        outcome=state.outcome,
        scene_tone=state.scene_tone,
    )


def _apply_set_encounter_outcome(
    state: EncounterState,
    target: str,
    value: object,
) -> EncounterState:
    _require_encounter_target(state, target)
    return EncounterState(
        encounter_id=state.encounter_id,
        phase=state.phase,
        setting=state.setting,
        actors=state.actors,
        public_events=state.public_events,
        hidden_facts=_copy_hidden_facts(state),
        combat_turns=state.combat_turns,
        outcome=_require_string(value, "encounter outcome"),
        scene_tone=state.scene_tone,
    )


def _apply_change_hp(
    state: EncounterState,
    target: str,
    value: object,
) -> EncounterState:
    actor = _require_actor(state, target)
    delta = _require_int(value, "hp delta")
    updated_actor = replace(
        actor,
        hp_current=max(0, min(actor.hp_max, actor.hp_current + delta)),
    )
    return _replace_actor(state, updated_actor)


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
    if target != f"encounter:{state.encounter_id}":
        raise ValueError(f"state effect target mismatch: {target}")  # noqa: TRY003


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


def _require_int(value: object, label: str) -> int:
    if not isinstance(value, int):
        raise TypeError(f"invalid {label}: {value}")  # noqa: TRY003
    return value


def _copy_hidden_facts(state: EncounterState) -> dict[str, object]:
    return deepcopy(dict(state.hidden_facts))


def _copy_state_with(
    state: EncounterState,
    **changes: object,
) -> EncounterState:
    values = {
        "encounter_id": state.encounter_id,
        "phase": state.phase,
        "setting": state.setting,
        "actors": state.actors,
        "public_events": state.public_events,
        "hidden_facts": _copy_hidden_facts(state),
        "combat_turns": state.combat_turns,
        "outcome": state.outcome,
        "scene_tone": state.scene_tone,
    }
    values.update(changes)
    return EncounterState(**values)
