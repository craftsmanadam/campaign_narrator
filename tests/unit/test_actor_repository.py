"""Unit tests for ActorRepository."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from campaignnarrator.repositories.actor_repository import ActorRepository

from tests.fixtures.fighter_talia import TALIA


def test_load_player_returns_actor_from_json_file(tmp_path: Path) -> None:
    repo = ActorRepository(tmp_path)
    repo.save(TALIA)
    loaded = repo.load_player()
    assert loaded.actor_id == TALIA.actor_id
    assert loaded.hp_max == TALIA.hp_max
    assert len(loaded.feats) == len(TALIA.feats)


def test_save_and_load_round_trips_actor(tmp_path: Path) -> None:
    repo = ActorRepository(tmp_path)
    repo.save(TALIA)
    loaded = repo.load_player()
    assert loaded.armor_class == TALIA.armor_class
    assert loaded.equipped_weapons[0].name == TALIA.equipped_weapons[0].name
    assert loaded.resources[0].resource == TALIA.resources[0].resource


def test_save_strips_references_before_writing(tmp_path: Path) -> None:
    actor_with_refs = replace(TALIA, references=("feat text 1", "feat text 2"))
    repo = ActorRepository(tmp_path)
    repo.save(actor_with_refs)
    loaded = repo.load_player()
    assert loaded.references == ()


def test_load_player_raises_when_file_missing(tmp_path: Path) -> None:
    repo = ActorRepository(tmp_path)
    with pytest.raises(FileNotFoundError):
        repo.load_player()
