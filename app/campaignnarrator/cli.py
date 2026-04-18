"""Command-line entrypoint for Campaign Narrator."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from campaignnarrator.adapters.pydantic_ai_adapter import PydanticAIAdapter
from campaignnarrator.agents.backstory_agent import BackstoryAgent
from campaignnarrator.agents.campaign_generator_agent import CampaignGeneratorAgent
from campaignnarrator.agents.character_interpreter_agent import (
    CharacterInterpreterAgent,
)
from campaignnarrator.agents.module_generator_agent import ModuleGeneratorAgent
from campaignnarrator.agents.narrator_agent import NarratorAgent
from campaignnarrator.agents.rules_agent import RulesAgent
from campaignnarrator.agents.startup_interpreter_agent import StartupInterpreterAgent
from campaignnarrator.domain.models import ActorState
from campaignnarrator.orchestrators.application_orchestrator import (
    ApplicationOrchestrator,
)
from campaignnarrator.orchestrators.campaign_creation_orchestrator import (
    CampaignCreationOrchestrator,
)
from campaignnarrator.orchestrators.character_creation_orchestrator import (
    CharacterCreationOrchestrator,
)
from campaignnarrator.orchestrators.encounter_orchestrator import (
    EncounterOrchestrator,
    OrchestratorAgents,
    OrchestratorRepositories,
    OrchestratorTools,
)
from campaignnarrator.orchestrators.startup_orchestrator import StartupOrchestrator
from campaignnarrator.repositories.actor_repository import ActorRepository
from campaignnarrator.repositories.campaign_repository import CampaignRepository
from campaignnarrator.repositories.character_template_repository import (
    CharacterTemplateRepository,
)
from campaignnarrator.repositories.compendium_repository import CompendiumRepository
from campaignnarrator.repositories.encounter_repository import EncounterRepository
from campaignnarrator.repositories.memory_repository import MemoryRepository
from campaignnarrator.repositories.module_repository import ModuleRepository
from campaignnarrator.repositories.rules_repository import RulesRepository
from campaignnarrator.repositories.state_repository import StateRepository
from campaignnarrator.tools.dice import roll as roll_dice

_DEFAULT_NARRATOR_PERSONALITY: str = (
    "You are a seasoned dungeon master with a flair for the dramatic. "
    "You favor vivid sensory detail, dry wit, and speak directly to the player "
    "in second person, present tense. "
    "Keep narration concise — two to four sentences unless the scene demands more."
)


@dataclass(frozen=True)
class _ApplicationGraph:
    """Container for all wired-up application objects."""

    game_orchestrator: _LazyGameOrchestrator
    application_orchestrator: ApplicationOrchestrator


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


class _LazyGameOrchestrator:
    """Builds player-dependent sub-orchestrators lazily, on first call to run()."""

    def __init__(
        self,
        *,
        actor_repository: ActorRepository,
        campaign_repository: CampaignRepository,
        character_creation_orchestrator: CharacterCreationOrchestrator,
        make_campaign_creation: object,
        make_startup: object,
    ) -> None:
        self._actor_repo = actor_repository
        self._campaign_repo = campaign_repository
        self._character_creation_orchestrator = character_creation_orchestrator
        self._make_campaign_creation = make_campaign_creation
        self._make_startup = make_startup

    def run(self) -> None:
        """Detect game state and route to the appropriate sub-orchestrator."""
        try:
            player = self._actor_repo.load_player()
            player_exists = True
        except FileNotFoundError:
            player_exists = False
            player = None  # type: ignore[assignment]

        if not player_exists:
            player = self._character_creation_orchestrator.run()
            self._make_campaign_creation(player).run()
            return

        if self._campaign_repo.exists():
            self._make_startup(player).handle_returning_with_campaign()
        else:
            self._make_startup(player).handle_returning_without_campaign()


def _build_application_graph(
    data_root: Path, stdin: TextIO, stdout: TextIO
) -> _ApplicationGraph:
    """Build the production application graph from the configured data root."""

    adapter = PydanticAIAdapter.from_env()
    io = _TerminalIO(stdin=stdin, stdout=stdout)

    # --- Repositories ---
    actor_repo = ActorRepository(data_root / "state")
    encounter_repo = EncounterRepository(data_root / "state")
    campaign_repo = CampaignRepository(data_root)
    module_repo = ModuleRepository(data_root)
    rules_repository = RulesRepository(data_root / "rules")
    compendium_repository = CompendiumRepository(data_root / "compendium")
    memory_repository = MemoryRepository(data_root / "memory")
    template_repo = CharacterTemplateRepository(data_root / "character_templates")
    state_repository = StateRepository(
        actor_repo=actor_repo,
        encounter_repo=encounter_repo,
        compendium=compendium_repository,
    )

    # --- Agents ---
    rules_agent = RulesAgent(
        adapter=adapter,
        rules_repository=rules_repository,
        compendium_repository=compendium_repository,
    )
    narrator_agent = NarratorAgent(
        adapter=adapter, personality=_DEFAULT_NARRATOR_PERSONALITY
    )
    startup_interpreter = StartupInterpreterAgent(adapter=adapter)
    class_interpreter = CharacterInterpreterAgent(adapter=adapter)
    backstory_agent = BackstoryAgent(adapter=adapter)
    campaign_agent = CampaignGeneratorAgent(adapter=adapter)
    module_agent = ModuleGeneratorAgent(adapter=adapter)

    # --- Shared EncounterOrchestrator ---
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

    # --- New orchestrators (require a loaded player — built lazily via factories) ---
    # CampaignCreationOrchestrator and StartupOrchestrator need the player ActorState,
    # which may not exist yet. GameOrchestrator builds them after loading the player.
    # We pass factories (lambdas) so _LazyGameOrchestrator can build them on demand.
    def _make_campaign_creation(player: ActorState) -> CampaignCreationOrchestrator:
        return CampaignCreationOrchestrator(
            io=io,
            player=player,
            campaign_repository=campaign_repo,
            module_repository=module_repo,
            encounter_repository=encounter_repo,
            campaign_agent=campaign_agent,
            module_agent=module_agent,
            encounter_orchestrator=encounter_orchestrator,
        )

    def _make_startup(player: ActorState) -> StartupOrchestrator:
        campaign_creation = _make_campaign_creation(player)
        return StartupOrchestrator(
            io=io,
            player=player,
            campaign_repository=campaign_repo,
            interpreter=startup_interpreter,
            campaign_creation_orchestrator=campaign_creation,
            encounter_orchestrator=encounter_orchestrator,
        )

    char_creation = CharacterCreationOrchestrator(
        io=io,
        actor_repository=actor_repo,
        template_repository=template_repo,
        class_agent=class_interpreter,
        backstory_agent=backstory_agent,
    )

    game_orchestrator = _LazyGameOrchestrator(
        actor_repository=actor_repo,
        campaign_repository=campaign_repo,
        character_creation_orchestrator=char_creation,
        make_campaign_creation=_make_campaign_creation,
        make_startup=_make_startup,
    )

    application_orchestrator = ApplicationOrchestrator(
        encounter_orchestrator=encounter_orchestrator
    )

    return _ApplicationGraph(
        game_orchestrator=game_orchestrator,
        application_orchestrator=application_orchestrator,
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> int:
    """Parse CLI arguments and run the appropriate orchestrator."""

    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout

    parser = argparse.ArgumentParser(prog="campaignnarrator")
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument(
        "--encounter-id",
        default=None,
        help="(Legacy) Run a named encounter directly, bypassing the startup flow.",
    )
    args = parser.parse_args(argv)

    graph = _build_application_graph(args.data_root, stdin=stdin, stdout=stdout)

    if args.encounter_id:
        # Legacy bypass: used by combat acceptance tests
        result = graph.application_orchestrator.run_encounter(
            encounter_id=args.encounter_id
        )
        stdout.write(result.output_text)
        if not result.output_text.endswith("\n"):
            stdout.write("\n")
    else:
        graph.game_orchestrator.run()

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
