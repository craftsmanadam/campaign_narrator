"""Unit tests for GameState.to_json() and GameState.from_json()."""

from __future__ import annotations

from unittest.mock import MagicMock

from campaignnarrator.domain.models import (
    ActorRegistry,
    CampaignState,
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
