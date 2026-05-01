"""Campaign and module state models."""

from __future__ import annotations

from dataclasses import dataclass, replace

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

    def advance_module(self, *, module_id: str, milestone_index: int) -> CampaignState:
        """Return a copy with current_module_id and current_milestone_index updated."""
        return replace(
            self,
            current_module_id=module_id,
            current_milestone_index=milestone_index,
        )

    def with_bbeg_actor_id(self, actor_id: str) -> CampaignState:
        """Return a copy with bbeg_actor_id set."""
        return replace(self, bbeg_actor_id=actor_id)


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

    def record_completed_encounter(
        self, encounter_id: str, summary: str
    ) -> ModuleState:
        """Return a copy with encounter appended to history and index incremented."""
        new_ids = (*self.completed_encounter_ids, encounter_id)
        new_summaries = (*self.completed_encounter_summaries, summary)
        return replace(
            self,
            completed_encounter_ids=new_ids,
            completed_encounter_summaries=new_summaries,
            next_encounter_index=self.next_encounter_index + 1,
        )

    def with_planned_encounters(
        self, encounters: tuple[EncounterTemplate, ...]
    ) -> ModuleState:
        """Return a copy with planned_encounters replaced."""
        return replace(self, planned_encounters=encounters)

    def with_next_encounter_index(self, index: int) -> ModuleState:
        """Return a copy with next_encounter_index set."""
        return replace(self, next_encounter_index=index)

    def mark_completed(self) -> ModuleState:
        """Return a copy with completed set to True."""
        return replace(self, completed=True)


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
