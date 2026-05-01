"""Startup orchestrator: handles returning-player decision tree."""

from __future__ import annotations

from campaignnarrator.agents.startup_interpreter_agent import StartupInterpreterAgent
from campaignnarrator.domain.models import ActorState, PlayerIO
from campaignnarrator.orchestrators.campaign_creation_orchestrator import (
    CampaignCreationOrchestrator,
)
from campaignnarrator.orchestrators.module_orchestrator import ModuleOrchestrator
from campaignnarrator.repositories.game_state_repository import GameStateRepository
from campaignnarrator.repositories.narrative_memory_repository import (
    NarrativeMemoryRepository,
)

_DESTRUCTION_WARNING = (
    "\nStarting a new campaign will permanently destroy your current story. "
    "The threads of your past will be lost to the void. "
    "\nAre you certain? "
    "(type 'yes, destroy it' to confirm, or anything else to cancel)\n"
)


class StartupOrchestrator:
    """Route returning players to the right flow based on their stated intent."""

    def __init__(
        self,
        *,
        io: PlayerIO,
        player: ActorState,
        narrative_repository: NarrativeMemoryRepository,
        game_state_repository: GameStateRepository,
        interpreter: StartupInterpreterAgent,
        campaign_creation_orchestrator: CampaignCreationOrchestrator,
        module_orchestrator: ModuleOrchestrator,
    ) -> None:
        self._io = io
        self._player = player
        self._narrative_repo = narrative_repository
        self._game_state_repo = game_state_repository
        self._interpreter = interpreter
        self._campaign_creation_orchestrator = campaign_creation_orchestrator
        self._module_orchestrator = module_orchestrator

    def handle_returning_with_campaign(self) -> None:
        """Greet the player, offer load-or-new, route accordingly."""
        campaign = self._game_state_repo.load().campaign
        if campaign is None:
            return

        self._io.display(
            f"\nWelcome back, {self._player.name}. "
            f"Your campaign '{campaign.name}' awaits. "
            "\nWould you like to load it, or start a new campaign?\n"
        )
        raw = self._io.prompt("> ")
        intent = self._interpreter.interpret(raw, has_campaign=True)

        if intent == "load_campaign":
            self._module_orchestrator.run(campaign=campaign)
        elif intent == "new_campaign":
            self._io.display(_DESTRUCTION_WARNING)
            confirm_raw = self._io.prompt("> ")
            confirm_intent = self._interpreter.interpret(confirm_raw, has_campaign=True)
            if confirm_intent == "confirm_destroy":
                self._destroy_campaign(campaign.campaign_id)
                self._campaign_creation_orchestrator.run()
        # abort or unrecognised: do nothing

    def handle_returning_without_campaign(self) -> None:
        """Player has a character but no campaign — go straight to campaign creation."""
        self._io.display(
            f"\nWelcome back, {self._player.name}. "
            "You have no active campaign. Let us begin a new story.\n"
        )
        self._campaign_creation_orchestrator.run()

    def _destroy_campaign(self, campaign_id: str) -> None:
        """Delete structured state and clear narrative memory for a destroyed campaign.

        Always calls both — never one without the other. Structured state is deleted
        first so the campaign file is gone before narrative history is cleared.
        """
        self._game_state_repo.destroy_campaign(campaign_id)
        self._narrative_repo.clear_narrative(campaign_id)
