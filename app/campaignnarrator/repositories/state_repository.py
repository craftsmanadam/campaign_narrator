"""State repositories for campaign and encounter data."""

from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from campaignnarrator.domain.models import ActorState, EncounterPhase, EncounterState


class StateRepository:
    """Store encounter state in memory, with file-backed persistence support."""

    def __init__(self, root: Path | str | None = None) -> None:
        self._state_root = Path(root) if root is not None else None
        self._encounter_dir = (
            self._state_root / "encounters" if self._state_root is not None else None
        )
        self._player_character_path = (
            self._state_root / "player_character.json"
            if self._state_root is not None
            else None
        )
        self._encounters: dict[str, EncounterState] = {}

    @classmethod
    def from_seed(cls, seed: object) -> StateRepository:
        """Build an in-memory repository from a structured encounter seed."""

        if not isinstance(seed, Mapping):
            _raise_invalid_encounter_seed("root")
        state = _encounter_state_from_seed(seed)
        repository = cls()
        repository._encounters[state.encounter_id] = state
        return repository

    @classmethod
    def from_default_encounter(cls) -> StateRepository:
        """Build the default goblin camp encounter repository."""

        return cls.from_seed(_default_seed())

    def load_encounter(self, encounter_id: str) -> EncounterState:
        """Return a copy of the requested encounter state.

        Checks the in-memory cache first. Falls back to reading from
        state/encounters/{encounter_id}.json if a state root is configured.
        """

        if encounter_id in self._encounters:
            return _copy_encounter_state(self._encounters[encounter_id])
        if self._encounter_dir is not None:
            path = self._encounter_dir / f"{encounter_id}.json"
            if path.exists():
                state = _encounter_state_from_seed(json.loads(path.read_text()))
                self._encounters[encounter_id] = state
                return _copy_encounter_state(state)
        raise ValueError(f"unknown encounter: {encounter_id}")  # noqa: TRY003

    def save_encounter(self, state: EncounterState) -> None:
        """Persist a copy of the supplied encounter state.

        Always updates the in-memory cache. Also writes to
        state/encounters/{encounter_id}.json if a state root is configured.
        """

        copied = _copy_encounter_state(state)
        self._encounters[state.encounter_id] = copied
        if self._encounter_dir is not None:
            self._encounter_dir.mkdir(parents=True, exist_ok=True)
            path = self._encounter_dir / f"{state.encounter_id}.json"
            path.write_text(
                json.dumps(_encounter_state_to_json(copied), indent=2, sort_keys=True)
                + "\n"
            )

    def load_player_character(self) -> dict[str, Any]:
        """Read the legacy player character snapshot from disk."""

        if self._player_character_path is None:
            raise ValueError("legacy player character storage unavailable")  # noqa: TRY003
        return json.loads(self._player_character_path.read_text())

    def save_player_character(self, player_character: dict[str, Any]) -> None:
        """Persist the legacy player character snapshot to disk."""

        if self._player_character_path is None:
            raise ValueError("legacy player character storage unavailable")  # noqa: TRY003
        self._player_character_path.write_text(
            json.dumps(player_character, indent=2, sort_keys=True) + "\n"
        )


def _encounter_state_to_json(state: EncounterState) -> dict[str, object]:
    return {
        "encounter_id": state.encounter_id,
        "phase": state.phase.value,
        "setting": state.setting,
        "public_events": list(state.public_events),
        "hidden_facts": dict(state.hidden_facts),
        "initiative_order": list(state.initiative_order),
        "outcome": state.outcome,
        "actors": {
            actor_id: _actor_state_to_json(actor)
            for actor_id, actor in state.actors.items()
        },
    }


def _actor_state_to_json(actor: ActorState) -> dict[str, object]:
    return {
        "actor_id": actor.actor_id,
        "name": actor.name,
        "kind": actor.kind,
        "hp_current": actor.hp_current,
        "hp_max": actor.hp_max,
        "armor_class": actor.armor_class,
        "inventory": list(actor.inventory),
        "conditions": list(actor.conditions),
        "is_visible": actor.is_visible,
        "character_class": actor.character_class,
        "character_background": actor.character_background,
    }


def _default_seed() -> dict[str, object]:
    return {
        "encounter_id": "goblin-camp",
        "setting": "A ruined roadside camp.",
        "phase": "scene_opening",
        "public_events": [],
        "hidden_facts": {"goblin_disposition": "neutral"},
        "actors": {
            "pc:talia": {
                "actor_id": "pc:talia",
                "name": "Talia",
                "kind": "pc",
                "hp_current": 12,
                "hp_max": 12,
                "armor_class": 18,
                "inventory": [
                    "longsword",
                    "chain-mail",
                    "shield",
                    "potion-of-healing",
                ],
                "is_visible": True,
                "character_class": "fighter",
                "character_background": "soldier",
            },
            "npc:goblin-scout": {
                "actor_id": "npc:goblin-scout",
                "name": "Goblin Scout",
                "kind": "npc",
                "hp_current": 7,
                "hp_max": 7,
                "armor_class": 15,
                "inventory": ["scimitar", "shortbow"],
                "is_visible": True,
                "character_class": None,
                "character_background": None,
            },
        },
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
        initiative_order=_string_tuple_from_seed(seed, "initiative_order"),
        outcome=_optional_string_from_seed(seed, "outcome"),
    )


def _encounter_actors_from_seed(seed: dict[str, object]) -> dict[str, ActorState]:
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
    kind = _require_actor_string(seed, resolved_actor_id, "kind")
    hp_current = _require_actor_int(seed, resolved_actor_id, "hp_current")
    hp_max = _require_actor_int(seed, resolved_actor_id, "hp_max")
    armor_class = _require_actor_int(seed, resolved_actor_id, "armor_class")
    inventory = _string_tuple_field_from_seed(seed, resolved_actor_id, "inventory")
    conditions = _string_tuple_field_from_seed(seed, resolved_actor_id, "conditions")
    is_visible = _bool_field_from_seed(seed, resolved_actor_id, "is_visible")
    character_class = _optional_string_from_seed(seed, "character_class")
    character_background = _optional_string_from_seed(seed, "character_background")

    return ActorState(
        actor_id=resolved_actor_id,
        name=name,
        kind=kind,
        hp_current=hp_current,
        hp_max=hp_max,
        armor_class=armor_class,
        inventory=inventory,
        is_visible=is_visible,
        conditions=conditions,
        character_class=character_class,
        character_background=character_background,
    )


def _copy_actor_state(actor: ActorState) -> ActorState:
    return ActorState(
        actor_id=actor.actor_id,
        name=actor.name,
        kind=actor.kind,
        hp_current=actor.hp_current,
        hp_max=actor.hp_max,
        armor_class=actor.armor_class,
        inventory=tuple(actor.inventory),
        is_visible=actor.is_visible,
        conditions=tuple(actor.conditions),
        character_class=actor.character_class,
        character_background=actor.character_background,
    )


def _copy_encounter_state(state: EncounterState) -> EncounterState:
    return EncounterState(
        encounter_id=state.encounter_id,
        phase=state.phase,
        setting=state.setting,
        actors={
            actor_id: _copy_actor_state(actor)
            for actor_id, actor in state.actors.items()
        },
        public_events=tuple(state.public_events),
        hidden_facts=deepcopy(dict(state.hidden_facts)),
        initiative_order=tuple(state.initiative_order),
        outcome=state.outcome,
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
