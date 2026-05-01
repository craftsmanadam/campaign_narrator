"""Application factory: builds the production wiring graph."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from campaignnarrator.adapters.embedding_adapter import (
    EmbeddingAdapter,
    OllamaEmbeddingAdapter,
    StubEmbeddingAdapter,
)
from campaignnarrator.adapters.pydantic_ai_adapter import PydanticAIAdapter
from campaignnarrator.agents.backstory_agent import BackstoryAgent
from campaignnarrator.agents.campaign_generator_agent import CampaignGeneratorAgent
from campaignnarrator.agents.encounter_planner_agent import EncounterPlannerAgent
from campaignnarrator.agents.module_generator_agent import ModuleGeneratorAgent
from campaignnarrator.agents.narrator_agent import NarratorAgent
from campaignnarrator.agents.prompts import NARRATOR_PERSONALITY
from campaignnarrator.agents.rules_agent import RulesAgent
from campaignnarrator.agents.startup_interpreter_agent import StartupInterpreterAgent
from campaignnarrator.domain.models import ActorState
from campaignnarrator.orchestrators.campaign_creation_orchestrator import (
    CampaignCreationAgents,
    CampaignCreationOrchestrator,
    CampaignCreationRepositories,
)
from campaignnarrator.orchestrators.character_creation_orchestrator import (
    CharacterCreationAgents,
    CharacterCreationOrchestrator,
    CharacterCreationRepositories,
)
from campaignnarrator.orchestrators.encounter_orchestrator import (
    EncounterOrchestrator,
    OrchestratorAgents,
    OrchestratorRepositories,
)
from campaignnarrator.orchestrators.encounter_planner_orchestrator import (
    EncounterPlannerOrchestrator,
    EncounterPlannerOrchestratorAgents,
    EncounterPlannerOrchestratorRepositories,
)
from campaignnarrator.orchestrators.module_orchestrator import (
    ModuleOrchestrator,
    ModuleOrchestratorAgents,
    ModuleOrchestratorRepositories,
)
from campaignnarrator.orchestrators.startup_orchestrator import StartupOrchestrator
from campaignnarrator.repositories.character_template_repository import (
    CharacterTemplateRepository,
)
from campaignnarrator.repositories.compendium_repository import CompendiumRepository
from campaignnarrator.repositories.game_state_repository import GameStateRepository
from campaignnarrator.repositories.narrative_memory_repository import (
    NarrativeMemoryRepository,
)
from campaignnarrator.repositories.player_repository import PlayerRepository
from campaignnarrator.settings import Settings
from campaignnarrator.terminal_io import TerminalIO


@dataclass(frozen=True)
class ApplicationGraph:
    """Container for all wired-up application objects."""

    game_orchestrator: _LazyGameOrchestrator


@dataclass(frozen=True)
class _Repositories:
    """All repositories, built in one place."""

    actor: PlayerRepository
    compendium: CompendiumRepository
    narrative: NarrativeMemoryRepository
    template: CharacterTemplateRepository
    game_state: GameStateRepository


@dataclass(frozen=True)
class _Agents:
    """All agents, built in one place."""

    rules: RulesAgent
    narrator: NarratorAgent
    startup_interpreter: StartupInterpreterAgent
    backstory: BackstoryAgent
    campaign_generator: CampaignGeneratorAgent
    module_generator: ModuleGeneratorAgent


class _LazyGameOrchestrator:
    """Builds player-dependent sub-orchestrators lazily, on first call to run()."""

    def __init__(
        self,
        *,
        actor_repository: PlayerRepository,
        game_state_repository: GameStateRepository,
        narrative_repository: NarrativeMemoryRepository,
        character_creation_orchestrator: CharacterCreationOrchestrator,
        make_campaign_creation: Callable[[ActorState], CampaignCreationOrchestrator],
        make_startup: Callable[[ActorState], StartupOrchestrator],
    ) -> None:
        self._actor_repo = actor_repository
        self._game_state_repo = game_state_repository
        self._narrative_repo = narrative_repository
        self._character_creation_orchestrator = character_creation_orchestrator
        self._make_campaign_creation = make_campaign_creation
        self._make_startup = make_startup

    def save_state(self) -> None:
        """Flush in-memory session state to disk."""
        self._narrative_repo.persist()

    def run(self) -> None:
        """Detect game state and route to the appropriate sub-orchestrator."""
        try:
            player = self._actor_repo.load()
            player_exists = True
        except FileNotFoundError:
            player_exists = False
            player = None  # type: ignore[assignment]

        if not player_exists:
            player = self._character_creation_orchestrator.run()
            self._make_campaign_creation(player).run()
            return

        if self._game_state_repo.load().campaign is not None:
            self._make_startup(player).handle_returning_with_campaign()
        else:
            self._make_startup(player).handle_returning_without_campaign()


def _build_embedding_adapter(settings: Settings) -> EmbeddingAdapter:
    """Construct the correct EmbeddingAdapter from settings."""
    if settings.embedding_provider == "stub":
        return StubEmbeddingAdapter()
    return OllamaEmbeddingAdapter(
        base_url=settings.embedding_base_url,
        model=settings.embedding_model,
    )


class ApplicationFactory:
    """Build the production application graph from a configured data root.

    Three explicit phases: _build_repositories(), _build_agents(repos),
    _build_graph(repos, agents).
    """

    def __init__(self, data_root: Path, stdin: TextIO, stdout: TextIO) -> None:
        self._data_root = data_root
        self._stdin = stdin
        self._stdout = stdout

    def build(self) -> ApplicationGraph:
        """Construct and return the fully wired application graph."""
        repos = self._build_repositories()
        agents = self._build_agents(repos)
        return self._build_graph(repos, agents)

    def _build_repositories(self) -> _Repositories:
        settings = Settings()
        embedding_adapter = _build_embedding_adapter(settings)
        lancedb_path = (
            Path(settings.lancedb_path)
            if settings.lancedb_path
            else self._data_root / "memory" / "lancedb"
        )

        actor = PlayerRepository(self._data_root)
        compendium = CompendiumRepository(self._data_root / "compendium")
        game_state = GameStateRepository(
            state_path=self._data_root / "state" / "game_state.json",
            player_repo=actor,
        )
        memory = NarrativeMemoryRepository(
            self._data_root / "memory",
            embedding_adapter=embedding_adapter,
            lancedb_path=lancedb_path,
        )
        template = CharacterTemplateRepository(self._data_root / "character_templates")
        return _Repositories(
            actor=actor,
            compendium=compendium,
            narrative=memory,
            template=template,
            game_state=game_state,
        )

    def _build_agents(self, repos: _Repositories) -> _Agents:
        adapter = PydanticAIAdapter.from_env()
        return _Agents(
            rules=RulesAgent(
                adapter=adapter,
                compendium_repository=repos.compendium,
            ),
            narrator=NarratorAgent(
                adapter=adapter,
                personality=NARRATOR_PERSONALITY,
                memory_repository=repos.narrative,
            ),
            startup_interpreter=StartupInterpreterAgent(adapter=adapter),
            backstory=BackstoryAgent(adapter=adapter),
            campaign_generator=CampaignGeneratorAgent(adapter=adapter),
            module_generator=ModuleGeneratorAgent(adapter=adapter),
        )

    def _build_graph(self, repos: _Repositories, agents: _Agents) -> ApplicationGraph:
        io = TerminalIO(stdin=self._stdin, stdout=self._stdout)

        encounter_orchestrator = EncounterOrchestrator(
            repositories=OrchestratorRepositories(
                memory=repos.narrative,
                game_state=repos.game_state,
            ),
            agents=OrchestratorAgents(
                rules=agents.rules,
                narrator=agents.narrator,
            ),
            io=io,
            adapter=agents.narrator.adapter,
        )

        encounter_planner_orchestrator = EncounterPlannerOrchestrator(
            repositories=EncounterPlannerOrchestratorRepositories(
                narrative=repos.narrative,
                compendium=repos.compendium,
                game_state=repos.game_state,
            ),
            agents=EncounterPlannerOrchestratorAgents(
                planner=EncounterPlannerAgent(adapter=agents.narrator.adapter),
            ),
        )

        module_orchestrator = ModuleOrchestrator(
            io=io,
            repositories=ModuleOrchestratorRepositories(
                narrative=repos.narrative,
                compendium=repos.compendium,
                game_state=repos.game_state,
            ),
            agents=ModuleOrchestratorAgents(
                narrator=agents.narrator,
                module_generator=agents.module_generator,
                encounter_planner=encounter_planner_orchestrator,
            ),
            encounter_orchestrator=encounter_orchestrator,
        )

        def _make_campaign_creation(player: ActorState) -> CampaignCreationOrchestrator:
            return CampaignCreationOrchestrator(
                io=io,
                player=player,
                repositories=CampaignCreationRepositories(
                    narrative=repos.narrative,
                    game_state=repos.game_state,
                ),
                agents=CampaignCreationAgents(
                    campaign_generator=agents.campaign_generator,
                    module_generator=agents.module_generator,
                ),
                module_orchestrator=module_orchestrator,
            )

        def _make_startup(player: ActorState) -> StartupOrchestrator:
            return StartupOrchestrator(
                io=io,
                player=player,
                narrative_repository=repos.narrative,
                game_state_repository=repos.game_state,
                interpreter=agents.startup_interpreter,
                campaign_creation_orchestrator=_make_campaign_creation(player),
                module_orchestrator=module_orchestrator,
            )

        char_creation = CharacterCreationOrchestrator(
            io=io,
            repositories=CharacterCreationRepositories(
                actor=repos.actor,
                template=repos.template,
                memory=repos.narrative,
            ),
            agents=CharacterCreationAgents(
                backstory=agents.backstory,
            ),
        )

        game_orchestrator = _LazyGameOrchestrator(
            actor_repository=repos.actor,
            game_state_repository=repos.game_state,
            narrative_repository=repos.narrative,
            character_creation_orchestrator=char_creation,
            make_campaign_creation=_make_campaign_creation,
            make_startup=_make_startup,
        )

        return ApplicationGraph(game_orchestrator=game_orchestrator)
