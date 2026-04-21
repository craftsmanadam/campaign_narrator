"""Shared fixtures for Dockerized acceptance tests."""

from __future__ import annotations

import json
import os
import shutil
import socket
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from subprocess import CompletedProcess, run

import pytest
from pytest_bdd import given, parsers, then, when

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures"
EXAMPLES_ROOT = FIXTURE_ROOT / "examples"
RUNTIME_ROOT = FIXTURE_ROOT / "runtime"


WIREMOCK_READY_STATUS = 200
_HTTP_NOT_FOUND = 404

_ENCOUNTER_TO_WIREMOCK_SCENARIO: dict[str, str] = {
    "fighter-vs-2-goblins": "combat-s1",
    "fighter-vs-3-goblins": "combat-s2",
    "fighter-vs-4-goblins": "combat-s3",
}

_WIREMOCK_SCENARIO_TERMINAL_STATE: dict[str, str] = {
    "combat-s1": "S1-Done",
    "combat-s2": "S2-Done",
    "combat-s3": "S3-Done",
    "startup-s1": "S1-Done",
    "startup-s2": "S2-Done",
    "startup-s3": "S3-Done",
    "module-s1": "S1-Done",
}


def _get_free_port() -> int:
    """Ask the OS for an available local TCP port."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
        candidate.bind(("127.0.0.1", 0))
        return int(candidate.getsockname()[1])


def _overlay_runtime_fixtures(runtime_root: Path) -> None:
    """Copy runtime-specific acceptance fixtures into the temp data root."""

    if not RUNTIME_ROOT.exists():
        return

    for source in RUNTIME_ROOT.rglob("*"):
        if not source.is_file():
            continue
        target = runtime_root / source.relative_to(RUNTIME_ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _wait_for_wiremock(port: int) -> None:
    """Block until the WireMock admin endpoint is reachable."""

    deadline = time.monotonic() + 30.0
    url = f"http://127.0.0.1:{port}/__admin/mappings"
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as response:
                if response.status == WIREMOCK_READY_STATUS:
                    return
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last_error = exc
            time.sleep(0.5)
    raise TimeoutError from last_error


def _deactivate_wiremock_scenarios(port: int, active_scenario: str) -> None:
    """Advance all inactive WireMock combat scenarios to their terminal state.

    Prevents stubs from non-active scenarios from matching requests when
    multiple combat scenario stub sets coexist in the same WireMock instance.
    WireMock only accepts states declared by existing stubs; terminal states
    (e.g. S1-Done, S2-Done) have no matching stubs, so advancing to them
    effectively disables that scenario for the duration of the test.
    """
    for scenario, terminal_state in _WIREMOCK_SCENARIO_TERMINAL_STATE.items():
        if scenario == active_scenario:
            continue
        url = f"http://127.0.0.1:{port}/__admin/scenarios/{scenario}/state"
        payload = json.dumps({"state": terminal_state}).encode()
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        try:
            with urllib.request.urlopen(req, timeout=5.0):
                pass
        except urllib.error.HTTPError as exc:
            if exc.code != _HTTP_NOT_FOUND:
                raise
            # 404 means the scenario does not exist yet; WireMock creates
            # scenario state on the first stub match, not on registration.


@pytest.fixture
def runtime_data_root(tmp_path: Path) -> Path:
    """Prepare an isolated runtime data root for each acceptance scenario."""

    runtime_root = tmp_path / "runtime-data"
    shutil.copytree(EXAMPLES_ROOT, runtime_root)
    _overlay_runtime_fixtures(runtime_root)

    player_path = runtime_root / "state" / "actors" / "player.json"
    player = json.loads(player_path.read_text())
    player["hp_current"] = 12
    player_path.write_text(json.dumps(player, indent=2, sort_keys=True) + "\n")

    event_log_path = runtime_root / "memory" / "event_log.jsonl"
    event_log_path.parent.mkdir(parents=True, exist_ok=True)
    event_log_path.write_text("")
    return runtime_root


@pytest.fixture
def compose_environment(
    runtime_data_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, str]:
    """Build the environment for the Docker Compose acceptance run."""

    env = os.environ.copy()
    env["COMPOSE_PROJECT_NAME"] = f"campaignnarrator-{tmp_path.name}"
    env["RUNTIME_DATA_ROOT"] = str(runtime_data_root)
    env["WIREMOCK_PORT"] = str(_get_free_port())
    env.setdefault("OPENAI_API_KEY", "fake-openai-api-key")
    env.setdefault("OPENAI_MODEL", "gpt-5.4")
    env.setdefault("OPENAI_BASE_URL", "http://wiremock:8080/v1")
    env.setdefault("CAMPAIGNNARRATOR_DICE_SEED", "7")
    # Acceptance tests always target WireMock (OpenAI-compatible API)
    env["LLM_PROVIDER"] = "openai"
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", env["COMPOSE_PROJECT_NAME"])
    monkeypatch.setenv("RUNTIME_DATA_ROOT", env["RUNTIME_DATA_ROOT"])
    monkeypatch.setenv("WIREMOCK_PORT", env["WIREMOCK_PORT"])
    monkeypatch.setenv("OPENAI_API_KEY", env["OPENAI_API_KEY"])
    monkeypatch.setenv("OPENAI_MODEL", env["OPENAI_MODEL"])
    monkeypatch.setenv("OPENAI_BASE_URL", env["OPENAI_BASE_URL"])
    monkeypatch.setenv("CAMPAIGNNARRATOR_DICE_SEED", env["CAMPAIGNNARRATOR_DICE_SEED"])
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    env["EMBEDDING_PROVIDER"] = "stub"
    env["LANCEDB_PATH"] = "/runtime/data/memory/lancedb"
    monkeypatch.setenv("EMBEDDING_PROVIDER", "stub")
    monkeypatch.setenv("LANCEDB_PATH", "/runtime/data/memory/lancedb")
    return env


@pytest.fixture
def docker_compose(
    compose_environment: dict[str, str],
) -> Callable[..., CompletedProcess[str]]:
    """Run docker compose commands against the acceptance stack."""

    def _run(*args: str) -> CompletedProcess[str]:
        return run(
            [
                "docker",
                "compose",
                "-f",
                str(PROJECT_ROOT / "docker-compose.acceptance.yml"),
                *args,
            ],
            cwd=PROJECT_ROOT,
            env=compose_environment,
            capture_output=True,
            text=True,
            check=False,
        )

    return _run


@pytest.fixture
def wiremock_stack(docker_compose, compose_environment: dict[str, str]):
    """Start the WireMock service for one acceptance scenario."""

    result = docker_compose("up", "-d", "wiremock")
    assert result.returncode == 0, result.stderr
    _wait_for_wiremock(int(compose_environment["WIREMOCK_PORT"]))
    build = docker_compose("build", "app")
    assert build.returncode == 0, build.stderr
    yield
    docker_compose("down", "--volumes", "--remove-orphans")


@given(
    parsers.parse(
        "the OpenAI API is configured for {scenario_name} on encounter {encounter_id}"
    ),
    target_fixture="encounter_config",
)
def configure_openai_api_for_scenario_with_encounter(
    scenario_name: str,
    encounter_id: str,
    request: pytest.FixtureRequest,
    runtime_data_root: Path,
    wiremock_stack: None,
) -> dict[str, str]:
    """Start the acceptance stack with a specific encounter ID."""

    request.node._encounter_scenario_name = scenario_name
    named_encounter = EXAMPLES_ROOT / "state" / "encounters" / f"{encounter_id}.json"
    if named_encounter.exists():
        active_path = runtime_data_root / "state" / "encounters" / "active.json"
        active_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(named_encounter, active_path)
    active_wiremock_scenario = _ENCOUNTER_TO_WIREMOCK_SCENARIO.get(scenario_name)
    if active_wiremock_scenario is not None:
        env: dict[str, str] = request.getfixturevalue("compose_environment")
        _deactivate_wiremock_scenarios(
            int(env["WIREMOCK_PORT"]),
            active_wiremock_scenario,
        )
    return {"scenario_name": scenario_name, "encounter_id": encounter_id}


@given(
    # The negative lookahead (?!.*\bon encounter\b) prevents this step from
    # matching any step text that contains "on encounter", which would otherwise
    # create an ambiguous match with configure_openai_api_for_scenario_with_encounter
    # above. If you add new scenario names containing "on encounter", use the
    # encounter-specific step instead.
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
    """Start the acceptance stack and deactivate all scenario-based WireMock stubs.

    Encounter-loop tests that do not exercise a named combat scenario must advance
    all scenario stubs to their terminal states.  Otherwise the combat-s* stubs
    (which match on the PLAYER_INTENT_INSTRUCTIONS system prompt) will shadow the
    decision-* stubs during the first player-intent classification call.
    """
    request.node._encounter_scenario_name = scenario_name
    env: dict[str, str] = request.getfixturevalue("compose_environment")
    _deactivate_wiremock_scenarios(int(env["WIREMOCK_PORT"]), "")
    return {"scenario_name": scenario_name, "encounter_id": "goblin-camp"}


@when(
    "the player runs the encounter with scripted input:",
    target_fixture="cli_result",
)
def run_encounter_with_scripted_input(
    compose_environment: dict[str, str],
    encounter_config: dict[str, str],
    request: pytest.FixtureRequest,
    wiremock_stack: None,
    docstring: str = "",
) -> CompletedProcess[str]:
    """Run the production CLI through Docker Compose with scripted stdin."""

    request.node._encounter_scenario_name = encounter_config["scenario_name"]
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
            encounter_config["encounter_id"],
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


_STARTUP_SCENARIO_TO_WIREMOCK: dict[str, str] = {
    "startup-s1": "startup-s1",
    "startup-s2": "startup-s2",
    "startup-s3": "startup-s3",
}

_STARTUP_FIXTURE_DIR: dict[str, str] = {
    "startup-s1": "new-player",
    "startup-s2": "returning-with-campaign",
    "startup-s3": "returning-without-campaign",
}

STARTUP_FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "startup"
MODULE_FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "module"


@given(
    parsers.parse("the module has a completed encounter for scenario {scenario_name}"),
    target_fixture="startup_config",
)
def module_has_completed_encounter(
    scenario_name: str,
    runtime_data_root: Path,
    wiremock_stack: None,
    request: pytest.FixtureRequest,
) -> dict[str, str]:
    """Set up a module with a completed active encounter for progression testing."""
    fixture_dir = MODULE_FIXTURE_ROOT / scenario_name
    _copy_fixture_tree(fixture_dir, runtime_data_root)
    env: dict[str, str] = request.getfixturevalue("compose_environment")
    _deactivate_wiremock_scenarios(int(env["WIREMOCK_PORT"]), scenario_name)
    return {"scenario_name": scenario_name}


@given(
    parsers.parse("the game state is empty for scenario {scenario_name}"),
    target_fixture="startup_config",
)
def game_state_empty(
    scenario_name: str,
    runtime_data_root: Path,
    wiremock_stack: None,
    request: pytest.FixtureRequest,
) -> dict[str, str]:
    """Set up an empty state (no player, no campaign) for the startup flow."""
    state_dir = runtime_data_root / "state"
    if state_dir.exists():
        shutil.rmtree(state_dir)
    state_dir.mkdir(parents=True)

    wiremock_scenario = _STARTUP_SCENARIO_TO_WIREMOCK[scenario_name]
    env: dict[str, str] = request.getfixturevalue("compose_environment")
    _deactivate_wiremock_scenarios(int(env["WIREMOCK_PORT"]), wiremock_scenario)
    return {"scenario_name": scenario_name}


@given(
    parsers.parse("the game state has a saved campaign for scenario {scenario_name}"),
    target_fixture="startup_config",
)
def game_state_with_campaign(
    scenario_name: str,
    runtime_data_root: Path,
    wiremock_stack: None,
    request: pytest.FixtureRequest,
) -> dict[str, str]:
    """Set up player + campaign + active encounter for returning-player scenario."""
    fixture_dir = STARTUP_FIXTURE_ROOT / _STARTUP_FIXTURE_DIR[scenario_name]
    _copy_fixture_tree(fixture_dir, runtime_data_root)
    wiremock_scenario = _STARTUP_SCENARIO_TO_WIREMOCK[scenario_name]
    env: dict[str, str] = request.getfixturevalue("compose_environment")
    _deactivate_wiremock_scenarios(int(env["WIREMOCK_PORT"]), wiremock_scenario)
    return {"scenario_name": scenario_name}


_GIVEN_PLAYER_NO_CAMPAIGN = (
    "the game state has a player but no campaign for scenario {scenario_name}"
)


@given(
    parsers.parse(_GIVEN_PLAYER_NO_CAMPAIGN),
    target_fixture="startup_config",
)
def game_state_player_no_campaign(
    scenario_name: str,
    runtime_data_root: Path,
    wiremock_stack: None,
    request: pytest.FixtureRequest,
) -> dict[str, str]:
    """Set up player-only state (no campaign) for returning-without-campaign."""
    fixture_dir = STARTUP_FIXTURE_ROOT / _STARTUP_FIXTURE_DIR[scenario_name]
    _copy_fixture_tree(fixture_dir, runtime_data_root)
    wiremock_scenario = _STARTUP_SCENARIO_TO_WIREMOCK[scenario_name]
    env: dict[str, str] = request.getfixturevalue("compose_environment")
    _deactivate_wiremock_scenarios(int(env["WIREMOCK_PORT"]), wiremock_scenario)
    return {"scenario_name": scenario_name}


def _copy_fixture_tree(fixture_dir: Path, runtime_data_root: Path) -> None:
    """Copy fixture files from fixture_dir into the runtime data root."""
    if not fixture_dir.exists():
        return
    for source in fixture_dir.rglob("*"):
        if not source.is_file():
            continue
        target = runtime_data_root / source.relative_to(fixture_dir)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


@when(
    "the player runs the game with scripted input:",
    target_fixture="cli_result",
)
def run_game_with_scripted_input(
    compose_environment: dict[str, str],
    startup_config: dict[str, str],
    wiremock_stack: None,
    docstring: str = "",
) -> CompletedProcess[str]:
    """Run the production CLI (no --encounter-id) with scripted stdin."""
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
        ],
        input=docstring,
        text=True,
        capture_output=True,
        timeout=90,
        env=compose_environment,
        cwd=PROJECT_ROOT,
        check=False,
    )
    assert completed_process.returncode == 0, completed_process.stderr
    return completed_process
