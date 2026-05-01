"""Encounter state and phase models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from types import MappingProxyType

from .npc_presence import NpcPresence, NpcPresenceStatus


class EncounterPhase(StrEnum):
    """High-level phases for encounter progression."""

    SCENE_OPENING = "scene_opening"
    SOCIAL = "social"
    RULES_RESOLUTION = "rules_resolution"
    COMBAT = "combat"
    ENCOUNTER_COMPLETE = "encounter_complete"


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
            msg = "InitiativeTurn: actor_id must be str"
            raise TypeError(msg)
        if type(roll) is not int:
            msg = "InitiativeTurn: initiative_roll must be int"
            raise TypeError(msg)
        return cls(actor_id=actor_id, initiative_roll=roll)


@dataclass(frozen=True, slots=True)
class EncounterState:
    """Canonical state for an in-progress encounter."""

    encounter_id: str
    phase: EncounterPhase
    setting: str
    actor_ids: tuple[str, ...] = field(default_factory=tuple)
    player_actor_id: str = ""
    public_events: tuple[str, ...] = field(default_factory=tuple)
    hidden_facts: Mapping[str, object] = field(default_factory=dict)
    # TODO: combat_turns is a smell — combat-specific state embedded in the general
    # encounter object purely for serialization convenience. Should be extracted to a
    # CombatState dataclass (with InitiativeTurn) that EncounterState holds as an
    # optional field: combat_state: CombatState | None = None.
    combat_turns: tuple[InitiativeTurn, ...] = field(default_factory=tuple)
    outcome: str | None = None
    scene_tone: str | None = None
    npc_presences: tuple[NpcPresence, ...] = field(default_factory=tuple)
    current_location: str | None = None
    traveling_actor_ids: tuple[str, ...] = field(default_factory=tuple)
    next_location_hint: str | None = None

    def __post_init__(self) -> None:
        """Snapshot mutable mappings so encounter state cannot be mutated externally."""
        object.__setattr__(
            self, "hidden_facts", MappingProxyType(dict(self.hidden_facts))
        )
        if self.current_location is None:
            object.__setattr__(self, "current_location", self.setting)

    def with_phase(self, phase: EncounterPhase) -> EncounterState:
        """Return a copy of the state with an updated phase."""
        return replace(self, phase=phase)

    def append_public_event(self, event: str) -> EncounterState:
        """Return a copy with event appended to public_events."""
        return replace(self, public_events=(*self.public_events, event))

    def with_outcome(self, outcome: str) -> EncounterState:
        """Return a copy with outcome set."""
        return replace(self, outcome=outcome)

    def with_npc_status(
        self, actor_id: str, status: NpcPresenceStatus
    ) -> EncounterState:
        """Return a copy with the named NPC's presence status updated.

        No-op (no error) if actor_id is not found in npc_presences.
        """
        presences = tuple(
            replace(p, status=status) if p.actor_id == actor_id else p
            for p in self.npc_presences
        )
        return replace(self, npc_presences=presences)

    def with_current_location(self, location: str) -> EncounterState:
        """Return a copy with current_location set."""
        return replace(self, current_location=location)

    def with_traveling_actor_ids(self, ids: tuple[str, ...]) -> EncounterState:
        """Return a copy with traveling_actor_ids replaced."""
        return replace(self, traveling_actor_ids=ids)

    def with_next_location_hint(self, hint: str | None) -> EncounterState:
        """Return a copy with next_location_hint set."""
        return replace(self, next_location_hint=hint)

    def to_dict(self) -> dict[str, object]:
        return {
            "encounter_id": self.encounter_id,
            "phase": self.phase.value,
            "setting": self.setting,
            "current_location": self.current_location,
            "actor_ids": list(self.actor_ids),
            "player_actor_id": self.player_actor_id,
            "public_events": list(self.public_events),
            "hidden_facts": dict(self.hidden_facts),
            "combat_turns": [t.to_dict() for t in self.combat_turns],
            "outcome": self.outcome,
            "scene_tone": self.scene_tone,
            "npc_presences": [p.to_dict() for p in self.npc_presences],
            "traveling_actor_ids": list(self.traveling_actor_ids),
            "next_location_hint": self.next_location_hint,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> EncounterState:
        encounter_id = data.get("encounter_id")
        if not isinstance(encounter_id, str):
            msg = "EncounterState: encounter_id must be str"
            raise TypeError(msg)
        phase_raw = data.get("phase")
        if not isinstance(phase_raw, str):
            msg = "EncounterState: phase must be str"
            raise TypeError(msg)
        setting = data.get("setting")
        if not isinstance(setting, str):
            msg = "EncounterState: setting must be str"
            raise TypeError(msg)

        # Backward compat: old saves have actors dict instead of actor_ids list.
        actor_ids: tuple[str, ...]
        player_actor_id: str
        if "actor_ids" in data:
            actor_ids_raw = data.get("actor_ids", ())
            actor_ids = (
                tuple(str(i) for i in actor_ids_raw if isinstance(i, str))
                if isinstance(actor_ids_raw, list | tuple)
                else ()
            )
            player_actor_id_raw = data.get("player_actor_id", "")
            player_actor_id = (
                player_actor_id_raw if isinstance(player_actor_id_raw, str) else ""
            )
        else:
            # Old format: actors dict — extract keys; find PC for player_actor_id.
            actors_raw = data.get("actors", {})
            if isinstance(actors_raw, Mapping):
                actor_ids = tuple(str(k) for k in actors_raw)
                player_actor_id = _derive_player_actor_id(actors_raw)
            else:
                actor_ids = ()
                player_actor_id = ""

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
        traveling_actor_ids_raw = data.get("traveling_actor_ids", ())
        traveling_actor_ids: tuple[str, ...] = (
            tuple(str(i) for i in traveling_actor_ids_raw if isinstance(i, str))
            if isinstance(traveling_actor_ids_raw, list | tuple)
            else ()
        )
        next_location_hint_raw = data.get("next_location_hint")
        next_location_hint = (
            next_location_hint_raw if isinstance(next_location_hint_raw, str) else None
        )
        return cls(
            encounter_id=encounter_id,
            phase=EncounterPhase(phase_raw),
            setting=setting,
            actor_ids=actor_ids,
            player_actor_id=player_actor_id,
            public_events=public_events,
            hidden_facts=hidden_facts,
            combat_turns=combat_turns,
            outcome=outcome if isinstance(outcome, str) else None,
            scene_tone=scene_tone if isinstance(scene_tone, str) else None,
            npc_presences=npc_presences,
            current_location=(
                current_location if isinstance(current_location, str) else None
            ),
            traveling_actor_ids=traveling_actor_ids,
            next_location_hint=next_location_hint,
        )


def _derive_player_actor_id(actors_raw: Mapping[object, object]) -> str:
    """Scan an old-format actors dict to find the PC actor_id."""
    for k, v in actors_raw.items():
        if isinstance(v, Mapping) and v.get("actor_type") == "pc":
            return str(k)
    return ""
