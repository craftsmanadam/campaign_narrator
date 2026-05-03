"""Combat models: assessment, result, and intent."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict


class CombatStatus(StrEnum):
    """Lifecycle status of a combat encounter tracked in CombatState."""

    ACTIVE = "active"
    COMPLETE = "complete"
    PLAYER_DOWN_NO_ALLIES = "player_down_no_allies"
    SAVED_AND_QUIT = "saved_and_quit"


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
