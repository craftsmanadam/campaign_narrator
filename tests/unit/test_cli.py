"""Unit tests for the CLI entrypoint."""

from __future__ import annotations

from pathlib import Path

from campaignnarrator.cli import main
from campaignnarrator.domain.models import Narration


class _FakeOrchestrator:
    def __init__(self, narration: Narration) -> None:
        self.narration = narration
        self.calls: list[str] = []

    def run(self, player_input: str) -> Narration:
        self.calls.append(player_input)
        return self.narration


def test_cli_parses_arguments_and_prints_narration(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    """The CLI should route parsed input into the application graph and print text."""

    fake_orchestrator = _FakeOrchestrator(
        Narration(text="Talia regains 7 hit points.", audience="player")
    )
    builder_calls: list[Path] = []

    def _build_application_graph(data_root: Path) -> _FakeOrchestrator:
        builder_calls.append(data_root)
        return fake_orchestrator

    monkeypatch.setattr(
        "campaignnarrator.cli._build_application_graph",
        _build_application_graph,
    )

    exit_code = main(
        [
            "--input",
            "I drink my potion of healing",
            "--data-root",
            str(tmp_path),
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert builder_calls == [tmp_path]
    assert fake_orchestrator.calls == ["I drink my potion of healing"]
    assert captured.out == "Talia regains 7 hit points.\n"
