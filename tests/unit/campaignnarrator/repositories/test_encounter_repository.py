"""Unit tests for EncounterRepository."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from campaignnarrator.domain.models import (
    EncounterPhase,
    EncounterState,
    InitiativeTurn,
)
from campaignnarrator.repositories.encounter_repository import EncounterRepository

from tests.fixtures.fighter_talia import TALIA


def _minimal_encounter(
    phase: EncounterPhase = EncounterPhase.SCENE_OPENING,
) -> EncounterState:
    return EncounterState(
        encounter_id="goblin-camp",
        phase=phase,
        setting="A ruined roadside camp.",
        actor_ids=("pc:talia",),
        player_actor_id="pc:talia",
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
    assert "pc:talia" in loaded.actor_ids
    assert loaded.player_actor_id == "pc:talia"


def test_clear_removes_active_encounter_file(tmp_path: Path) -> None:
    repo = EncounterRepository(tmp_path)
    repo.save(_minimal_encounter())
    assert repo.load_active() is not None
    repo.clear()
    assert repo.load_active() is None


def test_save_round_trips_actor_ids(tmp_path: Path) -> None:
    """actor_ids should survive a save/load round-trip (actors live in registry now)."""
    repo = EncounterRepository(tmp_path)
    encounter = EncounterState(
        encounter_id="goblin-camp",
        phase=EncounterPhase.COMBAT,
        setting="A ruined roadside camp.",
        actor_ids=(TALIA.actor_id,),
        player_actor_id=TALIA.actor_id,
    )
    repo.save(encounter)
    loaded = repo.load_active()
    assert loaded is not None
    assert TALIA.actor_id in loaded.actor_ids
    assert loaded.player_actor_id == TALIA.actor_id


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


def test_save_and_load_round_trips_scene_tone(tmp_path: Path) -> None:
    """scene_tone should survive a save/load round-trip through the repository."""
    repo = EncounterRepository(tmp_path)
    state = _minimal_encounter()
    state = replace(state, scene_tone="tense and foreboding")

    repo.save(state)
    loaded = repo.load_active()

    assert loaded is not None
    assert loaded.scene_tone == "tense and foreboding"
