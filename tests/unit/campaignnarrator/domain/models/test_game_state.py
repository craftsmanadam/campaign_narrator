"""Unit tests for GameState.to_json(), GameState.from_json(), and GameState methods."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from campaignnarrator.domain.models import (
    ActorRegistry,
    CampaignState,
    EncounterPhase,
    EncounterState,
    GameState,
    Milestone,
    ModuleState,
)

from tests.fixtures.fighter_talia import TALIA
from tests.fixtures.goblin_scout import make_goblin_scout


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
        "title": "Dockside Shadows",
        "summary": "Investigate the disappearances.",
        "guiding_milestone_id": "m1",
    }
    defaults.update(overrides)
    return ModuleState(**defaults)  # type: ignore[arg-type]


# --- to_json() ---


def test_to_json_campaign_is_none_when_not_set() -> None:
    gs = GameState()
    assert gs.to_json()["campaign"] is None


def test_to_json_module_is_none_when_not_set() -> None:
    gs = GameState()
    assert gs.to_json()["module"] is None


def test_to_json_encounter_is_none_when_not_set() -> None:
    gs = GameState()
    assert gs.to_json()["encounter"] is None


def test_to_json_actor_registry_present_when_empty() -> None:
    gs = GameState()
    blob = gs.to_json()
    assert "actor_registry" in blob


def test_to_json_campaign_fields_serialised() -> None:
    gs = GameState(campaign=_make_campaign())
    blob = gs.to_json()
    assert blob["campaign"] is not None
    assert blob["campaign"]["campaign_id"] == "c1"  # type: ignore[index]
    assert blob["campaign"]["name"] == "The Cursed Coast"  # type: ignore[index]


def test_to_json_campaign_milestones_serialised() -> None:
    gs = GameState(campaign=_make_campaign())
    blob = gs.to_json()
    milestones = blob["campaign"]["milestones"]  # type: ignore[index]
    assert len(milestones) == 1
    assert milestones[0]["milestone_id"] == "m1"
    assert milestones[0]["title"] == "First Blood"


def test_to_json_module_fields_serialised() -> None:
    gs = GameState(module=_make_module())
    blob = gs.to_json()
    assert blob["module"] is not None
    assert blob["module"]["module_id"] == "module-001"  # type: ignore[index]
    assert blob["module"]["title"] == "Dockside Shadows"  # type: ignore[index]


def test_to_json_encounter_serialised_via_to_dict() -> None:
    encounter = MagicMock(spec=EncounterState)
    encounter.to_dict.return_value = {"encounter_id": "enc-1"}
    gs = GameState(encounter=encounter)
    blob = gs.to_json()
    assert blob["encounter"] == {"encounter_id": "enc-1"}
    encounter.to_dict.assert_called_once()


def test_to_json_actor_registry_includes_all_actors() -> None:
    goblin = make_goblin_scout("npc:goblin", "Goblin Scout")
    registry = ActorRegistry(actors={TALIA.actor_id: TALIA, goblin.actor_id: goblin})
    gs = GameState(actor_registry=registry)
    blob = gs.to_json()
    actors = blob["actor_registry"]["actors"]  # type: ignore[index]
    assert TALIA.actor_id in actors
    assert goblin.actor_id in actors


def test_to_json_returns_dict() -> None:
    gs = GameState(campaign=_make_campaign(), module=_make_module())
    assert isinstance(gs.to_json(), dict)


# --- from_json() ---


def test_from_json_campaign_none_when_absent() -> None:
    gs = GameState.from_json({"actor_registry": {"actors": {}}})
    assert gs.campaign is None


def test_from_json_module_none_when_absent() -> None:
    gs = GameState.from_json({"actor_registry": {"actors": {}}})
    assert gs.module is None


def test_from_json_encounter_none_when_absent() -> None:
    gs = GameState.from_json({"actor_registry": {"actors": {}}})
    assert gs.encounter is None


def test_from_json_empty_registry_when_actor_registry_absent() -> None:
    gs = GameState.from_json({})
    assert isinstance(gs.actor_registry, ActorRegistry)


def test_from_json_campaign_fields_round_trip() -> None:
    original = _make_campaign()
    blob = GameState(campaign=original).to_json()
    gs = GameState.from_json(blob)
    assert gs.campaign is not None
    assert gs.campaign.campaign_id == "c1"
    assert gs.campaign.name == "The Cursed Coast"
    assert gs.campaign.hidden_goal == "Awaken the sea god."


def test_from_json_milestone_fields_round_trip() -> None:
    original = _make_campaign()
    blob = GameState(campaign=original).to_json()
    gs = GameState.from_json(blob)
    assert gs.campaign is not None
    assert len(gs.campaign.milestones) == 1
    assert gs.campaign.milestones[0].milestone_id == "m1"
    assert gs.campaign.milestones[0].title == "First Blood"


def test_from_json_module_fields_round_trip() -> None:
    original = _make_module()
    blob = GameState(module=original).to_json()
    gs = GameState.from_json(blob)
    assert gs.module is not None
    assert gs.module.module_id == "module-001"
    assert gs.module.title == "Dockside Shadows"


def test_from_json_actor_registry_round_trip() -> None:
    goblin = make_goblin_scout("npc:goblin", "Goblin Scout")
    registry = ActorRegistry(actors={goblin.actor_id: goblin})
    blob = GameState(actor_registry=registry).to_json()
    gs = GameState.from_json(blob)
    assert goblin.actor_id in gs.actor_registry.actors


def test_from_json_returns_game_state() -> None:
    gs = GameState.from_json({})
    assert isinstance(gs, GameState)


# --- round-trip ---


def test_round_trip_with_all_fields() -> None:
    goblin = make_goblin_scout("npc:goblin", "Goblin Scout")
    registry = ActorRegistry(actors={goblin.actor_id: goblin})
    original = GameState(
        campaign=_make_campaign(),
        module=_make_module(),
        actor_registry=registry,
    )
    restored = GameState.from_json(original.to_json())
    assert restored.campaign is not None
    assert restored.campaign.campaign_id == original.campaign.campaign_id
    assert restored.module is not None
    assert restored.module.module_id == original.module.module_id
    assert goblin.actor_id in restored.actor_registry.actors


def test_round_trip_campaign_optional_fields_none() -> None:
    original = GameState(
        campaign=_make_campaign(bbeg_actor_id=None, current_module_id=None)
    )
    restored = GameState.from_json(original.to_json())
    assert restored.campaign is not None
    assert restored.campaign.bbeg_actor_id is None
    assert restored.campaign.current_module_id is None


def test_round_trip_null_campaign_and_module() -> None:
    original = GameState(campaign=None, module=None)
    restored = GameState.from_json(original.to_json())
    assert restored.campaign is None
    assert restored.module is None


# --- GameState update methods ---


def _make_enc() -> EncounterState:
    return EncounterState(
        encounter_id="enc-001",
        phase=EncounterPhase.SOCIAL,
        setting="The docks.",
    )


def test_with_campaign_replaces_campaign() -> None:
    gs = GameState()
    campaign = _make_campaign()
    result = gs.with_campaign(campaign)
    assert result.campaign is campaign


def test_with_campaign_does_not_mutate_original() -> None:
    gs = GameState()
    _ = gs.with_campaign(_make_campaign())
    assert gs.campaign is None


def test_with_module_replaces_module() -> None:
    gs = GameState()
    module = _make_module()
    result = gs.with_module(module)
    assert result.module is module


def test_with_module_does_not_mutate_original() -> None:
    gs = GameState()
    _ = gs.with_module(_make_module())
    assert gs.module is None


def test_with_encounter_sets_encounter() -> None:
    gs = GameState()
    enc = _make_enc()
    result = gs.with_encounter(enc)
    assert result.encounter is enc


def test_with_encounter_does_not_mutate_original() -> None:
    gs = GameState()
    _ = gs.with_encounter(_make_enc())
    assert gs.encounter is None


def test_clear_encounter_removes_encounter() -> None:
    gs = GameState(encounter=_make_enc())
    result = gs.clear_encounter()
    assert result.encounter is None


def test_clear_encounter_when_already_none_is_idempotent() -> None:
    gs = GameState()
    result = gs.clear_encounter()
    assert result.encounter is None


def test_clear_encounter_does_not_mutate_original() -> None:
    enc = _make_enc()
    gs = GameState(encounter=enc)
    _ = gs.clear_encounter()
    assert gs.encounter is enc


def test_with_actor_registry_replaces_registry() -> None:
    registry = ActorRegistry().with_actor(TALIA)
    gs = GameState()
    result = gs.with_actor_registry(registry)
    assert TALIA.actor_id in result.actor_registry.actors


def test_with_actor_registry_does_not_mutate_original() -> None:
    registry = ActorRegistry().with_actor(TALIA)
    gs = GameState()
    _ = gs.with_actor_registry(registry)
    assert TALIA.actor_id not in gs.actor_registry.actors


# --- GameState.get_player ---


def test_get_player_returns_player_from_registry() -> None:
    registry = ActorRegistry().with_actor(TALIA)
    campaign = _make_campaign(player_actor_id=TALIA.actor_id)
    gs = GameState(campaign=campaign, actor_registry=registry)
    assert gs.get_player() is TALIA


def test_get_player_raises_when_player_not_in_registry() -> None:
    campaign = _make_campaign(player_actor_id="pc:missing")
    gs = GameState(campaign=campaign)
    with pytest.raises(RuntimeError, match="pc:missing"):
        gs.get_player()
