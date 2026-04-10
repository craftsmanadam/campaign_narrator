"""Command-line entrypoint for the Campaign Narrator steel thread."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from campaignnarrator.adapters.openai_adapter import OpenAIAdapter
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

    adapter = OpenAIAdapter.from_env()
    rules_repository = RulesRepository(data_root / "rules")
    compendium_repository = CompendiumRepository(data_root / "compendium")
    state_repository = StateRepository(data_root / "state")
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
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Parse CLI arguments, run the orchestrator, and print narration."""

    parser = argparse.ArgumentParser(prog="campaignnarrator")
    parser.add_argument("--input", required=True)
    parser.add_argument("--data-root", required=True, type=Path)
    args = parser.parse_args(argv)

    orchestrator = _build_application_graph(args.data_root)
    narration = orchestrator.run(args.input)
    print(narration.text)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
