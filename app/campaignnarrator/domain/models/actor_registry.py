"""ActorRegistry and EncounterTransition models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from .actor_state import ActorState
from .npc_presence import NpcPresence


@dataclass(frozen=True, slots=True)
class ActorRegistry:
    """Immutable registry mapping actor_id to ActorState.

    Provides copy-on-write mutation via with_actor and with_actors.
    The actors mapping is always exposed as a MappingProxyType to
    prevent external mutation.
    """

    actors: Mapping[str, ActorState] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Freeze actors into a MappingProxyType to prevent external mutation."""
        object.__setattr__(self, "actors", MappingProxyType(dict(self.actors)))

    def with_actor(self, actor: ActorState) -> ActorRegistry:
        """Return a new ActorRegistry with actor added or replaced."""
        return ActorRegistry(actors={**self.actors, actor.actor_id: actor})

    def with_actors(self, actors: Mapping[str, ActorState]) -> ActorRegistry:
        """Return a new ActorRegistry merging existing actors with the provided mapping.

        Later entries in actors win over existing ones.
        """
        return ActorRegistry(actors={**self.actors, **actors})

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-compatible dict."""
        return {"actors": {k: v.to_dict() for k, v in self.actors.items()}}

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ActorRegistry:
        """Restore from to_dict(). Returns empty registry on invalid input."""
        actors_raw = data.get("actors", {})
        if not isinstance(actors_raw, Mapping):
            return cls()
        return cls(
            actors={
                str(k): ActorState.from_dict(v)
                for k, v in actors_raw.items()
                if isinstance(v, Mapping)
            }
        )


@dataclass(frozen=True, slots=True)
class EncounterTransition:
    """Call-chain value object — not persisted.

    Carries traveling NPC state from _archive_encounter to _instantiate.
    The traveling_actors mapping is always exposed as a MappingProxyType
    to prevent external mutation.
    """

    from_encounter_id: str
    next_location_hint: str | None
    traveling_actor_ids: tuple[str, ...]
    traveling_actors: Mapping[str, ActorState]
    traveling_presences: tuple[NpcPresence, ...]

    def __post_init__(self) -> None:
        """Freeze traveling_actors into a MappingProxyType."""
        object.__setattr__(
            self, "traveling_actors", MappingProxyType(dict(self.traveling_actors))
        )
