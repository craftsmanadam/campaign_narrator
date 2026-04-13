"""Acceptance coverage for the encounter loop CLI slice."""

from __future__ import annotations

import json
from pathlib import Path
from subprocess import CompletedProcess, run

import pytest
from pytest_bdd import given, parsers, scenario, then, when

PROJECT_ROOT = Path(__file__).resolve().parents[2]


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


def _read_event_log(runtime_data_root: Path) -> list[dict[str, object]]:
    path = runtime_data_root / "memory" / "event_log.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _read_encounter(runtime_data_root: Path, encounter_id: str) -> dict[str, object]:
    path = runtime_data_root / "state" / "encounters" / f"{encounter_id}.json"
    return json.loads(path.read_text())


@given(
    parsers.parse("the OpenAI API is configured for {scenario_name}"),
    target_fixture="encounter_scenario_name",
)
def configure_openai_api_for_scenario(
    scenario_name: str,
    request: pytest.FixtureRequest,
    wiremock_stack: None,
) -> str:
    """Start the acceptance stack and record which scenario is under test."""

    request.node._encounter_scenario_name = scenario_name
    return scenario_name


@when(
    "the player runs the encounter with scripted input:",
    target_fixture="cli_result",
)
def run_encounter_with_scripted_input(
    compose_environment: dict[str, str],
    encounter_scenario_name: str,
    docstring: str,
    request: pytest.FixtureRequest,
    wiremock_stack: None,
) -> CompletedProcess[str]:
    """Run the production CLI through Docker Compose with scripted stdin."""

    request.node._encounter_scenario_name = encounter_scenario_name
    scripted_input = docstring
    completed_process = run(
        [
            "docker",
            "compose",
            "-f",
            str(PROJECT_ROOT / "docker-compose.acceptance.yml"),
            "run",
            "--rm",
            "--no-deps",
            "-T",
            "app",
            "--data-root",
            "/runtime/data",
            "--encounter-id",
            "goblin-camp",
        ],
        input=scripted_input,
        text=True,
        capture_output=True,
        timeout=60,
        env=compose_environment,
        cwd=PROJECT_ROOT,
        check=False,
    )
    request.node._cli_result = completed_process
    assert completed_process.returncode == 0, completed_process.stderr
    return completed_process


@then(parsers.parse('the CLI output includes "{expected}"'))
def cli_output_includes(
    cli_result: CompletedProcess[str],
    expected: str,
) -> None:
    """The CLI output should contain the expected text."""

    assert expected in cli_result.stdout


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
    """The on-disk encounter state should have a non-empty initiative order."""

    state = _read_encounter(runtime_data_root, encounter_id)
    order = state.get("initiative_order", [])
    assert order, f"Expected non-empty initiative_order but got {order!r}"


@then(parsers.parse("the player state has current hit points {hp:d}"))
def player_state_has_current_hit_points(
    runtime_data_root: Path,
    hp: int,
) -> None:
    """The on-disk player character state should reflect the expected HP."""

    path = runtime_data_root / "state" / "player_character.json"
    player = json.loads(path.read_text())
    actual = player.get("hp", {}).get("current")
    assert actual == hp, f"Expected current HP {hp} but got {actual}"
