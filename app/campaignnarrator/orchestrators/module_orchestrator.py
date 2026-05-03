"""Module encounter loop orchestrator."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from campaignnarrator.agents.module_generator_agent import ModuleGeneratorAgent
from campaignnarrator.agents.narrator_agent import NarratorAgent
from campaignnarrator.domain.models import (
    EncounterPhase,
    EncounterTransition,
    GameState,
    MilestoneAchieved,
    ModuleState,
    PlayerIO,
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

    def run(self, *, game_state: GameState) -> None:
        """Detect module state and run the encounter loop."""
        self._run_loop(game_state=game_state, depth=0)

    def _run_loop(
        self,
        *,
        game_state: GameState,
        depth: int = 0,
    ) -> None:
        """Inner loop: check encounter → archive if complete → prepare → run."""
        if game_state.campaign is None or game_state.module is None:
            return

        active = game_state.encounter

        # No active encounter — proceed to planning
        if active is None:
            self._prepare_and_run(game_state=game_state, depth=depth)
            return

        # Encounter already complete — archive then prepare
        if active.phase == EncounterPhase.ENCOUNTER_COMPLETE:
            game_state, transition = self._archive_encounter(game_state=game_state)
            self._prepare_and_run(
                game_state=game_state,
                depth=depth,
                transition=transition,
            )
            return

        # Encounter in progress — resume it; output is displayed live during the loop
        game_state = self._encounter_orchestrator.run(game_state)
        reloaded = game_state.encounter
        if reloaded is not None and reloaded.phase == EncounterPhase.ENCOUNTER_COMPLETE:
            game_state, transition = self._archive_encounter(game_state=game_state)
            self._prepare_and_run(
                game_state=game_state,
                depth=depth,
                transition=transition,
            )
        # else: player quit — state already persisted by run(); return

    def _archive_encounter(
        self,
        *,
        game_state: GameState,
    ) -> tuple[GameState, EncounterTransition]:
        """Summarize, store narrative, update module log, persist, clear."""
        encounter = game_state.encounter  # guaranteed non-None by caller
        module = game_state.module  # guaranteed non-None by caller
        campaign = game_state.campaign  # guaranteed non-None by caller

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

        updated_module = module.record_completed_encounter(
            encounter_id=encounter.encounter_id,
            summary=summary,
        )
        game_state = game_state.with_module(updated_module).clear_encounter()
        self._game_state_repo.persist(game_state)

        # Build transition from current registry (no reload — registry unchanged)
        registry = game_state.actor_registry
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

        return game_state, transition

    def _prepare_and_run(
        self,
        *,
        game_state: GameState,
        depth: int = 0,
        transition: EncounterTransition | None = None,
    ) -> None:
        """Ask the planner to prepare the next encounter, then run it."""
        player = game_state.get_player()
        result = self._agents.encounter_planner.prepare(
            module=game_state.module,
            campaign=game_state.campaign,
            player=player,
            transition=transition,
        )
        if isinstance(result, MilestoneAchieved):
            self._advance_module(game_state=game_state, depth=depth)
            return

        # EncounterReady: the planner persisted the full encounter + actor registry.
        # Reload so the encounter orchestrator sees all actors — not the stale
        # in-memory registry that predates the planner's persist().
        encounter_id = result.encounter_state.encounter_id
        game_state = self._game_state_repo.load()
        game_state = self._encounter_orchestrator.run(game_state)
        reloaded = game_state.encounter
        if (
            reloaded is not None
            and reloaded.encounter_id == encounter_id
            and reloaded.phase == EncounterPhase.ENCOUNTER_COMPLETE
        ):
            game_state, next_transition = self._archive_encounter(game_state=game_state)
            self._prepare_and_run(
                game_state=game_state,
                transition=next_transition,
            )

    def _advance_module(
        self,
        *,
        game_state: GameState,
        depth: int,
    ) -> None:
        """Increment milestone index, generate next module or end campaign."""
        if depth >= self._MAX_MODULE_DEPTH:
            return

        campaign = game_state.campaign
        module = game_state.module

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

        updated_campaign = campaign.advance_module(
            module_id=new_module_id,
            milestone_index=new_index,
        )
        new_gs = game_state.with_campaign(updated_campaign).with_module(new_module)
        self._game_state_repo.persist(new_gs)

        # Recurse into new module
        self._run_loop(game_state=new_gs, depth=depth + 1)
