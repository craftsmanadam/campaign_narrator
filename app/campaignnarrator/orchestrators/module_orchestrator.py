"""Module encounter loop orchestrator."""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace

from campaignnarrator.agents.module_generator_agent import ModuleGeneratorAgent
from campaignnarrator.agents.narrator_agent import NarratorAgent
from campaignnarrator.domain.models import (
    ActorState,
    CampaignState,
    EncounterPhase,
    EncounterState,
    EncounterTransition,
    MilestoneAchieved,
    ModuleState,
    PlayerIO,
    get_player,
)
from campaignnarrator.orchestrators.encounter_orchestrator import EncounterOrchestrator
from campaignnarrator.orchestrators.encounter_planner_orchestrator import (
    EncounterPlannerOrchestrator,
)
from campaignnarrator.repositories.compendium_repository import CompendiumRepository
from campaignnarrator.repositories.game_state_repository import GameStateRepository
from campaignnarrator.repositories.narrative_memory_repository import (
    NarrativeMemoryRepository,
)

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModuleOrchestratorRepositories:
    """All repositories required by ModuleOrchestrator."""

    narrative: NarrativeMemoryRepository
    compendium: CompendiumRepository
    game_state: GameStateRepository


@dataclass(frozen=True)
class ModuleOrchestratorAgents:
    """All agents required by ModuleOrchestrator."""

    narrator: NarratorAgent
    module_generator: ModuleGeneratorAgent
    encounter_planner: EncounterPlannerOrchestrator


