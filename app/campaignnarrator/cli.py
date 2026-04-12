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
from campaignnarrator.orchestrator import CampaignOrchestrator
from campaignnarrator.repositories.compendium_repository import CompendiumRepository
from campaignnarrator.repositories.memory_repository import MemoryRepository
from campaignnarrator.repositories.rules_repository import RulesRepository
from campaignnarrator.repositories.state_repository import StateRepository
from campaignnarrator.tools.dice import roll as roll_dice


def _build_application_graph(data_root: Path) -> CampaignOrchestrator:
    """Build the production application graph from the configured data root."""

    adapter = PydanticAIAdapter.from_env()
    rules_repository = RulesRepository(data_root / "rules")
    compendium_repository = CompendiumRepository(data_root / "compendium")
    state_repository = StateRepository.from_default_encounter()
    memory_repository = MemoryRepository(data_root / "memory")
    rules_agent = RulesAgent(
        adapter=adapter,
        rules_repository=rules_repository,
        compendium_repository=compendium_repository,
    )
    narrator_agent = NarratorAgent(adapter=adapter)
    return CampaignOrchestrator(
        state_repository=state_repository,
        rules_agent=rules_agent,
        memory_repository=memory_repository,
        narrator_agent=narrator_agent,
        roll_dice=roll_dice,
        decision_adapter=adapter,
    )


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

    orchestrator = _build_application_graph(args.data_root)
    result = orchestrator.run_encounter(
        encounter_id=args.encounter_id,
        player_inputs=stdin,
    )
    stdout.write(result.output_text)
    if not result.output_text.endswith("\n"):
        stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
