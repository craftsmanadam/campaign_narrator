"""NPC presence tracking models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class NpcPresenceStatus(StrEnum):
    """Scene presence state for an established NPC.

    PRESENT  - NPC is active in the scene and visible to the player.
    CONCEALED - NPC is in the scene but hidden from the player (e.g. behind a
                screen, in disguise).  The narrator may still reference them
                obliquely; the player has not interacted with them directly.
    DEPARTED - NPC has left the scene.  They must not appear in narrator
               context; the orchestrator filters them out entirely.
    """

    PRESENT = "present"
    CONCEALED = "concealed"
    DEPARTED = "departed"


@dataclass(frozen=True, slots=True)
class NpcPresence:
    """Identity anchor for an NPC established in the encounter scene.

    Prevents the narrator from inventing new named characters mid-scene.
    When name_known=False the narrator uses description; when True it uses
    display_name.
    """

    actor_id: str  # FK to EncounterState.actors
    display_name: str  # Canonical name used when name_known=True
    description: str  # Narrative label used when name_known=False ("the innkeeper")
    name_known: bool  # Has the player learned this NPC's name?
    status: NpcPresenceStatus = NpcPresenceStatus.PRESENT

    def to_dict(self) -> dict[str, object]:
        return {
            "actor_id": self.actor_id,
            "display_name": self.display_name,
            "description": self.description,
            "name_known": self.name_known,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> NpcPresence:
        actor_id = data.get("actor_id")
        display_name = data.get("display_name")
        description = data.get("description")
        name_known = data.get("name_known")
        if not (
            isinstance(actor_id, str)
            and isinstance(display_name, str)
            and isinstance(description, str)
            and isinstance(name_known, bool)
        ):
            raise TypeError("NpcPresence: missing or invalid required fields")  # noqa: TRY003
        # Backward compatibility: old saves use visible: bool.
        # visible=True → PRESENT; visible=False → CONCEALED.
        # DEPARTED had no representation in old saves and cannot appear here.
        raw_status = data.get("status")
        if isinstance(raw_status, str):
            try:
                status = NpcPresenceStatus(raw_status)
            except ValueError as exc:
                msg = f"NpcPresence: invalid status value {raw_status!r}"
                raise TypeError(msg) from exc
        elif "visible" in data:
            status = (
                NpcPresenceStatus.PRESENT
                if data["visible"]
                else NpcPresenceStatus.CONCEALED
            )
        else:
            status = NpcPresenceStatus.PRESENT
        return cls(
            actor_id=actor_id,
            display_name=display_name,
            description=description,
            name_known=name_known,
            status=status,
        )
