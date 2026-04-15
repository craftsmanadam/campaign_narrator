"""Unit tests for EncounterRepository."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from campaignnarrator.domain.models import (
    ActorState,
    ActorType,
    EncounterPhase,
    EncounterState,
    InitiativeTurn,
)
from campaignnarrator.repositories.encounter_repository import EncounterRepository

from tests.fixtures.fighter_talia import TALIA


def _minimal_encounter(
    phase: EncounterPhase = EncounterPhase.SCENE_OPENING,
) -> EncounterState:
    actor = ActorState(
        actor_id="pc:talia",
        name="Talia",
        actor_type=ActorType.PC,
        hp_current=12,
        hp_max=12,
        armor_class=15,
        strength=10,
        dexterity=10,
        constitution=10,
        intelligence=10,
        wisdom=10,
        charisma=10,
        proficiency_bonus=2,
        initiative_bonus=0,
        speed=30,
        attacks_per_action=1,
        action_options=(),
        ac_breakdown=(),
    )
    return EncounterState(
        encounter_id="goblin-camp",
        phase=phase,
        setting="A ruined roadside camp.",
        actors={"pc:talia": actor},
    )


def test_load_active_returns_none_when_no_file(tmp_path: Path) -> None:
    repo = EncounterRepository(tmp_path)
    assert repo.load_active() is None


def test_load_active_returns_encounter_when_file_exists(tmp_path: Path) -> None:
    repo = EncounterRepository(tmp_path)
    encounter = _minimal_encounter()
    repo.save(encounter)
    loaded = repo.load_active()
    assert loaded is not None
    assert loaded.encounter_id == "goblin-camp"
    assert loaded.phase is EncounterPhase.SCENE_OPENING


def test_save_and_load_round_trips_encounter(tmp_path: Path) -> None:
    repo = EncounterRepository(tmp_path)
    encounter = _minimal_encounter(EncounterPhase.SOCIAL)
    repo.save(encounter)
    loaded = repo.load_active()
    assert loaded is not None
    assert loaded.phase is EncounterPhase.SOCIAL
    assert loaded.actors["pc:talia"].hp_max == 12  # noqa: PLR2004


def test_clear_removes_active_encounter_file(tmp_path: Path) -> None:
    repo = EncounterRepository(tmp_path)
    repo.save(_minimal_encounter())
    assert repo.load_active() is not None
    repo.clear()
    assert repo.load_active() is None


def test_save_round_trips_rich_actor_with_weapons_feats_resources_inventory(
    tmp_path: Path,
) -> None:
    repo = EncounterRepository(tmp_path)
    encounter = EncounterState(
        encounter_id="goblin-camp",
        phase=EncounterPhase.COMBAT,
        setting="A ruined roadside camp.",
        actors={"pc:talia": TALIA},
    )
    repo.save(encounter)
    loaded = repo.load_active()
    assert loaded is not None
    actor = loaded.actors["pc:talia"]
    assert actor.actor_id == "pc:talia"
    assert actor.armor_class == TALIA.armor_class
    assert len(actor.equipped_weapons) == len(TALIA.equipped_weapons)
    assert actor.equipped_weapons[0].name == TALIA.equipped_weapons[0].name
    assert len(actor.feats) == len(TALIA.feats)
    assert actor.feats[0].name == TALIA.feats[0].name
    assert len(actor.resources) == len(TALIA.resources)
    assert actor.resources[0].resource == TALIA.resources[0].resource
    assert len(actor.inventory) == len(TALIA.inventory)
    assert actor.inventory[0].item == TALIA.inventory[0].item


def test_save_round_trips_combat_turns(tmp_path: Path) -> None:
    repo = EncounterRepository(tmp_path)
    encounter = _minimal_encounter(EncounterPhase.COMBAT)
    encounter = replace(
        encounter,
        combat_turns=(InitiativeTurn(actor_id="pc:talia", initiative_roll=18),),
    )
    repo.save(encounter)
    loaded = repo.load_active()
    assert loaded is not None
    assert loaded.combat_turns[0].actor_id == "pc:talia"
    assert loaded.combat_turns[0].initiative_roll == 18  # noqa: PLR2004
