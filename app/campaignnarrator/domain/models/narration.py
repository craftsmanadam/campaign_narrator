"""Narration frame and response models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from .encounter_state import EncounterPhase
from .npc_presence import NpcPresence


@dataclass(frozen=True, slots=True)
class NarrationFrame:
    """Public context that can be narrated to the player."""

    purpose: str
    phase: EncounterPhase
    setting: str
    public_actor_summaries: tuple[str, ...]
    recent_public_events: tuple[str, ...]
    resolved_outcomes: tuple[str, ...]
    allowed_disclosures: tuple[str, ...]
    tone_guidance: str | None = None
    player_action: str | None = None
    prior_narrative_context: str = ""
    compendium_context: tuple[str, ...] = field(default_factory=tuple)
    npc_presences: tuple[NpcPresence, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class Narration:
    """The text that should be spoken to the user."""

    text: str
    audience: str | None = None
    scene_tone: str | None = None
    current_location: str | None = None
    encounter_complete: bool = False
    completion_reason: str | None = None
    next_location_hint: str | None = None


class _MissingCompletionHint(ValueError):
    """Raised when encounter_complete is True but next_location_hint is absent."""

    def __init__(self) -> None:
        super().__init__("next_location_hint required when encounter_complete=True")


class _MissingCompletionReason(ValueError):
    """Raised when encounter_complete is True but completion_reason is absent."""

    def __init__(self) -> None:
        super().__init__("completion_reason required when encounter_complete=True")


class NarrationResponse(BaseModel):
    """Structured LLM output for all non-scene-opening narrations."""

    model_config = ConfigDict(frozen=True)

    text: str
    current_location: str
    encounter_complete: bool = False
    completion_reason: str | None = None
    next_location_hint: str | None = None

    @model_validator(mode="after")
    def _validate_completion_fields(self) -> Self:
        if self.encounter_complete and not self.completion_reason:
            raise _MissingCompletionReason()
        if self.encounter_complete and not self.next_location_hint:
            raise _MissingCompletionHint()
        return self


class SceneOpeningResponse(BaseModel):
    """Structured LLM output for scene opening narration."""

    model_config = ConfigDict(frozen=True)

    text: str
    scene_tone: str
