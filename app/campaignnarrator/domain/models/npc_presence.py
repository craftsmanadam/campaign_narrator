"""NPC presence tracking models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum


class NpcPresenceStatus(StrEnum):
    """Scene presence state for an established NPC.

    AVAILABLE  - NPC is in scene, not yet addressed by the player.
    INTERACTED - NPC is in scene; player has spoken to them at least once.
    MENTIONED  - NPC is referenced/known but not physically present.
    DEPARTED   - NPC has left the scene. Filtered out of narrator context entirely.
    PRESENT    - Legacy alias for AVAILABLE. Accepted on deserialization of old saves.
    CONCEALED  - NPC is in scene but hidden from the player.
    """

    AVAILABLE = "available"
    INTERACTED = "interacted"
    MENTIONED = "mentioned"
    DEPARTED = "departed"
    PRESENT = "present"  # legacy alias — old saves; treated as AVAILABLE
    CONCEALED = "concealed"


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
    status: NpcPresenceStatus = NpcPresenceStatus.AVAILABLE
    interaction_summaries: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        d: dict[str, object] = {
            "actor_id": self.actor_id,
            "display_name": self.display_name,
            "description": self.description,
            "name_known": self.name_known,
            "status": self.status.value,
        }
        if self.interaction_summaries:
            d["interaction_summaries"] = list(self.interaction_summaries)
        return d

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
            status = NpcPresenceStatus.AVAILABLE
        summaries_raw = data.get("interaction_summaries", ())
        interaction_summaries: tuple[str, ...] = (
            tuple(str(s) for s in summaries_raw if isinstance(s, str))
            if isinstance(summaries_raw, list | tuple)
            else ()
        )
        return cls(
            actor_id=actor_id,
            display_name=display_name,
            description=description,
            name_known=name_known,
            status=status,
            interaction_summaries=interaction_summaries,
        )
