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

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures"
EXAMPLES_ROOT = FIXTURE_ROOT / "examples"
RUNTIME_ROOT = FIXTURE_ROOT / "runtime"


WIREMOCK_READY_STATUS = 200


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
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", env["COMPOSE_PROJECT_NAME"])
    monkeypatch.setenv("RUNTIME_DATA_ROOT", env["RUNTIME_DATA_ROOT"])
    monkeypatch.setenv("WIREMOCK_PORT", env["WIREMOCK_PORT"])
    monkeypatch.setenv("OPENAI_API_KEY", env["OPENAI_API_KEY"])
    monkeypatch.setenv("OPENAI_MODEL", env["OPENAI_MODEL"])
    monkeypatch.setenv("OPENAI_BASE_URL", env["OPENAI_BASE_URL"])
    monkeypatch.setenv("CAMPAIGNNARRATOR_DICE_SEED", env["CAMPAIGNNARRATOR_DICE_SEED"])
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
