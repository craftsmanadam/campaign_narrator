"""Unit tests for CampaignRepository."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from campaignnarrator.domain.models import CampaignEvent, CampaignState, Milestone
from campaignnarrator.repositories.campaign_repository import CampaignRepository

_EXPECTED_MILESTONE_COUNT = 3
_EXPECTED_EVENT_COUNT = 2


def _make_campaign() -> CampaignState:
    return CampaignState(
        campaign_id="c1",
        name="The Cursed Coast",
        setting="A dark coastal city plagued by shadows.",
        narrator_personality="Grim and methodical.",
        hidden_goal="Awaken the drowned god.",
        bbeg_name="Malachar",
        bbeg_description="A lich who walks the tides.",
        milestones=(
            Milestone(
                milestone_id="m1", title="First Blood", description="Enter the city."
            ),
            Milestone(
                milestone_id="m2", title="The Truth", description="Uncover the cult."
            ),
            Milestone(
                milestone_id="m3", title="Reckoning", description="Confront Malachar."
            ),
        ),
        current_milestone_index=0,
        starting_level=1,
        target_level=5,
        player_brief="Dark coastal horror with undead.",
        player_actor_id="pc:player",
    )


def test_exists_returns_false_when_no_file(tmp_path: Path) -> None:
    repo = CampaignRepository(tmp_path)
    assert repo.exists() is False


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    repo = CampaignRepository(tmp_path)
    campaign = _make_campaign()
    repo.save(campaign)
    loaded = repo.load()
    assert loaded is not None
    assert loaded.campaign_id == "c1"
    assert loaded.name == "The Cursed Coast"
    assert loaded.hidden_goal == "Awaken the drowned god."
    assert loaded.bbeg_name == "Malachar"
    assert len(loaded.milestones) == _EXPECTED_MILESTONE_COUNT
    assert loaded.milestones[0].milestone_id == "m1"
    assert loaded.milestones[0].completed is False
    assert loaded.bbeg_actor_id is None


def test_exists_returns_true_after_save(tmp_path: Path) -> None:
    repo = CampaignRepository(tmp_path)
    repo.save(_make_campaign())
    assert repo.exists() is True


def test_load_returns_none_when_no_file(tmp_path: Path) -> None:
    repo = CampaignRepository(tmp_path)
    assert repo.load() is None


def test_save_preserves_bbeg_actor_id(tmp_path: Path) -> None:
    repo = CampaignRepository(tmp_path)
    campaign = replace(_make_campaign(), bbeg_actor_id="npc:malachar")
    repo.save(campaign)
    loaded = repo.load()
    assert loaded is not None
    assert loaded.bbeg_actor_id == "npc:malachar"


def test_append_and_load_events(tmp_path: Path) -> None:
    repo = CampaignRepository(tmp_path)
    evt = CampaignEvent(
        campaign_id="c1",
        event_type="encounter_completed",
        summary="The goblins were routed.",
        timestamp="2026-04-18T12:00:00Z",
        module_id="module-001",
        encounter_id="enc-001",
    )
    repo.append_event(evt)
    repo.append_event(evt)
    events = repo.load_events("c1")
    assert len(events) == _EXPECTED_EVENT_COUNT
    assert events[0].event_type == "encounter_completed"
    assert events[0].module_id == "module-001"


def test_load_events_returns_empty_when_no_log(tmp_path: Path) -> None:
    repo = CampaignRepository(tmp_path)
    assert repo.load_events("c1") == []
