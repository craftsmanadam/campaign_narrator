"""Acceptance coverage for the combat flow CLI slice."""

from __future__ import annotations

from pytest_bdd import scenario


@scenario(
    "features/combat_flow.feature",
    "Fighter defeats two goblins in multi-round combat",
)
def test_fighter_defeats_two_goblins() -> None:
    """Run the fighter vs two goblins combat scenario."""
