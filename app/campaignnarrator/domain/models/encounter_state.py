"""Encounter state, phase, and game state models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from types import MappingProxyType

from .actor_registry import ActorRegistry
from .actor_state import ActorState, ActorType
from .campaign_state import CampaignState, ModuleState
from .npc_presence import NpcPresence, NpcPresenceStatus

# Statuses that mean the NPC is physically in the scene.
_ACTIVE_NPC_STATUSES = frozenset(
    {
        NpcPresenceStatus.AVAILABLE,
        NpcPresenceStatus.PRESENT,
        NpcPresenceStatus.INTERACTED,
        NpcPresenceStatus.CONCEALED,
    }
)


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
            raise TypeError("InitiativeTurn: actor_id must be str")  # noqa: TRY003
        if type(roll) is not int:
            raise TypeError("InitiativeTurn: initiative_roll must be int")  # noqa: TRY003
        return cls(actor_id=actor_id, initiative_roll=roll)


@dataclass(frozen=True, slots=True)
class EncounterState:
    """Canonical state for an in-progress encounter."""

    encounter_id: str
    phase: EncounterPhase
    setting: str
    actors: Mapping[str, ActorState]
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
        are included. When populated, only PCs and actively present NPCs appear.
        MENTIONED and DEPARTED NPCs are excluded.
        """
        if not self.npc_presences:
            return tuple(actor.narrative_summary() for actor in self.actors.values())
        present_ids = {
            p.actor_id for p in self.npc_presences if p.status in _ACTIVE_NPC_STATUSES
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
            "traveling_actor_ids": list(self.traveling_actor_ids),
            "next_location_hint": self.next_location_hint,
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
            traveling_actor_ids=traveling_actor_ids,
            next_location_hint=next_location_hint,
        )


@dataclass(frozen=True)
class GameState:
    """Top-level game state: player + optional campaign/module/encounter."""

    player: ActorState
    campaign: CampaignState | None = None
    module: ModuleState | None = None
    encounter: EncounterState | None = None
    actor_registry: ActorRegistry = field(default_factory=ActorRegistry)


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
