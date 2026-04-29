"""Top-level game orchestrator: detects state and routes to the right flow."""

from __future__ import annotations

from campaignnarrator.orchestrators.campaign_creation_orchestrator import (
    CampaignCreationOrchestrator,
)
from campaignnarrator.orchestrators.character_creation_orchestrator import (
    CharacterCreationOrchestrator,
)
from campaignnarrator.orchestrators.startup_orchestrator import StartupOrchestrator
from campaignnarrator.repositories.campaign_repository import CampaignRepository
from campaignnarrator.repositories.player_repository import PlayerRepository


class GameOrchestrator:
    """Route startup flow based on what state exists on disk."""

    def __init__(
        self,
        *,
        actor_repository: PlayerRepository,
        campaign_repository: CampaignRepository,
        character_creation_orchestrator: CharacterCreationOrchestrator,
        campaign_creation_orchestrator: CampaignCreationOrchestrator,
        startup_orchestrator: StartupOrchestrator,
    ) -> None:
        self._actor_repo = actor_repository
        self._campaign_repo = campaign_repository
        self._character_creation_orchestrator = character_creation_orchestrator
        self._campaign_creation_orchestrator = campaign_creation_orchestrator
        self._startup_orchestrator = startup_orchestrator

    def run(self) -> None:
        """Detect game state and delegate to the appropriate sub-orchestrator."""
        try:
            self._actor_repo.load()
            player_exists = True
        except FileNotFoundError:
            player_exists = False

        if not player_exists:
            self._character_creation_orchestrator.run()
            self._campaign_creation_orchestrator.run()
            return

        if self._campaign_repo.exists():
            self._startup_orchestrator.handle_returning_with_campaign()
        else:
            self._startup_orchestrator.handle_returning_without_campaign()
