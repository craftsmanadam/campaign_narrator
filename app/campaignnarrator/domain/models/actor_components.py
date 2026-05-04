"""Actor component models: resources, inventory, weapons, feats."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class RecoveryPeriod(StrEnum):
    """When a resource or item charge replenishes."""

    TURN = "turn"  # resets at start of actor's turn
    SHORT_REST = "short_rest"
    LONG_REST = "long_rest"
    DAY = "day"  # items only — "regains charges at dawn"


@dataclass(frozen=True, slots=True)
class FeatState:
    """A feat carried by an actor, with LLM-readable effect text."""

    name: str
    effect_summary: str  # Injected verbatim into Rules Agent context
    reference: str | None  # e.g. "DND.SRD.Wiki-0.5.2/Feats.md#Alert"
    per_turn_uses: int | None  # None = passive; int = resource reset each turn

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-compatible dict."""
        return {
            "name": self.name,
            "effect_summary": self.effect_summary,
            "reference": self.reference,
            "per_turn_uses": self.per_turn_uses,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> FeatState:
        """Restore from to_dict(). Missing keys fall back to empty strings."""
        name = data.get("name", "")
        effect_summary = data.get("effect_summary", "")
        reference = data.get("reference")
        per_turn_uses_raw = data.get("per_turn_uses")
        return cls(
            name=str(name),
            effect_summary=str(effect_summary),
            reference=reference if isinstance(reference, str) else None,
            per_turn_uses=(
                int(per_turn_uses_raw) if per_turn_uses_raw is not None else None
            ),
        )


@dataclass(frozen=True, slots=True)
class WeaponState:
    """A weapon with fully pre-computed attack and damage values."""

    name: str
    attack_bonus: int  # proficiency + ability mod (+ magic if any)
    damage_dice: str  # e.g. "1d8", "2d6"
    damage_bonus: int  # ability mod (+ magic if any)
    damage_type: str  # "slashing", "piercing", "bludgeoning", etc.
    properties: tuple[str, ...]  # e.g. ("versatile (1d10)", "finesse")

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-compatible dict."""
        return {
            "name": self.name,
            "attack_bonus": self.attack_bonus,
            "damage_dice": self.damage_dice,
            "damage_bonus": self.damage_bonus,
            "damage_type": self.damage_type,
            "properties": list(self.properties),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> WeaponState:
        """Restore from to_dict(). Missing keys fall back to safe defaults."""
        return cls(
            name=str(data.get("name", "")),
            attack_bonus=int(data.get("attack_bonus", 0)),
            damage_dice=str(data.get("damage_dice", "1d4")),
            damage_bonus=int(data.get("damage_bonus", 0)),
            damage_type=str(data.get("damage_type", "bludgeoning")),
            properties=tuple(
                str(p) for p in data.get("properties", ()) if isinstance(p, str)
            ),
        )


@dataclass(frozen=True, slots=True)
class ResourceState:
    """A character class resource with current/max tracking and recovery metadata."""

    resource: str  # e.g. "second_wind", "action_surge"
    current: int
    max: int
    recovers_after: RecoveryPeriod
    reference: str | None = None  # e.g. "class_features.json#second-wind"

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-compatible dict."""
        return {
            "resource": self.resource,
            "current": self.current,
            "max": self.max,
            "recovers_after": self.recovers_after.value,
            "reference": self.reference,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ResourceState:
        """Restore from to_dict(). Defaults recovers_after to long_rest."""
        recovers_raw = data.get("recovers_after", "long_rest")
        return cls(
            resource=str(data.get("resource", "")),
            current=int(data.get("current", 0)),
            max=int(data.get("max", 0)),
            recovers_after=RecoveryPeriod(recovers_raw),
            reference=(
                data.get("reference")
                if isinstance(data.get("reference"), str)
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class InventoryItem:
    """A physical item carried by an actor."""

    item_id: str  # unique within actor inventory, e.g. "potion-1", "rope-1"
    item: str  # display name
    count: int
    charges: int | None = None  # current charges (e.g. wand)
    max_charges: int | None = None
    recovers_after: RecoveryPeriod | None = None  # None for consumables/mundane items
    reference: str | None = None  # None for narrative-only items

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-compatible dict."""
        return {
            "item_id": self.item_id,
            "item": self.item,
            "count": self.count,
            "charges": self.charges,
            "max_charges": self.max_charges,
            "recovers_after": (
                self.recovers_after.value if self.recovers_after is not None else None
            ),
            "reference": self.reference,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> InventoryItem:
        """Restore from to_dict(). Optional fields default to None."""
        recovers_raw = data.get("recovers_after")
        charges_raw = data.get("charges")
        max_charges_raw = data.get("max_charges")
        return cls(
            item_id=str(data.get("item_id", "")),
            item=str(data.get("item", "")),
            count=int(data.get("count", 0)),
            charges=int(charges_raw) if charges_raw is not None else None,
            max_charges=int(max_charges_raw) if max_charges_raw is not None else None,
            recovers_after=(
                RecoveryPeriod(recovers_raw) if isinstance(recovers_raw, str) else None
            ),
            reference=(
                data.get("reference")
                if isinstance(data.get("reference"), str)
                else None
            ),
        )
