"""Orchestrator that prepares a ready-to-run EncounterState before scene opening.

Single public method: prepare(module, campaign, player).
Returns EncounterReady | MilestoneAchieved.
Called by ModuleOrchestrator only when no active encounter exists.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace

from campaignnarrator.agents.encounter_planner_agent import EncounterPlannerAgent
from campaignnarrator.domain.models import (
    ActorState,
    CampaignState,
    EncounterReady,
    MilestoneAchieved,
    ModuleState,
)
from campaignnarrator.repositories.compendium_repository import CompendiumRepository
from campaignnarrator.repositories.encounter_repository import EncounterRepository
from campaignnarrator.repositories.memory_repository import MemoryRepository
from campaignnarrator.repositories.module_repository import ModuleRepository

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class EncounterPlannerOrchestratorRepositories:
    """All repositories required by EncounterPlannerOrchestrator."""

    module: ModuleRepository
    encounter: EncounterRepository
    memory: MemoryRepository
    compendium: CompendiumRepository


@dataclass(frozen=True)
class EncounterPlannerOrchestratorAgents:
    """All agents required by EncounterPlannerOrchestrator."""

    planner: EncounterPlannerAgent


class EncounterPlannerOrchestrator:
    """Produce a ready-to-run EncounterState before the narrator opens the scene.

    Called by ModuleOrchestrator only when load_active() returns None.
    prepare() is the single public entry point.
    """

    def __init__(
        self,
        *,
        repositories: EncounterPlannerOrchestratorRepositories,
        agents: EncounterPlannerOrchestratorAgents,
    ) -> None:
        self._repos = repositories
        self._agents = agents

    def prepare(
        self,
        *,
        module: ModuleState,
        campaign: CampaignState,
        player: ActorState,
    ) -> EncounterReady | MilestoneAchieved:
        """Produce a ready-to-run EncounterState.

        Steps (implemented across Plans 3a, 3b, 3c):
          1. [3a] If planned_encounters empty → call planner, save module
          2. [3b] Divergence check → viable / milestone_achieved / recovery
          3. [3c] CR scaling → instantiate actors + NpcPresences → save EncounterState
        """
        module = self._ensure_planned(module=module, campaign=campaign, player=player)
        return self._diverge_and_instantiate(
            module=module, campaign=campaign, player=player
        )

    # ── Step 1: ensure the module has a populated encounter list ─────────────

    def _ensure_planned(
        self,
        *,
        module: ModuleState,
        campaign: CampaignState,
        player: ActorState,
    ) -> ModuleState:
        """If planned_encounters is empty, run the planning agent and save."""
        if module.planned_encounters:
            return module

        _log.info(
            "Module %s has no planned encounters — running planner",
            module.module_id,
        )
        narrative_context = self._narrative_context(module=module)
        new_plans = self._agents.planner.plan_encounters(
            module=module,
            campaign=campaign,
            player=player,
            narrative_context=narrative_context,
        )
        module = replace(module, planned_encounters=new_plans, next_encounter_index=0)
        self._repos.module.save(module)
        return module

    # ── Step 2 & 3: divergence check + instantiation (Plans 3b and 3c) ───────

    def _diverge_and_instantiate(
        self,
        *,
        module: ModuleState,
        campaign: CampaignState,
        player: ActorState,
    ) -> EncounterReady | MilestoneAchieved:
        raise NotImplementedError

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _narrative_context(self, *, module: ModuleState) -> str:
        """Retrieve recent narrative memory relevant to this module."""
        results = self._repos.memory.retrieve_relevant(module.title, limit=5)
        return "\n---\n".join(results) if results else "No prior narrative context."
