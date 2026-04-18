"""Acceptance coverage for the encounter loop CLI slice."""

from __future__ import annotations

import json
from pathlib import Path
from subprocess import CompletedProcess

import pytest
from pytest_bdd import given, parsers, scenario, then


@scenario(
    "features/encounter_loop.feature",
    "Friendly player and peaceful goblins resolve the encounter without combat",
)
def test_peaceful_goblins_encounter() -> None:
    """Run the peaceful goblin encounter scenario."""


@scenario(
    "features/encounter_loop.feature",
    "Hostile player and hostile goblins enter combat immediately",
)
def test_hostile_goblins_encounter() -> None:
    """Run the hostile goblin encounter scenario."""


@scenario(
    "features/encounter_loop.feature",
    "Neutral player succeeds at de-escalating aggressive goblins",
)
def test_successful_de_escalation_encounter() -> None:
    """Run the successful de-escalation scenario."""


@scenario(
    "features/encounter_loop.feature",
    "Neutral player fails to de-escalate aggressive goblins",
)
def test_failed_de_escalation_encounter() -> None:
    """Run the failed de-escalation scenario."""


@scenario(
    "features/encounter_loop.feature",
    "Player saves and quits during combat",
)
def test_save_and_quit_during_combat() -> None:
    """Run the save-and-quit during combat scenario."""


@scenario(
    "features/encounter_loop.feature",
    "Rogue deceives goblins from concealment with advantage",
)
def test_rogue_deception_with_advantage() -> None:
    """Run the rogue deception with advantage scenario."""


@scenario(
    "features/encounter_loop.feature",
    "Rogue stealth past the goblin camp",
)
def test_rogue_stealth_past_goblins() -> None:
    """Run the rogue stealth scenario."""


@scenario(
    "features/encounter_loop.feature",
    "Rogue ambushes goblin scout with Sneak Attack",
)
def test_rogue_sneak_attack() -> None:
    """Run the rogue sneak attack scenario."""


def _read_event_log(runtime_data_root: Path) -> list[dict[str, object]]:
    path = runtime_data_root / "memory" / "event_log.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _read_encounter(runtime_data_root: Path, encounter_id: str) -> dict[str, object]:
    path = runtime_data_root / "state" / "encounters" / "active.json"
    return json.loads(path.read_text())


@given(
    # The negative lookahead (?!.*\bon encounter\b) prevents this step from
    # matching any step text that contains "on encounter", which would otherwise
    # create an ambiguous match with the conftest.py step
    # `configure_openai_api_for_scenario_with_encounter`. If you add new
    # scenario names containing "on encounter", use the conftest step instead.
    parsers.re(
        r"the OpenAI API is configured for (?P<scenario_name>(?!.*\bon encounter\b).+)"
    ),
    target_fixture="encounter_config",
)
def configure_openai_api_for_scenario(
    scenario_name: str,
    request: pytest.FixtureRequest,
    wiremock_stack: None,
) -> dict[str, str]:
    """Start the acceptance stack and record which scenario is under test."""

    request.node._encounter_scenario_name = scenario_name
    return {"scenario_name": scenario_name, "encounter_id": "goblin-camp"}


@then(parsers.parse('the CLI output does not include "{unexpected}"'))
def cli_output_excludes(
    cli_result: CompletedProcess[str],
    unexpected: str,
) -> None:
    """The CLI output should not contain the unexpected text."""

    assert unexpected not in cli_result.stdout


@then(
    parsers.parse(
        'the event log includes an encounter_completed event for "{encounter_id}"'
        ' with outcome "{outcome}"'
    )
)
def event_log_includes_encounter_completed(
    runtime_data_root: Path,
    encounter_id: str,
    outcome: str,
) -> None:
    """The event log should contain a matching encounter_completed event."""

    events = _read_event_log(runtime_data_root)
    matching = [
        e
        for e in events
        if e.get("type") == "encounter_completed"
        and e.get("encounter_id") == encounter_id
        and e.get("outcome") == outcome
    ]
    assert matching, (
        f"No encounter_completed event for {encounter_id!r} with outcome {outcome!r}. "
        f"Events: {events}"
    )


@then(
    parsers.parse(
        'the event log includes an encounter_saved event for "{encounter_id}"'
        ' in phase "{phase}"'
    )
)
def event_log_includes_encounter_saved(
    runtime_data_root: Path,
    encounter_id: str,
    phase: str,
) -> None:
    """The event log should contain an encounter_saved event in the given phase."""

    events = _read_event_log(runtime_data_root)
    matching = [
        e
        for e in events
        if e.get("type") == "encounter_saved"
        and e.get("encounter_id") == encounter_id
        and e.get("phase") == phase
    ]
    assert matching, (
        f"No encounter_saved event for {encounter_id!r} in phase {phase!r}. "
        f"Events: {events}"
    )


@then(parsers.parse('the persisted encounter "{encounter_id}" is in phase "{phase}"'))
def persisted_encounter_is_in_phase(
    runtime_data_root: Path,
    encounter_id: str,
    phase: str,
) -> None:
    """The on-disk encounter state should reflect the expected phase."""

    state = _read_encounter(runtime_data_root, encounter_id)
    assert state.get("phase") == phase, (
        f"Expected phase {phase!r} but got {state.get('phase')!r}"
    )


@then(parsers.parse('the persisted encounter "{encounter_id}" has initiative order'))
def persisted_encounter_has_initiative_order(
    runtime_data_root: Path,
    encounter_id: str,
) -> None:
    """The on-disk encounter state should have a non-empty combat turns list."""

    state = _read_encounter(runtime_data_root, encounter_id)
    order = state.get("combat_turns", [])
    assert order, f"Expected non-empty combat_turns but got {order!r}"


@then(parsers.parse("the player state has current hit points {hp:d}"))
def player_state_has_current_hit_points(
    runtime_data_root: Path,
    hp: int,
) -> None:
    """The on-disk player character state should reflect the expected HP."""

    path = runtime_data_root / "state" / "actors" / "player.json"
    player = json.loads(path.read_text())
    actual = player.get("hp_current")
    assert actual == hp, f"Expected current HP {hp} but got {actual}"
