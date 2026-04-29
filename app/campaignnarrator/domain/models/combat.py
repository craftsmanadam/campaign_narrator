"""Combat models: assessment, result, and intent."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict

from .actor_registry import ActorRegistry
from .encounter_state import EncounterState


class CombatStatus(StrEnum):
    """Terminal outcome of a combat encounter from CombatOrchestrator's perspective."""

    COMPLETE = "complete"
    PLAYER_DOWN_NO_ALLIES = "player_down_no_allies"
    SAVED_AND_QUIT = "saved_and_quit"


@dataclass(frozen=True)
class CombatResult:
    """Returned by CombatOrchestrator to EncounterOrchestrator when combat ends."""

    status: CombatStatus
    final_state: EncounterState
    death_saves_remaining: int | None  # None unless status is PLAYER_DOWN_NO_ALLIES
    final_registry: ActorRegistry = field(default_factory=ActorRegistry)


class CombatOutcome(BaseModel):
    """Compact and rich description of how a combat encounter ended."""

    model_config = ConfigDict(frozen=True)
    short_description: str  # compact, for future encounter logs
    full_description: str  # rich prose shown to player


class CombatAssessment(BaseModel):
    """Narrator's assessment of whether combat should continue."""

    model_config = ConfigDict(frozen=True)
    combat_active: bool
    outcome: CombatOutcome | None  # None when combat_active is True


class CombatIntent(BaseModel):
    """Structured LLM output for a player's declared combat intent."""

    model_config = ConfigDict(frozen=True)

    intent: Literal["end_turn", "query_status", "exit_session", "combat_action"]
