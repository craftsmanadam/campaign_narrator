"""Unit tests for GameState.to_json(), GameState.from_json(), and GameState methods."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock

import pytest
from campaignnarrator.domain.models import (
    ActorRegistry,
    CampaignState,
    CombatState,
    CombatStatus,
    EncounterPhase,
    EncounterState,
    GameState,
    InitiativeTurn,
    InventoryItem,
    Milestone,
    ModuleState,
    NpcPresence,
    NpcPresenceStatus,
    ResourceUnavailableError,
    TurnOrder,
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


def test_clear_encounter_also_clears_combat_state() -> None:
    gs = GameState(encounter=_make_enc(), combat_state=CombatState())
    result = gs.clear_encounter()
    assert result.encounter is None
    assert result.combat_state is None


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


# --- Helper factories for combat/encounter tests ---


def _make_encounter(**overrides: object) -> EncounterState:
    defaults: dict[str, object] = {
        "encounter_id": "enc-001",
        "phase": EncounterPhase.SOCIAL,
        "setting": "The docks.",
        "actor_ids": (),
        "player_actor_id": "",
    }
    defaults.update(overrides)
    return EncounterState(**defaults)  # type: ignore[arg-type]


def _make_combat_state(**overrides: object) -> CombatState:
    talia_turn = InitiativeTurn(actor_id=TALIA.actor_id, initiative_roll=18)
    goblin_turn = InitiativeTurn(actor_id="npc:goblin-1", initiative_roll=12)
    defaults: dict[str, object] = {
        "turn_order": TurnOrder(turns=(talia_turn, goblin_turn)),
        "status": CombatStatus.ACTIVE,
        "current_turn_resources": TALIA.get_turn_resources(),
    }
    defaults.update(overrides)
    return CombatState(**defaults)  # type: ignore[arg-type]


# --- GameState.with_combat_state ---


def test_with_combat_state_sets_combat_state() -> None:
    gs = GameState()
    result = gs.with_combat_state(CombatState())
    assert result.combat_state is not None


def test_with_combat_state_clears_to_none() -> None:
    gs = GameState(combat_state=CombatState())
    result = gs.with_combat_state(None)
    assert result.combat_state is None


def test_with_combat_state_does_not_mutate_original() -> None:
    gs = GameState()
    _ = gs.with_combat_state(CombatState())
    assert gs.combat_state is None


# --- GameState.with_combat_status ---


def test_with_combat_status_updates_status() -> None:
    gs = GameState(combat_state=_make_combat_state(status=CombatStatus.ACTIVE))
    result = gs.with_combat_status(CombatStatus.COMPLETE)
    assert result.combat_state is not None
    assert result.combat_state.status == CombatStatus.COMPLETE


def test_with_combat_status_noop_when_no_combat_state() -> None:
    gs = GameState()
    result = gs.with_combat_status(CombatStatus.COMPLETE)
    assert result is gs


# --- GameState.advance_turn ---


def test_advance_turn_rotates_to_next_actor() -> None:
    goblin = make_goblin_scout("npc:goblin-1", "Goblin Scout")
    registry = ActorRegistry(actors={TALIA.actor_id: TALIA, goblin.actor_id: goblin})
    gs = GameState(combat_state=_make_combat_state(), actor_registry=registry)
    result = gs.advance_turn()
    assert result.combat_state is not None
    assert result.combat_state.turn_order.current_actor_id == "npc:goblin-1"


def test_advance_turn_seeds_fresh_resources() -> None:
    goblin = make_goblin_scout("npc:goblin-1", "Goblin Scout")
    registry = ActorRegistry(actors={TALIA.actor_id: TALIA, goblin.actor_id: goblin})
    spent_resources = replace(TALIA.get_turn_resources(), action_available=False)
    cs = _make_combat_state(current_turn_resources=spent_resources)
    gs = GameState(combat_state=cs, actor_registry=registry)
    result = gs.advance_turn()
    assert result.combat_state is not None
    assert result.combat_state.current_turn_resources.action_available is True


def test_advance_turn_noop_when_no_combat_state() -> None:
    gs = GameState()
    result = gs.advance_turn()
    assert result is gs


def test_advance_turn_does_not_mutate_original() -> None:
    goblin = make_goblin_scout("npc:goblin-1", "Goblin Scout")
    registry = ActorRegistry(actors={TALIA.actor_id: TALIA, goblin.actor_id: goblin})
    gs = GameState(combat_state=_make_combat_state(), actor_registry=registry)
    original_current = gs.combat_state.turn_order.current_actor_id  # type: ignore[union-attr]
    _ = gs.advance_turn()
    assert gs.combat_state is not None
    assert gs.combat_state.turn_order.current_actor_id == original_current


# --- GameState.spend_turn_resource ---


def test_spend_turn_resource_action_marks_unavailable() -> None:
    gs = GameState(combat_state=_make_combat_state())
    result = gs.spend_turn_resource("action")
    assert result.combat_state is not None
    assert result.combat_state.current_turn_resources.action_available is False


def test_spend_turn_resource_raises_when_exhausted() -> None:
    gs = GameState(combat_state=_make_combat_state())
    gs_spent = gs.spend_turn_resource("action")
    with pytest.raises(ResourceUnavailableError):
        gs_spent.spend_turn_resource("action")


def test_spend_turn_resource_noop_when_no_combat_state() -> None:
    gs = GameState()
    result = gs.spend_turn_resource("action")
    assert result is gs


# --- GameState.adjust_hit_points ---


def test_adjust_hit_points_reduces_hp() -> None:
    registry = ActorRegistry().with_actor(TALIA)
    gs = GameState(actor_registry=registry)
    result = gs.adjust_hit_points(TALIA.actor_id, -5)
    actor = result.actor_registry.actors[TALIA.actor_id]
    assert actor.hp_current == TALIA.hp_max - 5


def test_adjust_hit_points_clamps_to_zero() -> None:
    registry = ActorRegistry().with_actor(TALIA)
    gs = GameState(actor_registry=registry)
    result = gs.adjust_hit_points(TALIA.actor_id, -9999)
    actor = result.actor_registry.actors[TALIA.actor_id]
    assert actor.hp_current == 0


def test_adjust_hit_points_clamps_to_max() -> None:
    low_hp_talia = replace(TALIA, hp_current=1)
    registry = ActorRegistry().with_actor(low_hp_talia)
    gs = GameState(actor_registry=registry)
    result = gs.adjust_hit_points(TALIA.actor_id, 9999)
    actor = result.actor_registry.actors[TALIA.actor_id]
    assert actor.hp_current == TALIA.hp_max


def test_adjust_hit_points_does_not_mutate_original() -> None:
    registry = ActorRegistry().with_actor(TALIA)
    gs = GameState(actor_registry=registry)
    _ = gs.adjust_hit_points(TALIA.actor_id, -5)
    assert gs.actor_registry.actors[TALIA.actor_id].hp_current == TALIA.hp_current


# --- GameState.add_condition ---


def test_add_condition_adds_condition() -> None:
    registry = ActorRegistry().with_actor(TALIA)
    gs = GameState(actor_registry=registry)
    result = gs.add_condition(TALIA.actor_id, "poisoned")
    actor = result.actor_registry.actors[TALIA.actor_id]
    assert "poisoned" in actor.conditions


def test_add_condition_does_not_mutate_original() -> None:
    registry = ActorRegistry().with_actor(TALIA)
    gs = GameState(actor_registry=registry)
    _ = gs.add_condition(TALIA.actor_id, "poisoned")
    assert "poisoned" not in gs.actor_registry.actors[TALIA.actor_id].conditions


# --- GameState.remove_condition ---


def test_remove_condition_removes_condition() -> None:
    poisoned_talia = replace(TALIA, conditions=("poisoned",))
    registry = ActorRegistry().with_actor(poisoned_talia)
    gs = GameState(actor_registry=registry)
    result = gs.remove_condition(TALIA.actor_id, "poisoned")
    actor = result.actor_registry.actors[TALIA.actor_id]
    assert "poisoned" not in actor.conditions


def test_remove_condition_noop_when_not_present() -> None:
    registry = ActorRegistry().with_actor(TALIA)
    gs = GameState(actor_registry=registry)
    result = gs.remove_condition(TALIA.actor_id, "stunned")
    actor = result.actor_registry.actors[TALIA.actor_id]
    assert "stunned" not in actor.conditions


# --- GameState.spend_inventory ---


def test_spend_inventory_reduces_count() -> None:
    item = InventoryItem(item_id="potion-1", item="Healing Potion", count=2)
    talia_with_item = replace(TALIA, inventory=(item,))
    registry = ActorRegistry().with_actor(talia_with_item)
    gs = GameState(actor_registry=registry)
    result = gs.spend_inventory(TALIA.actor_id, "potion-1")
    actor = result.actor_registry.actors[TALIA.actor_id]
    remaining = [i for i in actor.inventory if i.item_id == "potion-1"]
    assert remaining[0].count == 1


def test_spend_inventory_removes_item_at_zero() -> None:
    item = InventoryItem(item_id="potion-1", item="Healing Potion", count=1)
    talia_with_item = replace(TALIA, inventory=(item,))
    registry = ActorRegistry().with_actor(talia_with_item)
    gs = GameState(actor_registry=registry)
    result = gs.spend_inventory(TALIA.actor_id, "potion-1")
    actor = result.actor_registry.actors[TALIA.actor_id]
    assert not any(i.item_id == "potion-1" for i in actor.inventory)


# --- GameState.set_phase ---


def test_set_phase_updates_encounter_phase() -> None:
    gs = GameState(encounter=_make_encounter(phase=EncounterPhase.SOCIAL))
    result = gs.set_phase(EncounterPhase.COMBAT)
    assert result.encounter is not None
    assert result.encounter.phase == EncounterPhase.COMBAT


def test_set_phase_noop_when_no_encounter() -> None:
    gs = GameState()
    result = gs.set_phase(EncounterPhase.COMBAT)
    assert result is gs


# --- GameState.set_encounter_outcome ---


def test_set_encounter_outcome_sets_outcome() -> None:
    gs = GameState(encounter=_make_encounter())
    result = gs.set_encounter_outcome("victory")
    assert result.encounter is not None
    assert result.encounter.outcome == "victory"


def test_set_encounter_outcome_noop_when_no_encounter() -> None:
    gs = GameState()
    result = gs.set_encounter_outcome("victory")
    assert result is gs


# --- GameState.append_public_event ---


def test_append_public_event_appends_to_events() -> None:
    enc = _make_encounter(public_events=("first event",))
    gs = GameState(encounter=enc)
    result = gs.append_public_event("second event")
    assert result.encounter is not None
    assert len(result.encounter.public_events) == 2  # noqa: PLR2004
    assert result.encounter.public_events[1] == "second event"


def test_append_public_event_noop_when_no_encounter() -> None:
    gs = GameState()
    result = gs.append_public_event("event")
    assert result is gs


# --- GameState.set_npc_status ---


def test_set_npc_status_updates_matching_npc() -> None:
    npc = NpcPresence(
        actor_id="npc:goblin-1",
        display_name="Goblin Scout",
        description="a small goblin",
        name_known=False,
        status=NpcPresenceStatus.PRESENT,
    )
    enc = _make_encounter(npc_presences=(npc,))
    gs = GameState(encounter=enc)
    result = gs.set_npc_status("npc:goblin-1", NpcPresenceStatus.DEPARTED)
    assert result.encounter is not None
    assert result.encounter.npc_presences[0].status == NpcPresenceStatus.DEPARTED


def test_set_npc_status_noop_when_no_encounter() -> None:
    gs = GameState()
    result = gs.set_npc_status("npc:goblin-1", NpcPresenceStatus.DEPARTED)
    assert result is gs


def test_set_npc_status_noop_when_actor_not_in_presences() -> None:
    enc = _make_encounter()
    gs = GameState(encounter=enc)
    result = gs.set_npc_status("npc:unknown", NpcPresenceStatus.DEPARTED)
    assert result is gs
