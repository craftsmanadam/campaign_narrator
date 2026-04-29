"""Unit tests for PlayerRepository."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from campaignnarrator.repositories.player_repository import (
    PlayerRepository,
    player_template_from_seed,
)

from tests.fixtures.fighter_talia import TALIA


def test_load_returns_actor_from_json_file(tmp_path: Path) -> None:
    repo = PlayerRepository(tmp_path)
    repo.save(TALIA)
    loaded = repo.load()
    assert loaded.actor_id == TALIA.actor_id
    assert loaded.hp_max == TALIA.hp_max
    assert len(loaded.feats) == len(TALIA.feats)


def test_save_and_load_round_trips_actor(tmp_path: Path) -> None:
    repo = PlayerRepository(tmp_path)
    repo.save(TALIA)
    loaded = repo.load()
    assert loaded.armor_class == TALIA.armor_class
    assert loaded.equipped_weapons[0].name == TALIA.equipped_weapons[0].name
    assert loaded.resources[0].resource == TALIA.resources[0].resource


def test_save_strips_references_before_writing(tmp_path: Path) -> None:
    actor_with_refs = replace(TALIA, references=("feat text 1", "feat text 2"))
    repo = PlayerRepository(tmp_path)
    repo.save(actor_with_refs)
    loaded = repo.load()
    assert loaded.references == ()


def test_load_raises_when_file_missing(tmp_path: Path) -> None:
    repo = PlayerRepository(tmp_path)
    with pytest.raises(FileNotFoundError):
        repo.load()


def test_save_and_load_preserves_race_description_background(tmp_path: Path) -> None:
    """round-trip: race, description, background survive save/load."""
    repo = PlayerRepository(tmp_path)
    actor = replace(
        TALIA,
        race="Human",
        description="Broad-shouldered with a scar across the jaw.",
        background="Served the king's guard for six years.",
    )
    repo.save(actor)
    loaded = repo.load()
    assert loaded.race == "Human"
    assert loaded.description == "Broad-shouldered with a scar across the jaw."
    assert loaded.background == "Served the king's guard for six years."


def test_save_and_load_new_fields_default_to_none(tmp_path: Path) -> None:
    """When fields are absent in JSON, they load as None."""
    repo = PlayerRepository(tmp_path)
    repo.save(TALIA)  # TALIA has no race/description/background
    loaded = repo.load()
    assert loaded.race is None
    assert loaded.description is None
    assert loaded.background is None


def test_player_template_from_seed_is_public() -> None:
    """player_template_from_seed should be importable as a public function."""
    fixture = (
        Path(__file__).parents[3]
        / "acceptance"
        / "fixtures"
        / "examples"
        / "state"
        / "actors"
        / "player.json"
    )
    data = json.loads(fixture.read_text())
    actor = player_template_from_seed(data)
    assert actor.name == "Talia"
