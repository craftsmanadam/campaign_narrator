"""Unit tests for campaign_state domain models."""

from __future__ import annotations

import dataclasses
from dataclasses import FrozenInstanceError

import pytest
from campaignnarrator.domain.models import (
    CampaignEvent,
    CampaignState,
    EncounterTemplate,
    Milestone,
    ModuleState,
)


def _make_campaign(**overrides: object) -> CampaignState:
    defaults: dict[str, object] = {
        "campaign_id": "c1",
        "name": "The Cursed Coast",
        "setting": "A dark coastal city.",
        "narrator_personality": "Grim and dramatic.",
        "hidden_goal": "Awaken the sea god.",
        "bbeg_name": "Malachar",
        "bbeg_description": "A lich who walks the tides.",
        "milestones": (
            Milestone(
                milestone_id="m1", title="First Blood", description="Enter the city."
            ),
        ),
        "current_milestone_index": 0,
        "starting_level": 1,
        "target_level": 5,
        "player_brief": "I want dark coastal horror.",
        "player_actor_id": "pc:player",
    }
    defaults.update(overrides)
    return CampaignState(**defaults)  # type: ignore[arg-type]


def _make_module(**overrides: object) -> ModuleState:
    defaults: dict[str, object] = {
        "module_id": "module-001",
        "campaign_id": "c1",
        "title": "The Dockside Murders",
        "summary": "Bodies wash ashore nightly.",
        "guiding_milestone_id": "m1",
    }
    defaults.update(overrides)
    return ModuleState(**defaults)  # type: ignore[arg-type]


def test_milestone_is_frozen() -> None:
    m = Milestone(milestone_id="m1", title="The Awakening", description="Evil stirs.")
    with pytest.raises(FrozenInstanceError):
        m.milestone_id = "x"  # type: ignore[misc]


def test_milestone_default_not_completed() -> None:
    m = Milestone(milestone_id="m1", title="T", description="D")
    assert m.completed is False


def test_campaign_state_is_frozen() -> None:
    campaign = _make_campaign()
    with pytest.raises(FrozenInstanceError):
        campaign.name = "other"  # type: ignore[misc]


def test_campaign_state_bbeg_actor_id_defaults_none() -> None:
    assert _make_campaign().bbeg_actor_id is None


def test_module_state_is_frozen() -> None:
    mod = _make_module()
    with pytest.raises(FrozenInstanceError):
        mod.module_id = "x"  # type: ignore[misc]


def test_module_state_completed_defaults_false() -> None:
    assert _make_module().completed is False


def test_campaign_event_is_frozen() -> None:
    evt = CampaignEvent(
        campaign_id="c1",
        event_type="encounter_completed",
        summary="The goblins were defeated.",
        timestamp="2026-04-18T12:00:00Z",
    )
    with pytest.raises(FrozenInstanceError):
        evt.campaign_id = "x"  # type: ignore[misc]


def test_campaign_event_optional_fields_default_none() -> None:
    evt = CampaignEvent(
        campaign_id="c1",
        event_type="encounter_completed",
        summary="Done.",
        timestamp="2026-04-18T12:00:00Z",
    )
    assert evt.module_id is None
    assert evt.encounter_id is None


def test_campaign_state_default_module_id_is_none() -> None:
    campaign = _make_campaign()
    assert campaign.current_module_id is None


def test_campaign_state_accepts_module_id() -> None:
    campaign = _make_campaign(current_module_id="module-001")
    assert campaign.current_module_id == "module-001"


def test_module_state_default_log_fields_are_empty() -> None:
    module = _make_module()
    assert module.completed_encounter_ids == ()
    assert module.completed_encounter_summaries == ()


def test_module_state_accepts_completed_encounters() -> None:
    module = _make_module(
        completed_encounter_ids=("module-001-enc-001",),
        completed_encounter_summaries=("The player fought a goblin at the docks.",),
    )
    assert len(module.completed_encounter_ids) == 1


def test_module_state_has_no_encounters_field() -> None:
    field_names = {f.name for f in dataclasses.fields(ModuleState)}
    assert "encounters" not in field_names
    assert "current_encounter_index" not in field_names


def test_module_state_planned_encounters_defaults_empty() -> None:
    module = _make_module()
    assert module.planned_encounters == ()
    assert module.next_encounter_index == 0


def test_module_state_accepts_planned_encounters() -> None:
    t = EncounterTemplate(
        template_id="enc-001",
        order=0,
        setting="The docks.",
        purpose="Intro.",
        npcs=(),
        prerequisites=(),
        expected_outcomes=(),
        downstream_dependencies=(),
    )
    module = _make_module(planned_encounters=(t,), next_encounter_index=0)
    assert len(module.planned_encounters) == 1
    assert module.planned_encounters[0].template_id == "enc-001"
