"""Top-level game state and planner result types."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from .actor_registry import ActorRegistry
from .campaign_state import CampaignState, Milestone, ModuleState
from .encounter_state import EncounterState
from .encounter_template import EncounterTemplate


class _InvalidCampaignSeedError(TypeError):
    """Raised when a campaign seed is not a valid mapping."""


class _InvalidMilestoneSeedError(TypeError):
    """Raised when a milestone seed is not a valid mapping."""


class _InvalidModuleSeedError(TypeError):
    """Raised when a module seed is not a valid mapping."""


@dataclass(frozen=True)
class GameState:
    """Top-level game state. Player lives in actor_registry."""

    campaign: CampaignState | None = None
    module: ModuleState | None = None
    encounter: EncounterState | None = None
    actor_registry: ActorRegistry = field(default_factory=ActorRegistry)

    def to_json(self) -> dict[str, object]:
        """Serialise to a JSON-compatible dict.

        Faithfully serialises whatever actor_registry is present. The caller
        is responsible for stripping the player actor before writing to disk
        if the player is stored separately.
        """
        return {
            "campaign": _campaign_to_json(self.campaign)
            if self.campaign is not None
            else None,
            "module": _module_to_json(self.module) if self.module is not None else None,
            "encounter": self.encounter.to_dict()
            if self.encounter is not None
            else None,
            "actor_registry": self.actor_registry.to_dict(),
        }

    @classmethod
    def from_json(cls, raw: dict[str, object]) -> GameState:
        """Deserialise from a JSON-compatible dict.

        Faithfully reconstructs whatever was serialised. The caller is
        responsible for merging the player back into actor_registry if the
        player was stored separately.
        """
        campaign = _campaign_from_seed(raw["campaign"]) if raw.get("campaign") else None
        module = _module_from_seed(raw["module"]) if raw.get("module") else None
        encounter = (
            EncounterState.from_dict(raw["encounter"]) if raw.get("encounter") else None
        )
        actor_registry = ActorRegistry.from_dict(
            raw.get("actor_registry") or {"actors": {}}
        )
        return cls(
            campaign=campaign,
            module=module,
            encounter=encounter,
            actor_registry=actor_registry,
        )


@dataclass(frozen=True)
class EncounterReady:
    """Returned by EncounterPlannerOrchestrator.prepare() on success.

    module may differ from the input module if recovery occurred.
    Callers must use EncounterReady.module, not their local reference.
    """

    encounter_state: EncounterState
    module: ModuleState


@dataclass(frozen=True)
class MilestoneAchieved:
    """Returned by EncounterPlannerOrchestrator.prepare() when milestone is complete.

    Signals ModuleOrchestrator to advance to the next module.
    """


# --- Campaign serialisation helpers ---


def _campaign_to_json(c: CampaignState) -> dict[str, object]:
    return {
        "campaign_id": c.campaign_id,
        "name": c.name,
        "setting": c.setting,
        "narrator_personality": c.narrator_personality,
        "hidden_goal": c.hidden_goal,
        "bbeg_name": c.bbeg_name,
        "bbeg_description": c.bbeg_description,
        "milestones": [_milestone_to_json(m) for m in c.milestones],
        "current_milestone_index": c.current_milestone_index,
        "starting_level": c.starting_level,
        "target_level": c.target_level,
        "player_brief": c.player_brief,
        "player_actor_id": c.player_actor_id,
        "bbeg_actor_id": c.bbeg_actor_id,
        "current_module_id": c.current_module_id,
    }


def _milestone_to_json(m: Milestone) -> dict[str, object]:
    return {
        "milestone_id": m.milestone_id,
        "title": m.title,
        "description": m.description,
        "completed": m.completed,
    }


def _campaign_from_seed(seed: object) -> CampaignState:
    if not isinstance(seed, Mapping):
        raise _InvalidCampaignSeedError()
    return CampaignState(
        campaign_id=str(seed["campaign_id"]),
        name=str(seed["name"]),
        setting=str(seed["setting"]),
        narrator_personality=str(seed["narrator_personality"]),
        hidden_goal=str(seed["hidden_goal"]),
        bbeg_name=str(seed["bbeg_name"]),
        bbeg_description=str(seed["bbeg_description"]),
        milestones=tuple(_milestone_from_seed(m) for m in seed.get("milestones", [])),
        current_milestone_index=int(seed["current_milestone_index"]),
        starting_level=int(seed["starting_level"]),
        target_level=int(seed["target_level"]),
        player_brief=str(seed["player_brief"]),
        player_actor_id=str(seed["player_actor_id"]),
        bbeg_actor_id=(
            str(seed["bbeg_actor_id"])
            if seed.get("bbeg_actor_id") is not None
            else None
        ),
        current_module_id=(
            str(seed["current_module_id"])
            if seed.get("current_module_id") is not None
            else None
        ),
    )


def _milestone_from_seed(seed: object) -> Milestone:
    if not isinstance(seed, Mapping):
        raise _InvalidMilestoneSeedError()
    return Milestone(
        milestone_id=str(seed["milestone_id"]),
        title=str(seed["title"]),
        description=str(seed["description"]),
        completed=bool(seed.get("completed", False)),
    )


# --- Module serialisation helpers ---


def _module_to_json(m: ModuleState) -> dict[str, object]:
    return {
        "module_id": m.module_id,
        "campaign_id": m.campaign_id,
        "title": m.title,
        "summary": m.summary,
        "guiding_milestone_id": m.guiding_milestone_id,
        "completed_encounter_ids": list(m.completed_encounter_ids),
        "completed_encounter_summaries": list(m.completed_encounter_summaries),
        "completed": m.completed,
        "planned_encounters": [t.model_dump() for t in m.planned_encounters],
        "next_encounter_index": m.next_encounter_index,
    }


def _module_from_seed(seed: object) -> ModuleState:
    if not isinstance(seed, Mapping):
        raise _InvalidModuleSeedError()
    raw = dict(seed)
    raw.pop("next_encounter_seed", None)
    planned_raw = raw.pop("planned_encounters", [])
    return ModuleState(
        module_id=str(raw["module_id"]),
        campaign_id=str(raw["campaign_id"]),
        title=str(raw["title"]),
        summary=str(raw["summary"]),
        guiding_milestone_id=str(raw["guiding_milestone_id"]),
        completed_encounter_ids=tuple(
            str(e) for e in raw.get("completed_encounter_ids", [])
        ),
        completed_encounter_summaries=tuple(
            str(s) for s in raw.get("completed_encounter_summaries", [])
        ),
        completed=bool(raw.get("completed", False)),
        planned_encounters=tuple(
            EncounterTemplate.model_validate(t) for t in planned_raw
        ),
        next_encounter_index=int(raw.get("next_encounter_index", 0)),
    )
