"""CombatState: first-class combat tracking object owned by GameState."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from .actor_state import TurnResources
from .combat import CombatStatus
from .encounter_state import InitiativeTurn


@dataclass(frozen=True, slots=True)
class TurnOrder:
    """Ordered combat sequence with O(1) current-actor access and rotation."""

    turns: tuple[InitiativeTurn, ...] = field(default_factory=tuple)

    @property
    def current_actor_id(self) -> str:
        """Return the actor_id whose turn it is; empty string if no turns."""
        return self.turns[0].actor_id if self.turns else ""

    def end_turn(self) -> TurnOrder:
        """Rotate: move the current actor to the back of the queue."""
        if not self.turns:
            return self
        return replace(self, turns=(*self.turns[1:], self.turns[0]))

    def to_dict(self) -> list[dict[str, object]]:
        return [t.to_dict() for t in self.turns]

    @classmethod
    def from_dict(cls, data: object) -> TurnOrder:
        if not isinstance(data, list | tuple):
            return cls()
        return cls(
            turns=tuple(
                InitiativeTurn.from_dict(t) for t in data if isinstance(t, Mapping)
            )
        )


@dataclass(frozen=True, slots=True)
class CombatState:
    """First-class combat tracking: turn order, status, and active-turn resources."""

    turn_order: TurnOrder = field(default_factory=TurnOrder)
    status: CombatStatus = CombatStatus.ACTIVE
    current_turn_resources: TurnResources = field(default_factory=TurnResources)
    death_saves_remaining: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "turn_order": self.turn_order.to_dict(),
            "status": self.status.value,
            "current_turn_resources": {
                "action_available": self.current_turn_resources.action_available,
                "bonus_action_available": (
                    self.current_turn_resources.bonus_action_available
                ),
                "reaction_available": self.current_turn_resources.reaction_available,
                "movement_remaining": self.current_turn_resources.movement_remaining,
            },
            "death_saves_remaining": self.death_saves_remaining,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> CombatState:
        turn_order = TurnOrder.from_dict(data.get("turn_order", []))
        status_raw = data.get("status", CombatStatus.ACTIVE.value)
        status = (
            CombatStatus(status_raw)
            if isinstance(status_raw, str)
            else CombatStatus.ACTIVE
        )
        resources_raw = data.get("current_turn_resources", {})
        resources: TurnResources
        if isinstance(resources_raw, Mapping):
            resources = TurnResources(
                action_available=bool(resources_raw.get("action_available", True)),
                bonus_action_available=bool(
                    resources_raw.get("bonus_action_available", True)
                ),
                reaction_available=bool(resources_raw.get("reaction_available", True)),
                movement_remaining=int(resources_raw.get("movement_remaining", 0)),
            )
        else:
            resources = TurnResources()
        death_saves_raw = data.get("death_saves_remaining")
        death_saves_remaining = (
            int(death_saves_raw) if isinstance(death_saves_raw, int) else None
        )
        return cls(
            turn_order=turn_order,
            status=status,
            current_turn_resources=resources,
            death_saves_remaining=death_saves_remaining,
        )

    def with_combat_status(self, status: CombatStatus) -> CombatState:
        """Return a copy with status replaced."""
        return replace(self, status=status)

    def with_turn_order(self, turn_order: TurnOrder) -> CombatState:
        """Return a copy with turn_order replaced."""
        return replace(self, turn_order=turn_order)

    def with_death_saves_remaining(self, n: int) -> CombatState:
        """Return a copy with death_saves_remaining replaced."""
        return replace(self, death_saves_remaining=n)

    def with_current_turn_resources(self, resources: TurnResources) -> CombatState:
        """Return a copy with current_turn_resources replaced."""
        return replace(self, current_turn_resources=resources)
