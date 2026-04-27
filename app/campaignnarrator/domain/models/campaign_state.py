"""Campaign and module state models."""

from __future__ import annotations

from dataclasses import dataclass, field

from .encounter_template import EncounterTemplate


@dataclass(frozen=True, slots=True)
class Milestone:
    """A campaign story anchor point. Narrator-only — never shown to the player."""

    milestone_id: str
    title: str
    description: str
    completed: bool = False


@dataclass(frozen=True, slots=True)
class CampaignState:
    """Top-level campaign definition.

    Narrator-only fields must never appear in player-facing prompts.
    """

    campaign_id: str
    name: str
    setting: str
    narrator_personality: str
    # --- Narrator-only fields (never send to player-facing prompts) ---
    hidden_goal: str
    bbeg_name: str
    bbeg_description: str
    milestones: tuple[Milestone, ...]
    # --- Progress tracking ---
    current_milestone_index: int
    starting_level: int
    target_level: int
    # --- Player inputs ---
    player_brief: str
    player_actor_id: str
    bbeg_actor_id: str | None = None
    current_module_id: str | None = None


@dataclass(frozen=True, slots=True)
class ModuleState:
    """One story arc within a campaign. Generated lazily as play progresses."""

    module_id: str
    campaign_id: str
    title: str
    summary: str
    guiding_milestone_id: str
    completed_encounter_ids: tuple[str, ...] = ()
    completed_encounter_summaries: tuple[str, ...] = ()
    completed: bool = False
    planned_encounters: tuple[EncounterTemplate, ...] = ()
    next_encounter_index: int = 0


@dataclass(frozen=True, slots=True)
class CampaignEvent:
    """A summarised story event appended to the campaign event log."""

    campaign_id: str
    # encounter_completed | milestone_reached | notable_moment
    # player_downed | npc_death | module_completed
    event_type: str
    summary: str  # narrator-written, 1-3 sentences
    timestamp: str  # ISO 8601
    module_id: str | None = None
    encounter_id: str | None = None
