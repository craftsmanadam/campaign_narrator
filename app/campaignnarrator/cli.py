"""Command-line entrypoint for the Campaign Narrator steel thread."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from campaignnarrator.adapters.pydantic_ai_adapter import PydanticAIAdapter
from campaignnarrator.agents.narrator_agent import NarratorAgent
from campaignnarrator.agents.rules_agent import RulesAgent
from campaignnarrator.orchestrators.application_orchestrator import (
    ApplicationOrchestrator,
)
from campaignnarrator.orchestrators.encounter_orchestrator import (
    EncounterOrchestrator,
    OrchestratorAgents,
    OrchestratorRepositories,
    OrchestratorTools,
)
from campaignnarrator.repositories.actor_repository import ActorRepository
from campaignnarrator.repositories.compendium_repository import CompendiumRepository
from campaignnarrator.repositories.encounter_repository import EncounterRepository
from campaignnarrator.repositories.memory_repository import MemoryRepository
from campaignnarrator.repositories.rules_repository import RulesRepository
from campaignnarrator.repositories.state_repository import StateRepository
from campaignnarrator.tools.dice import roll as roll_dice

_DEFAULT_NARRATOR_PERSONALITY: str = (
    "You are a seasoned dungeon master with a flair for the dramatic. "
    "You favor vivid sensory detail, dry wit, and speak directly to the player "
    "in second person, present tense. "
    "Keep narration concise — two to four sentences unless the scene demands more."
)


class _TerminalIO:
    """PlayerIO implementation backed by stdin/stdout."""

    def __init__(self, stdin: TextIO, stdout: TextIO) -> None:
        self._stdin = stdin
        self._stdout = stdout

    def prompt(self, text: str) -> str:
        self._stdout.write(text)
        self._stdout.flush()
        return self._stdin.readline().rstrip("\n")

    def display(self, text: str) -> None:
        self._stdout.write(text + "\n")
        self._stdout.flush()


def _build_application_graph(
    data_root: Path, stdin: TextIO, stdout: TextIO
) -> ApplicationOrchestrator:
    """Build the production application graph from the configured data root."""

    adapter = PydanticAIAdapter.from_env()
    rules_repository = RulesRepository(data_root / "rules")
    compendium_repository = CompendiumRepository(data_root / "compendium")
    actor_repo = ActorRepository(data_root / "state")
    encounter_repo = EncounterRepository(data_root / "state")
    state_repository = StateRepository(
        actor_repo=actor_repo,
        encounter_repo=encounter_repo,
        compendium=compendium_repository,
    )
    memory_repository = MemoryRepository(data_root / "memory")
    rules_agent = RulesAgent(
        adapter=adapter,
        rules_repository=rules_repository,
        compendium_repository=compendium_repository,
    )
    narrator_agent = NarratorAgent(
        adapter=adapter, personality=_DEFAULT_NARRATOR_PERSONALITY
    )
    io = _TerminalIO(stdin=stdin, stdout=stdout)
    encounter_orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            state=state_repository,
            memory=memory_repository,
        ),
        agents=OrchestratorAgents(
            rules=rules_agent,
            narrator=narrator_agent,
        ),
        tools=OrchestratorTools(roll_dice=roll_dice),
        io=io,
        adapter=adapter,
    )
    return ApplicationOrchestrator(encounter_orchestrator=encounter_orchestrator)


def main(
    argv: Sequence[str] | None = None,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> int:
    """Parse CLI arguments, run the orchestrator, and print narration."""

    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout

    parser = argparse.ArgumentParser(prog="campaignnarrator")
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--encounter-id", default="goblin-camp")
    args = parser.parse_args(argv)

    orchestrator = _build_application_graph(args.data_root, stdin=stdin, stdout=stdout)
    result = orchestrator.run_encounter(encounter_id=args.encounter_id)
    stdout.write(result.output_text)
    if not result.output_text.endswith("\n"):
        stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
