"""Unit tests for updated CampaignState and ModuleState models."""

from __future__ import annotations

import dataclasses
import tempfile

from campaignnarrator.domain.models import (
    CampaignState,
    Milestone,
    ModuleState,
    NextEncounterPlan,
)
from campaignnarrator.repositories.campaign_repository import CampaignRepository
from campaignnarrator.repositories.module_repository import ModuleRepository


def _make_campaign(**overrides: object) -> CampaignState:
    defaults = {
        "campaign_id": "c-1",
        "name": "Test Campaign",
        "setting": "A dark forest.",
        "narrator_personality": "Grim.",
        "hidden_goal": "Find the lich.",
        "bbeg_name": "Vexar",
        "bbeg_description": "Ancient evil.",
        "milestones": (
            Milestone(milestone_id="m1", title="First Blood", description="Survive."),
        ),
        "current_milestone_index": 0,
        "starting_level": 1,
        "target_level": 5,
        "player_brief": "Dark fantasy.",
        "player_actor_id": "pc:player",
    }
    defaults.update(overrides)
    return CampaignState(**defaults)  # type: ignore[arg-type]


def test_campaign_state_default_module_id_is_none() -> None:
    campaign = _make_campaign()
    assert campaign.current_module_id is None


def test_campaign_state_accepts_module_id() -> None:
    campaign = _make_campaign(current_module_id="module-001")
    assert campaign.current_module_id == "module-001"


def test_campaign_repository_round_trips_current_module_id() -> None:
    campaign = _make_campaign(current_module_id="module-002")
    with tempfile.TemporaryDirectory() as tmp:
        repo = CampaignRepository(tmp)
        repo.save(campaign)
        loaded = repo.load()
    assert loaded is not None
    assert loaded.current_module_id == "module-002"


def test_campaign_repository_round_trips_null_module_id() -> None:
    campaign = _make_campaign()
    with tempfile.TemporaryDirectory() as tmp:
        repo = CampaignRepository(tmp)
        repo.save(campaign)
        loaded = repo.load()
    assert loaded is not None
    assert loaded.current_module_id is None


def _make_module(**overrides: object) -> ModuleState:
    defaults = {
        "module_id": "module-001",
        "campaign_id": "c-1",
        "title": "The Dockside Murders",
        "summary": "Bodies wash ashore.",
        "guiding_milestone_id": "m1",
    }
    defaults.update(overrides)
    return ModuleState(**defaults)  # type: ignore[arg-type]


def test_module_state_default_log_fields_are_empty() -> None:
    module = _make_module()
    assert module.completed_encounter_ids == ()
    assert module.completed_encounter_summaries == ()
    assert module.next_encounter_seed is None


def test_module_state_accepts_completed_encounters() -> None:
    module = _make_module(
        completed_encounter_ids=("module-001-enc-001",),
        completed_encounter_summaries=("The player fought a goblin at the docks.",),
        next_encounter_seed="A shadowy figure waits near the warehouse.",
    )
    assert len(module.completed_encounter_ids) == 1
    assert module.next_encounter_seed == "A shadowy figure waits near the warehouse."


def test_module_state_has_no_encounters_field() -> None:
    field_names = {f.name for f in dataclasses.fields(ModuleState)}
    assert "encounters" not in field_names
    assert "current_encounter_index" not in field_names


def test_module_repository_round_trips_new_fields() -> None:
    module = _make_module(
        completed_encounter_ids=("module-001-enc-001",),
        completed_encounter_summaries=("The goblin fell at the docks.",),
        next_encounter_seed="Shadows move near the warehouse.",
        completed=False,
    )
    with tempfile.TemporaryDirectory() as tmp:
        repo = ModuleRepository(tmp)
        repo.save(module)
        loaded = repo.load("module-001")
    assert loaded is not None
    assert loaded.completed_encounter_ids == ("module-001-enc-001",)
    assert loaded.completed_encounter_summaries == ("The goblin fell at the docks.",)
    assert loaded.next_encounter_seed == "Shadows move near the warehouse."


def test_module_repository_round_trips_empty_log() -> None:
    module = _make_module()
    with tempfile.TemporaryDirectory() as tmp:
        repo = ModuleRepository(tmp)
        repo.save(module)
        loaded = repo.load("module-001")
    assert loaded is not None
    assert loaded.completed_encounter_ids == ()
    assert loaded.next_encounter_seed is None


def test_next_encounter_plan_fields() -> None:
    plan = NextEncounterPlan(seed="The docks at midnight.", milestone_achieved=False)
    assert plan.seed == "The docks at midnight."
    assert plan.milestone_achieved is False


def test_next_encounter_plan_milestone_achieved() -> None:
    plan = NextEncounterPlan(seed="", milestone_achieved=True)
    assert plan.milestone_achieved is True