class ModuleOrchestrator:
    """Own the encounter loop within a module.

    Single caller of EncounterOrchestrator.run_encounter() and single writer
    of encounter summaries to NarrativeMemoryRepository. Callers pass campaign at run()
    time — not at construction — so this can be built eagerly by
    ApplicationFactory. The player is read from ActorRegistry each iteration.
    """

    _MAX_MODULE_DEPTH: int = 5

    def __init__(
        self,
        *,
        io: PlayerIO,
        repositories: ModuleOrchestratorRepositories,
        agents: ModuleOrchestratorAgents,
        encounter_orchestrator: EncounterOrchestrator,
    ) -> None:
        self._io = io
        self._repos = repositories
        self._agents = agents
        self._encounter_orchestrator = encounter_orchestrator
        self._game_state_repo = repositories.game_state

    def run(self, *, campaign: CampaignState) -> None:
        """Detect module state and run the encounter loop."""
        module = self._game_state_repo.load().module
        if module is None:
            return

        self._run_loop(campaign=campaign, module=module, depth=0)

    def _run_loop(
        self,
        *,
        campaign: CampaignState,
        module: ModuleState,
        depth: int = 0,
    ) -> None:
        """Inner loop: check encounter → archive if complete → prepare → run."""
        # Read player from registry each iteration so level-ups are reflected.
        gs = self._game_state_repo.load()
        player = get_player(gs.actor_registry, campaign.player_actor_id)

        active = gs.encounter

        # No active encounter — proceed to planning
        if active is None:
            self._prepare_and_run(
                campaign=campaign,
                player=player,
                module=module,
                depth=depth,
            )
            return

        # Encounter already complete — archive then prepare
        if active.phase == EncounterPhase.ENCOUNTER_COMPLETE:
            module, transition = self._archive_encounter(
                encounter=active, module=module, campaign=campaign
            )
            # Re-read player after archiving: encounter may have changed HP/conditions.
            player = get_player(
                self._game_state_repo.load().actor_registry,
                campaign.player_actor_id,
            )
            self._prepare_and_run(
                campaign=campaign,
                player=player,
                module=module,
                depth=depth,
                transition=transition,
            )
            return

        # Encounter in progress — resume it; output is displayed live during the loop
        self._encounter_orchestrator.run_encounter(
            encounter_id=active.encounter_id, campaign_id=campaign.campaign_id
        )

        # Reload from cache (not disk) to detect completion vs player quit
        reloaded = self._game_state_repo.load().encounter
        if reloaded is not None and reloaded.phase == EncounterPhase.ENCOUNTER_COMPLETE:
            module, transition = self._archive_encounter(
                encounter=reloaded, module=module, campaign=campaign
            )
            # Re-read player after archiving: encounter may have changed HP/conditions.
            player = get_player(
                self._game_state_repo.load().actor_registry,
                campaign.player_actor_id,
            )
            self._prepare_and_run(
                campaign=campaign,
                player=player,
                module=module,
                depth=depth,
                transition=transition,
            )
        # else: player quit — save state as-is and return

    def _archive_encounter(
        self,
        *,
        encounter: EncounterState,
        module: ModuleState,
        campaign: CampaignState,
    ) -> tuple[ModuleState, EncounterTransition]:
        """Summarize, store narrative, update module log, persist, clear."""
        summary = self._agents.narrator.summarize_encounter(encounter, module, campaign)
        self._repos.narrative.store_narrative(
            summary,
            {
                "event_type": "encounter_summary",
                "campaign_id": campaign.campaign_id,
                "module_id": module.module_id,
                "encounter_id": encounter.encounter_id,
            },
        )

        new_ids = (*module.completed_encounter_ids, encounter.encounter_id)
        new_summaries = (*module.completed_encounter_summaries, summary)
        updated_module = replace(
            module,
            completed_encounter_ids=new_ids,
            completed_encounter_summaries=new_summaries,
            next_encounter_index=module.next_encounter_index + 1,
        )

        gs = self._game_state_repo.load()
        self._game_state_repo.persist(
            replace(gs, module=updated_module, encounter=None)
        )

        # Build transition payload: read traveling actors from (post-persist) registry.
        gs = self._game_state_repo.load()
        registry = gs.actor_registry
        traveling_actors = {
            aid: registry.actors[aid]
            for aid in encounter.traveling_actor_ids
            if aid in registry.actors
        }
        traveling_presences = tuple(
            p
            for p in encounter.npc_presences
            if p.actor_id in encounter.traveling_actor_ids
        )
        transition = EncounterTransition(
            from_encounter_id=encounter.encounter_id,
            next_location_hint=encounter.next_location_hint,
            traveling_actor_ids=encounter.traveling_actor_ids,
            traveling_actors=traveling_actors,
            traveling_presences=traveling_presences,
        )

        return updated_module, transition

    def _prepare_and_run(
        self,
        *,
        campaign: CampaignState,
        player: ActorState,
        module: ModuleState,
        depth: int = 0,
        transition: EncounterTransition | None = None,
    ) -> None:
        """Ask the planner to prepare the next encounter, then run it."""
        result = self._agents.encounter_planner.prepare(
            module=module, campaign=campaign, player=player, transition=transition
        )
        if isinstance(result, MilestoneAchieved):
            self._advance_module(
                campaign=campaign,
                player=player,
                module=module,
                depth=depth,
            )
            return

        # EncounterReady: the planner has created and saved the encounter.
        module = result.module
        encounter_id = result.encounter_state.encounter_id
        self._encounter_orchestrator.run_encounter(
            encounter_id=encounter_id, campaign_id=campaign.campaign_id
        )

        # Reload from cache (not disk) to detect completion vs player quit
        reloaded = self._game_state_repo.load().encounter
        if (
            reloaded is not None
            and reloaded.encounter_id == encounter_id
            and reloaded.phase == EncounterPhase.ENCOUNTER_COMPLETE
        ):
            updated_module, next_transition = self._archive_encounter(
                encounter=reloaded, module=module, campaign=campaign
            )
            self._prepare_and_run(
                campaign=campaign,
                player=player,
                module=updated_module,
                transition=next_transition,
            )

    def _advance_module(
        self,
        *,
        campaign: CampaignState,
        player: ActorState,
        module: ModuleState,
        depth: int,
    ) -> None:
        """Increment milestone index, generate next module or end campaign."""
        if depth >= self._MAX_MODULE_DEPTH:
            return

        new_index = campaign.current_milestone_index + 1
        if new_index >= len(campaign.milestones):
            self._io.display(
                "\nThe campaign is complete. Your legend will be remembered.\n"
            )
            return

        # Generate next module
        milestone_dicts = [
            {
                "milestone_id": m.milestone_id,
                "title": m.title,
                "description": m.description,
            }
            for m in campaign.milestones
        ]
        module_result = self._agents.module_generator.generate(
            campaign_name=campaign.name,
            setting=campaign.setting,
            milestones=milestone_dicts,
            current_milestone_index=new_index,
            completed_module_summaries=list(module.completed_encounter_summaries),
        )
        new_module_id = f"module-{new_index + 1:03d}"
        new_module = ModuleState(
            module_id=new_module_id,
            campaign_id=campaign.campaign_id,
            title=module_result.title,
            summary=module_result.summary,
            guiding_milestone_id=module_result.guiding_milestone_id,
        )

        updated_campaign = replace(
            campaign,
            current_milestone_index=new_index,
            current_module_id=new_module_id,
        )

        gs = self._game_state_repo.load()
        self._game_state_repo.persist(
            replace(gs, campaign=updated_campaign, module=new_module)
        )

        # Recurse into new module
        self._run_loop(
            campaign=updated_campaign,
            module=new_module,
            depth=depth + 1,
        )
