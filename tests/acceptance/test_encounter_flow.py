"""Acceptance coverage for the encounter flow CLI slice."""

from __future__ import annotations

from pytest_bdd import scenario


@scenario(
    "features/encounter_flow.feature",
    "Player resolves a social encounter peacefully",
)
def test_peaceful_encounter() -> None:
    """Run the peaceful encounter scenario."""


@scenario(
    "features/encounter_flow.feature",
    "Player initiates combat from a social encounter",
)
def test_hostile_encounter() -> None:
    """Run the hostile encounter scenario."""


@scenario(
    "features/encounter_flow.feature",
    "Player succeeds at de-escalating an aggressive encounter",
)
def test_deescalation_encounter() -> None:
    """Run the de-escalation scenario."""


@scenario(
    "features/encounter_flow.feature",
    "Player saves and quits mid-encounter",
)
def test_save_and_quit() -> None:
    """Run the save-and-quit scenario."""
