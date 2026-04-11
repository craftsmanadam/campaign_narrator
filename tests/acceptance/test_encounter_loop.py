"""Acceptance coverage for the encounter loop CLI slice."""

from __future__ import annotations

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
