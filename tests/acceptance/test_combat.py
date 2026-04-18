"""Acceptance coverage for full combat encounter scenarios."""

from __future__ import annotations

from pytest_bdd import scenario


@scenario(
    "features/combat.feature",
    "Fighter defeats two goblins in multi-round combat",
)
def test_fighter_defeats_two_goblins() -> None:
    """Run the fighter vs 2 goblins scenario."""


@scenario(
    "features/combat.feature",
    "Fighter uses a healing potion and defeats three goblins",
)
def test_fighter_uses_potion_defeats_three_goblins() -> None:
    """Run the fighter vs 3 goblins scenario."""


@scenario(
    "features/combat.feature",
    "Fighter is overwhelmed by four goblins and falls",
)
def test_fighter_overwhelmed_by_four_goblins() -> None:
    """Run the fighter vs 4 goblins scenario."""
