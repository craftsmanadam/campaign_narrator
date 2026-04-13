"""Unit tests for the encounter state repository."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from campaignnarrator.domain.models import EncounterPhase
from campaignnarrator.repositories.state_repository import StateRepository

EXPECTED_ARMOR_CLASS = 18
TALIA_HP_CURRENT = 12


def test_state_repository_loads_seed_encounter_state() -> None:
    """Seeded encounter state should load into the generic encounter model."""

    repository = StateRepository.from_seed(_seed())
    state = repository.load_encounter("goblin-camp")

    assert state.encounter_id == "goblin-camp"
    assert state.phase is EncounterPhase.SCENE_OPENING
    assert state.actors["pc:talia"].armor_class == EXPECTED_ARMOR_CLASS


def test_state_repository_saves_and_returns_copy_of_encounter_state() -> None:
    """Saving should persist a copied state, not the original object."""

    repository = StateRepository.from_default_encounter()
    state = repository.load_encounter("goblin-camp")
    updated = state.with_phase(EncounterPhase.COMBAT)

    repository.save_encounter(updated)

    reloaded = repository.load_encounter("goblin-camp")

    assert reloaded.phase is EncounterPhase.COMBAT
    assert reloaded is not updated


def test_state_repository_rejects_unknown_encounter() -> None:
    """Missing encounters should fail closed with a clear error."""

    repository = StateRepository.from_default_encounter()

    with pytest.raises(ValueError, match="unknown encounter: missing"):
        repository.load_encounter("missing")


def test_state_repository_rejects_non_mapping_actors() -> None:
    """Actors must be provided as a mapping."""

    with pytest.raises(ValueError, match="seed actors must be a mapping"):
        StateRepository.from_seed({**_seed(), "actors": []})


def test_state_repository_rejects_non_mapping_root_seed() -> None:
    """The top-level seed must be a mapping before field access."""

    with pytest.raises(ValueError, match="invalid encounter seed: root"):
        StateRepository.from_seed([])


def test_state_repository_rejects_missing_required_top_level_key() -> None:
    """Missing required top-level keys should fail the seed validation."""

    seed = _seed()
    seed.pop("setting")

    with pytest.raises(ValueError, match="invalid encounter seed: setting"):
        StateRepository.from_seed(seed)


def test_state_repository_rejects_invalid_enum_phase() -> None:
    """Unknown phase values should be rejected explicitly."""

    with pytest.raises(ValueError, match="invalid encounter phase: unknown"):
        StateRepository.from_seed({**_seed(), "phase": "unknown"})


def test_state_repository_normalizes_stringified_boolean_visibility() -> None:
    """Stringified visibility flags should normalize to booleans."""

    repository = StateRepository.from_seed(
        {
            **_seed(),
            "actors": {
                "npc:goblin-scout": {
                    "actor_id": "npc:goblin-scout",
                    "name": "Goblin Scout",
                    "kind": "npc",
                    "hp_current": 7,
                    "hp_max": 7,
                    "armor_class": 15,
                    "inventory": (),
                    "conditions": (),
                    "is_visible": "false",
                }
            },
        }
    )

    state = repository.load_encounter("goblin-camp")

    assert state.actors["npc:goblin-scout"].is_visible is False


def test_state_repository_copies_nested_state_on_save_and_load() -> None:
    """Loaded and reloaded states should be equal but not aliased."""

    repository = StateRepository.from_seed(_seed())
    state = repository.load_encounter("goblin-camp")
    repository.save_encounter(state)

    reloaded = repository.load_encounter("goblin-camp")

    assert reloaded == state
    assert reloaded is not state
    assert reloaded.hidden_facts == state.hidden_facts
    assert reloaded.hidden_facts is not state.hidden_facts
    assert reloaded.public_events == state.public_events
    assert reloaded.initiative_order == state.initiative_order
    assert reloaded.actors["pc:talia"] is not state.actors["pc:talia"]
    assert reloaded.actors["pc:talia"].inventory == state.actors["pc:talia"].inventory
    assert reloaded.actors["pc:talia"].conditions == state.actors["pc:talia"].conditions


def test_state_repository_deep_copies_nested_hidden_facts() -> None:
    """Nested hidden facts should not share mutable substructures."""

    seed = _seed()
    seed["hidden_facts"] = {"nested": {"alarm": ["bell"]}}

    repository = StateRepository.from_seed(seed)
    loaded = repository.load_encounter("goblin-camp")
    loaded.hidden_facts["nested"]["alarm"].append("gong")
    seed["hidden_facts"]["nested"]["alarm"].append("horn")

    reloaded = repository.load_encounter("goblin-camp")

    assert reloaded.hidden_facts == {"nested": {"alarm": ["bell"]}}
    assert reloaded.hidden_facts is not loaded.hidden_facts


def test_state_repository_loads_and_saves_root_backed_player_character_snapshot(
    tmp_path: Path,
) -> None:
    """Legacy file-backed state access should still work from a repository root."""

    state_root = tmp_path / "state"
    state_root.mkdir(parents=True)
    (state_root / "player_character.json").write_text(
        json.dumps(
            {
                "character_id": "pc-001",
                "name": "Talia",
                "hp": {"current": 12, "max": 18},
                "inventory": ["rope"],
            }
        )
    )

    repository = StateRepository(state_root)

    player_character = repository.load_player_character()
    assert player_character["character_id"] == "pc-001"
    assert player_character["inventory"] == ["rope"]

    repository.save_player_character(
        {
            "character_id": "pc-001",
            "name": "Talia",
            "hp": {"current": 18, "max": 18},
            "inventory": ["rope", "torch"],
        }
    )

    assert repository.load_player_character()["hp"] == {"current": 18, "max": 18}
    assert json.loads((state_root / "player_character.json").read_text()) == {
        "character_id": "pc-001",
        "name": "Talia",
        "hp": {"current": 18, "max": 18},
        "inventory": ["rope", "torch"],
    }


_FILE_BACKED_SEED = {
    "encounter_id": "goblin-camp",
    "phase": "social",
    "setting": "A ruined roadside camp.",
    "public_events": ["The goblins are watching."],
    "hidden_facts": {"goblin_disposition": "neutral"},
    "initiative_order": [],
    "outcome": None,
    "actors": {
        "pc:talia": {
            "actor_id": "pc:talia",
            "name": "Talia",
            "kind": "pc",
            "hp_current": 12,
            "hp_max": 12,
            "armor_class": 18,
            "inventory": ["longsword", "chain-mail", "shield", "potion-of-healing"],
            "conditions": [],
            "is_visible": True,
        },
        "npc:goblin-scout": {
            "actor_id": "npc:goblin-scout",
            "name": "Goblin Scout",
            "kind": "npc",
            "hp_current": 7,
            "hp_max": 7,
            "armor_class": 15,
            "inventory": ["scimitar", "shortbow"],
            "conditions": [],
            "is_visible": True,
        },
    },
}


def test_load_encounter_reads_from_encounter_file(tmp_path: Path) -> None:
    """StateRepository should load encounter state from a JSON file on disk."""

    encounter_dir = tmp_path / "encounters"
    encounter_dir.mkdir(parents=True)
    (encounter_dir / "goblin-camp.json").write_text(
        json.dumps(_FILE_BACKED_SEED) + "\n"
    )

    repository = StateRepository(tmp_path)
    state = repository.load_encounter("goblin-camp")

    assert state.encounter_id == "goblin-camp"
    assert state.phase is EncounterPhase.SOCIAL
    assert state.actors["pc:talia"].inventory == (
        "longsword",
        "chain-mail",
        "shield",
        "potion-of-healing",
    )


def test_save_encounter_writes_json_to_encounter_file(tmp_path: Path) -> None:
    """StateRepository should write encounter state to disk as sorted JSON."""

    repository = StateRepository(tmp_path)
    seed_repo = StateRepository.from_seed(_FILE_BACKED_SEED)
    state = seed_repo.load_encounter("goblin-camp")

    repository.save_encounter(state)

    encounter_path = tmp_path / "encounters" / "goblin-camp.json"
    assert encounter_path.exists()
    on_disk = json.loads(encounter_path.read_text())
    assert on_disk["phase"] == "social"
    assert on_disk["actors"]["pc:talia"]["hp_current"] == TALIA_HP_CURRENT
    assert encounter_path.read_text().endswith("\n")


def test_save_encounter_creates_encounter_directory_if_missing(tmp_path: Path) -> None:
    """save_encounter should create the encounters directory if it does not exist."""

    repository = StateRepository(tmp_path)
    seed_repo = StateRepository.from_seed(_FILE_BACKED_SEED)
    state = seed_repo.load_encounter("goblin-camp")

    repository.save_encounter(state)

    assert (tmp_path / "encounters" / "goblin-camp.json").exists()


def test_load_encounter_rejects_missing_file(tmp_path: Path) -> None:
    """load_encounter should raise ValueError when no file exists for the encounter."""

    repository = StateRepository(tmp_path)

    with pytest.raises(ValueError, match="unknown encounter: missing"):
        repository.load_encounter("missing")


def test_save_and_load_encounter_round_trips_state(tmp_path: Path) -> None:
    """A state saved to disk and reloaded should be equal to the original."""

    repository = StateRepository(tmp_path)
    seed_repo = StateRepository.from_seed(_FILE_BACKED_SEED)
    state = seed_repo.load_encounter("goblin-camp")

    repository.save_encounter(state)
    reloaded = repository.load_encounter("goblin-camp")

    assert reloaded.encounter_id == state.encounter_id
    assert reloaded.phase == state.phase
    assert reloaded.setting == state.setting
    assert reloaded.actors["pc:talia"].inventory == state.actors["pc:talia"].inventory
    assert reloaded.initiative_order == state.initiative_order
    assert reloaded.outcome == state.outcome


def test_load_encounter_prefers_in_memory_state_over_file(tmp_path: Path) -> None:
    """If a state is already in memory, the file should not be re-read."""

    encounter_dir = tmp_path / "encounters"
    encounter_dir.mkdir(parents=True)
    (encounter_dir / "goblin-camp.json").write_text(
        json.dumps(_FILE_BACKED_SEED) + "\n"
    )

    repository = StateRepository(tmp_path)
    state = repository.load_encounter("goblin-camp")
    updated = state.with_phase(EncounterPhase.COMBAT)
    repository.save_encounter(updated)

    reloaded = repository.load_encounter("goblin-camp")

    assert reloaded.phase is EncounterPhase.COMBAT


def _seed() -> dict[str, object]:
    return {
        "encounter_id": "goblin-camp",
        "setting": "A ruined roadside camp.",
        "phase": "scene_opening",
        "public_events": [
            "A cold wind moves through the camp.",
        ],
        "hidden_facts": {"goblin_disposition": "peaceful"},
        "initiative_order": ["pc:talia", "npc:goblin-scout"],
        "actors": {
            "pc:talia": {
                "actor_id": "pc:talia",
                "name": "Talia",
                "kind": "pc",
                "hp_current": 12,
                "hp_max": 12,
                "armor_class": EXPECTED_ARMOR_CLASS,
                "inventory": [
                    "longsword",
                    "chain-mail",
                    "shield",
                    "potion-of-healing",
                ],
                "conditions": ["steady"],
                "is_visible": True,
            },
            "npc:goblin-scout": {
                "actor_id": "npc:goblin-scout",
                "name": "Goblin Scout",
                "kind": "npc",
                "hp_current": 7,
                "hp_max": 7,
                "armor_class": 15,
                "inventory": ["scimitar", "shortbow"],
                "conditions": [],
                "is_visible": True,
            },
        },
    }
