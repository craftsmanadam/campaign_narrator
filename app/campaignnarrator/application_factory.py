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
from campaignnarrator.orchestrators.application_orchestrator import (
    ApplicationOrchestrator,
)
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
    OrchestratorTools,
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
from campaignnarrator.settings import Settings
from campaignnarrator.terminal_io import TerminalIO
from campaignnarrator.tools.dice import roll as roll_dice


@dataclass(frozen=True)
class ApplicationGraph:
    """Container for all wired-up application objects."""

    game_orchestrator: _LazyGameOrchestrator
    application_orchestrator: ApplicationOrchestrator


@dataclass(frozen=True)
class _Repositories:
    """All repositories, built in one place."""

    actor: ActorRepository
    encounter: EncounterRepository
    campaign: CampaignRepository
    module: ModuleRepository
    rules: RulesRepository
    compendium: CompendiumRepository
    memory: MemoryRepository
    template: CharacterTemplateRepository
    state: StateRepository


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
        actor_repository: ActorRepository,
        campaign_repository: CampaignRepository,
        character_creation_orchestrator: CharacterCreationOrchestrator,
        make_campaign_creation: Callable[[ActorState], CampaignCreationOrchestrator],
        make_startup: Callable[[ActorState], StartupOrchestrator],
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

        actor = ActorRepository(self._data_root / "state")
        encounter = EncounterRepository(self._data_root / "state")
        campaign = CampaignRepository(self._data_root)
        module = ModuleRepository(self._data_root)
        rules = RulesRepository(self._data_root / "rules")
        compendium = CompendiumRepository(self._data_root / "compendium")
        memory = MemoryRepository(
            self._data_root / "memory",
            embedding_adapter=embedding_adapter,
            lancedb_path=lancedb_path,
        )
        template = CharacterTemplateRepository(self._data_root / "character_templates")
        state = StateRepository(
            actor_repo=actor,
            encounter_repo=encounter,
            compendium=compendium,
        )
        return _Repositories(
            actor=actor,
            encounter=encounter,
            campaign=campaign,
            module=module,
            rules=rules,
            compendium=compendium,
            memory=memory,
            template=template,
            state=state,
        )

    def _build_agents(self, repos: _Repositories) -> _Agents:
        adapter = PydanticAIAdapter.from_env()
        return _Agents(
            rules=RulesAgent(
                adapter=adapter,
                rules_repository=repos.rules,
                compendium_repository=repos.compendium,
            ),
            narrator=NarratorAgent(
                adapter=adapter,
                personality=NARRATOR_PERSONALITY,
                memory_repository=repos.memory,
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
                memory=repos.memory,
            ),
            agents=OrchestratorAgents(
                rules=agents.rules,
                narrator=agents.narrator,
            ),
            tools=OrchestratorTools(roll_dice=roll_dice),
            io=io,
            adapter=agents.narrator.adapter,
        )

        encounter_planner_orchestrator = EncounterPlannerOrchestrator(
            repositories=EncounterPlannerOrchestratorRepositories(
                module=repos.module,
                encounter=repos.encounter,
                memory=repos.memory,
                compendium=repos.compendium,
            ),
            agents=EncounterPlannerOrchestratorAgents(
                planner=EncounterPlannerAgent(adapter=agents.narrator.adapter),
            ),
        )

        module_orchestrator = ModuleOrchestrator(
            io=io,
            repositories=ModuleOrchestratorRepositories(
                campaign=repos.campaign,
                module=repos.module,
                encounter=repos.encounter,
                actor=repos.actor,
                memory=repos.memory,
                compendium=repos.compendium,
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
                    campaign=repos.campaign,
                    module=repos.module,
                    memory=repos.memory,
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
                campaign_repository=repos.campaign,
                interpreter=agents.startup_interpreter,
                campaign_creation_orchestrator=_make_campaign_creation(player),
                module_orchestrator=module_orchestrator,
            )

        char_creation = CharacterCreationOrchestrator(
            io=io,
            repositories=CharacterCreationRepositories(
                actor=repos.actor,
                template=repos.template,
                memory=repos.memory,
            ),
            agents=CharacterCreationAgents(
                backstory=agents.backstory,
            ),
        )

        game_orchestrator = _LazyGameOrchestrator(
            actor_repository=repos.actor,
            campaign_repository=repos.campaign,
            character_creation_orchestrator=char_creation,
            make_campaign_creation=_make_campaign_creation,
            make_startup=_make_startup,
        )

        application_orchestrator = ApplicationOrchestrator(
            encounter_orchestrator=encounter_orchestrator
        )

        return ApplicationGraph(
            game_orchestrator=game_orchestrator,
            application_orchestrator=application_orchestrator,
        )
