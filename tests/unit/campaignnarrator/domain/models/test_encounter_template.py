"""Unit tests for encounter_template domain models."""

from __future__ import annotations

import pytest
from campaignnarrator.domain.models import (
    EncounterNpc,
    EncounterTemplate,
)
from pydantic import ValidationError


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


def test_encounter_npc_accepts_float_cr() -> None:
    cr_quarter = 0.25
    npc = EncounterNpc(
        template_npc_id="goblin-scout-a",
        display_name="Goblin Scout A",
        role="skittish lookout",
        description="A small goblin clutching a rusty shortbow.",
        monster_name="Goblin",
        stat_source="monster_compendium",
        cr=cr_quarter,
    )
    assert npc.cr == cr_quarter
    assert npc.name_known is False


def test_encounter_npc_parses_fraction_string_cr() -> None:
    cr_quarter = 0.25
    npc = EncounterNpc(
        template_npc_id="goblin-scout-b",
        display_name="Goblin Scout B",
        role="pack fighter",
        description="A goblin with a bent scimitar.",
        monster_name="Goblin",
        stat_source="monster_compendium",
        cr="1/4",
    )
    assert npc.cr == cr_quarter


def test_encounter_npc_parses_half_fraction_cr() -> None:
    cr_half = 0.5
    npc = EncounterNpc(
        template_npc_id="orc",
        display_name="Orc Raider",
        role="brute",
        description="A scarred orc with a greataxe.",
        monster_name="Orc",
        stat_source="monster_compendium",
        cr="1/2",
    )
    assert npc.cr == cr_half


def test_encounter_npc_rejects_invalid_cr() -> None:
    with pytest.raises(ValidationError):
        EncounterNpc(
            template_npc_id="bad",
            display_name="Bad",
            role="",
            description="",
            monster_name=None,
            stat_source="simple_npc",
            cr=[1, 2],  # type: ignore[arg-type]
        )


def test_encounter_npc_simple_npc_has_no_monster_name() -> None:
    npc = EncounterNpc(
        template_npc_id="innkeeper-mira",
        display_name="Mira",
        role="innkeeper",
        description="A tired woman with ink-stained fingers.",
        monster_name=None,
        stat_source="simple_npc",
        cr=0.0,
    )
    assert npc.monster_name is None
    assert npc.stat_source == "simple_npc"


def test_encounter_npc_is_frozen() -> None:
    npc = EncounterNpc(
        template_npc_id="x",
        display_name="X",
        role="r",
        description="d",
        monster_name=None,
        stat_source="simple_npc",
        cr=0.0,
    )
    with pytest.raises((ValidationError, TypeError)):
        npc.cr = 1.0  # type: ignore[misc]


def test_encounter_template_stores_all_fields() -> None:
    template = EncounterTemplate(
        template_id="enc-001",
        order=0,
        setting="The fog-shrouded docks of Darkholm.",
        purpose="Introduce the Drowned Lady cult threat.",
        scene_tone="dark and ominous",
        npcs=(
            _make_encounter_npc("goblin-scout-a"),
            _make_encounter_npc("goblin-scout-b"),
        ),
        prerequisites=(),
        expected_outcomes=("Player learns of the Drowned Lady",),
        downstream_dependencies=(),
    )
    assert template.template_id == "enc-001"
    assert template.order == 0
    assert template.npcs == (
        _make_encounter_npc("goblin-scout-a"),
        _make_encounter_npc("goblin-scout-b"),
    )
    assert template.scene_tone == "dark and ominous"


def test_encounter_template_scene_tone_defaults_none() -> None:
    template = EncounterTemplate(
        template_id="enc-001",
        order=0,
        setting="The docks.",
        purpose="A fight.",
        npcs=(_make_encounter_npc(),),
        prerequisites=(),
        expected_outcomes=(),
        downstream_dependencies=(),
    )
    assert template.scene_tone is None


def test_encounter_template_is_frozen() -> None:
    template = EncounterTemplate(
        template_id="enc-001",
        order=0,
        setting="x",
        purpose="y",
        npcs=(_make_encounter_npc(),),
        prerequisites=(),
        expected_outcomes=(),
        downstream_dependencies=(),
    )
    with pytest.raises((ValidationError, TypeError)):
        template.order = 1  # type: ignore[misc]


def test_encounter_template_empty_npcs_allowed() -> None:
    template = EncounterTemplate(
        template_id="enc-001",
        order=0,
        setting="x",
        purpose="y",
        npcs=(),
        prerequisites=(),
        expected_outcomes=(),
        downstream_dependencies=(),
    )
    assert template.npcs == ()
