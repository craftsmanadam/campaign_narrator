"""Encounter planning templates: EncounterNpc and EncounterTemplate."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


class EncounterNpc(BaseModel):
    """Planning-time NPC definition.

    Single source of truth for ActorState and NpcPresence.
    Assigned by EncounterPlannerAgent at planning time.
    template_npc_id must be unique within a module (not just within an encounter).
    """

    model_config = ConfigDict(frozen=True)

    template_npc_id: str
    display_name: str
    role: str
    description: str
    monster_name: str | None
    stat_source: Literal["monster_compendium", "simple_npc"]
    cr: float
    name_known: bool = False

    @field_validator("cr", mode="before")
    @classmethod
    def _parse_cr(cls, v: object) -> float:
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            if "/" in v:
                num, den = v.split("/")
                return int(num) / int(den)
            return float(v)
        raise ValueError(f"Cannot parse CR: {v!r}")  # noqa: TRY003


class EncounterTemplate(BaseModel):
    """Narrative skeleton for one planned encounter."""

    model_config = ConfigDict(frozen=True)

    template_id: str
    order: int
    setting: str
    purpose: str
    scene_tone: str | None = None
    npcs: tuple[EncounterNpc, ...]
    prerequisites: tuple[str, ...]
    expected_outcomes: tuple[str, ...]
    downstream_dependencies: tuple[str, ...]
