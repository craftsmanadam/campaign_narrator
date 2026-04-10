"""Acceptance coverage for the first Dockerized potion slice."""

from __future__ import annotations

import json
from pathlib import Path
from subprocess import CompletedProcess

from pytest_bdd import given, scenario, then, when

EXPECTED_HEALING_AMOUNT = 7


@scenario(
    "features/drink_potion.feature",
    "Drinking a potion of healing updates state and logs the event",
)
def test_drinking_potion_of_healing() -> None:
    """Run the Dockerized acceptance scenario."""


@given("the acceptance runtime root is ready", target_fixture="runtime_data_root")
def acceptance_runtime_root(runtime_data_root: Path) -> Path:
    """Expose the isolated runtime data root to the BDD scenario."""

    return runtime_data_root


@when("I run the real CLI in Docker", target_fixture="cli_result")
def run_real_cli_in_docker(
    wiremock_stack,
    docker_compose,
) -> CompletedProcess[str]:
    """Launch the production CLI in the app container."""

    return docker_compose(
        "run",
        "--rm",
        "--no-deps",
        "-T",
        "app",
        "--input",
        "I drink my potion of healing",
        "--data-root",
        "/runtime/data",
    )


def _load_event_log_entry(runtime_data_root: Path) -> dict[str, object]:
    """Return the single potion event written during the acceptance run."""

    event_log_path = runtime_data_root / "memory" / "event_log.jsonl"
    entries = [
        json.loads(line)
        for line in event_log_path.read_text().splitlines()
        if line.strip()
    ]
    assert len(entries) == 1
    return entries[0]


@then("the CLI prints the healing narration")
def cli_prints_the_healing_narration(
    cli_result: CompletedProcess[str],
    runtime_data_root: Path,
) -> None:
    """The app container should return the player-facing narration."""

    assert cli_result.returncode == 0, cli_result.stderr
    event_log_entry = _load_event_log_entry(runtime_data_root)
    assert cli_result.stdout == (
        f"Talia regains {EXPECTED_HEALING_AMOUNT} hit points.\n"
    )
    assert event_log_entry["healing_amount"] == EXPECTED_HEALING_AMOUNT


@then("the player character state is updated")
def player_character_state_is_updated(runtime_data_root: Path) -> None:
    """The runtime player state should reflect the resolved potion effect."""

    event_log_entry = _load_event_log_entry(runtime_data_root)
    player_character = json.loads(
        (runtime_data_root / "state" / "player_character.json").read_text()
    )
    expected_hp = min(
        int(player_character["hp"]["max"]),
        12 + int(event_log_entry["healing_amount"]),
    )
    assert player_character == {
        "ac": 14,
        "character_id": "pc-001",
        "hp": {"current": expected_hp, "max": 18},
        "inventory": ["rope"],
        "level": 1,
        "name": "Talia",
        "status": [],
    }


@then("the event log records the potion resolution")
def event_log_records_the_potion_resolution(runtime_data_root: Path) -> None:
    """The append-only event log should include the new potion event."""

    event_log_entry = _load_event_log_entry(runtime_data_root)
    healing_amount = int(event_log_entry["healing_amount"])
    assert event_log_entry == {
        "type": "potion_of_healing_resolved",
        "actor": "Talia",
        "input": "I drink my potion of healing",
        "roll_request": {
            "owner": "orchestrator",
            "visibility": "public",
            "expression": "2d4+2",
            "purpose": "heal from potion of healing",
        },
        "roll_total": EXPECTED_HEALING_AMOUNT,
        "healing_amount": EXPECTED_HEALING_AMOUNT,
        "hp_before": 12,
        "hp_after": min(18, 12 + healing_amount),
    }
