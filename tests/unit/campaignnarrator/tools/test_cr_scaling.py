"""Unit tests for the CR scaling pure function."""

from __future__ import annotations

import logging

import pytest
from campaignnarrator.domain.models import EncounterNpc
from campaignnarrator.tools.cr_scaling import scale_encounter_npcs


def _npc(template_npc_id: str, cr: float) -> EncounterNpc:
    return EncounterNpc(
        template_npc_id=template_npc_id,
        display_name=template_npc_id.title(),
        role="enemy",
        description="An enemy.",
        monster_name=None,
        stat_source="simple_npc",
        cr=cr,
    )


def test_within_budget_returns_unchanged() -> None:
    """CR 0.25, player level 1: target=0.25, total=0.25 — within budget."""
    npcs = (_npc("goblin-a", 0.25),)
    result = scale_encounter_npcs(npcs, player_level=1)
    assert result == npcs


def test_over_budget_trims_lowest_cr_first() -> None:
    """Two CR 0.5 NPCs = 1.0 total vs player level 1 (budget 0.5): trims to 1 NPC."""
    # budget = player_level / 4 + tolerance = 0.25 + 0.25 = 0.50
    # 1.0 > 0.50 → trimming required
    npcs = (_npc("orc-a", 0.5), _npc("orc-b", 0.5))
    result = scale_encounter_npcs(npcs, player_level=1)
    assert len(result) == 1


def test_floor_at_one_npc_even_if_over_budget() -> None:
    """Dragon (CR 17) vs player level 1 — always keep at least 1 NPC."""
    npcs = (_npc("dragon", 17.0),)
    result = scale_encounter_npcs(npcs, player_level=1)
    assert len(result) == 1
    assert result[0].template_npc_id == "dragon"


def test_multiple_npcs_trimmed_to_fit_budget() -> None:
    """Three CR 0.25 NPCs (total 0.75) vs player level 1 (budget 0.5): trim to 2."""
    npcs = (_npc("a", 0.25), _npc("b", 0.25), _npc("c", 0.25))
    result = scale_encounter_npcs(npcs, player_level=1)
    expected_count = 2
    assert len(result) == expected_count


def test_highest_cr_npcs_kept_when_trimming() -> None:
    """When trimming, the lowest-CR NPC is removed first."""
    # One CR 0.5 + one CR 0.25 = 0.75 total, budget 0.5 for level 1: trim CR 0.25
    npcs = (_npc("orc", 0.5), _npc("goblin", 0.25))
    result = scale_encounter_npcs(npcs, player_level=1)
    assert len(result) == 1
    assert result[0].template_npc_id == "orc"


def test_empty_encounter_returned_unchanged() -> None:
    result = scale_encounter_npcs((), player_level=1)
    assert result == ()


def test_higher_player_level_allows_more_npcs() -> None:
    """Player level 4: budget = 1.0 ± 0.25. Four CR 0.25 NPCs (total 1.0): within."""
    npcs = (_npc("a", 0.25), _npc("b", 0.25), _npc("c", 0.25), _npc("d", 0.25))
    result = scale_encounter_npcs(npcs, player_level=4)
    expected_count = 4
    assert len(result) == expected_count


def test_under_budget_returns_unchanged() -> None:
    """Under-budget encounters are not adjusted."""
    cr_tenth = 0.1
    npcs = (_npc("a", cr_tenth),)
    result = scale_encounter_npcs(npcs, player_level=5)
    assert result == npcs


def test_original_npc_order_preserved_after_trim() -> None:
    """The remaining NPCs after trim keep their relative order."""
    npcs = (_npc("alpha", 0.5), _npc("beta", 0.5), _npc("gamma", 0.25))
    # Budget for level 2 = 0.5 + 0.25 = 0.75. Total = 1.25. Trim gamma (CR 0.25) first.
    # Then 0.5 + 0.5 = 1.0 > 0.75. Trim next lowest (alpha or beta, both CR 0.5).
    result = scale_encounter_npcs(npcs, player_level=2)
    assert len(result) == 1
    cr_half = 0.5
    assert result[0].cr == cr_half


def test_tolerance_boundary_at_exact_target() -> None:
    """Total CR exactly at target is within tolerance — not trimmed."""
    # Player level 4: target = 1.0, tolerance = 0.25, budget = 1.25
    # Total CR = 1.0 — within budget
    npcs = (_npc("a", 0.5), _npc("b", 0.5))
    result = scale_encounter_npcs(npcs, player_level=4)
    expected_count = 2
    assert len(result) == expected_count


def test_log_warning_when_trimmed(caplog: pytest.LogCaptureFixture) -> None:
    """A warning is logged when the encounter is trimmed."""
    # budget = 0.50 for level 1; two CR 0.5 NPCs = 1.0 total → triggers trim
    npcs = (_npc("orc-a", 0.5), _npc("orc-b", 0.5))
    with caplog.at_level(logging.WARNING, logger="campaignnarrator.tools.cr_scaling"):
        scale_encounter_npcs(npcs, player_level=1)
    assert any(
        "trimmed" in record.message.lower() or "cr" in record.message.lower()
        for record in caplog.records
    )
