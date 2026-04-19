"""Unit tests for ModuleRepository."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from campaignnarrator.domain.models import ModuleState
from campaignnarrator.repositories.module_repository import ModuleRepository


def _make_module(module_id: str = "module-001") -> ModuleState:
    return ModuleState(
        module_id=module_id,
        campaign_id="c1",
        title="The Dockside Murders",
        summary="Bodies wash ashore nightly.",
        guiding_milestone_id="m1",
    )


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    repo = ModuleRepository(tmp_path)
    module = _make_module()
    repo.save(module)
    loaded = repo.load("module-001")
    assert loaded is not None
    assert loaded.module_id == "module-001"
    assert loaded.title == "The Dockside Murders"
    assert loaded.guiding_milestone_id == "m1"
    assert loaded.completed_encounter_ids == ()
    assert loaded.next_encounter_seed is None
    assert loaded.completed is False


def test_load_returns_none_when_absent(tmp_path: Path) -> None:
    repo = ModuleRepository(tmp_path)
    assert repo.load("module-001") is None


def test_save_preserves_completed_flag(tmp_path: Path) -> None:
    repo = ModuleRepository(tmp_path)
    module = replace(_make_module(), completed=True)
    repo.save(module)
    loaded = repo.load("module-001")
    assert loaded is not None
    assert loaded.completed is True


def test_save_preserves_multiple_encounters(tmp_path: Path) -> None:
    repo = ModuleRepository(tmp_path)
    module = replace(
        _make_module(),
        completed_encounter_ids=("enc-001", "enc-002"),
        completed_encounter_summaries=("First enc.", "Second enc."),
    )
    repo.save(module)
    loaded = repo.load("module-001")
    assert loaded is not None
    assert loaded.completed_encounter_ids == ("enc-001", "enc-002")
    assert loaded.completed_encounter_summaries == ("First enc.", "Second enc.")
