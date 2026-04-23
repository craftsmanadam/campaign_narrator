"""Unit tests for ModuleRepository."""

from __future__ import annotations

import json as _json
from dataclasses import replace
from pathlib import Path

from campaignnarrator.domain.models import EncounterNpc, EncounterTemplate, ModuleState
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


def _make_encounter_npc(template_npc_id: str = "goblin-a") -> EncounterNpc:
    return EncounterNpc(
        template_npc_id=template_npc_id,
        display_name="Goblin A",
        role="scout",
        description="A small goblin.",
        monster_name="Goblin",
        stat_source="monster_compendium",
        cr=0.25,
    )


def _make_template(template_id: str = "enc-001") -> EncounterTemplate:
    return EncounterTemplate(
        template_id=template_id,
        order=0,
        setting="The fog-shrouded docks.",
        purpose="Introduce the cult.",
        scene_tone="dark and ominous",
        npcs=(_make_encounter_npc(),),
        prerequisites=(),
        expected_outcomes=("Player learns of the cult",),
        downstream_dependencies=(),
    )


def test_save_and_load_planned_encounters(tmp_path: Path) -> None:
    repo = ModuleRepository(tmp_path)
    template = _make_template()
    module = replace(
        _make_module(),
        planned_encounters=(template,),
        next_encounter_index=0,
    )
    repo.save(module)
    loaded = repo.load("module-001")
    assert loaded is not None
    assert len(loaded.planned_encounters) == 1
    t = loaded.planned_encounters[0]
    assert t.template_id == "enc-001"
    assert t.scene_tone == "dark and ominous"
    assert len(t.npcs) == 1
    assert t.npcs[0].template_npc_id == "goblin-a"
    cr_quarter = 0.25
    assert t.npcs[0].cr == cr_quarter


def test_save_and_load_next_encounter_index(tmp_path: Path) -> None:
    expected_index = 2
    repo = ModuleRepository(tmp_path)
    module = replace(_make_module(), next_encounter_index=expected_index)
    repo.save(module)
    loaded = repo.load("module-001")
    assert loaded is not None
    assert loaded.next_encounter_index == expected_index


def test_load_old_record_without_planned_encounters(tmp_path: Path) -> None:
    """Old JSON records without planned_encounters/next_encounter_index must load cleanly."""
    modules_dir = tmp_path / "state" / "modules"
    modules_dir.mkdir(parents=True)
    old_json = {
        "module_id": "module-001",
        "campaign_id": "c1",
        "title": "Old Module",
        "summary": "Old summary.",
        "guiding_milestone_id": "m1",
        "completed_encounter_ids": [],
        "completed_encounter_summaries": [],
        "next_encounter_seed": "A goblin lurks in the shadows.",
        "completed": False,
    }
    (modules_dir / "module-001.json").write_text(__import__("json").dumps(old_json))
    repo = ModuleRepository(tmp_path)
    loaded = repo.load("module-001")
    assert loaded is not None
    assert loaded.planned_encounters == ()
    assert loaded.next_encounter_index == 0


def test_serialized_json_includes_planned_encounters_key(tmp_path: Path) -> None:
    """Serialized JSON must include planned_encounters and next_encounter_index."""
    repo = ModuleRepository(tmp_path)
    module = _make_module()
    repo.save(module)
    path = tmp_path / "state" / "modules" / "module-001.json"
    data = _json.loads(path.read_text())
    assert "planned_encounters" in data
    assert "next_encounter_index" in data
