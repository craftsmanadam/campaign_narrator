"""Module encounter loop orchestrator."""

from __future__ import annotations

from dataclasses import dataclass, replace

from campaignnarrator.agents.module_generator_agent import ModuleGeneratorAgent
from campaignnarrator.agents.narrator_agent import NarratorAgent
from campaignnarrator.domain.models import (
    ActorState,
    CampaignState,
    EncounterPhase,
    EncounterState,
    ModuleState,
    PlayerIO,
)
from campaignnarrator.orchestrators.encounter_orchestrator import EncounterOrchestrator
from campaignnarrator.repositories.actor_repository import ActorRepository
from campaignnarrator.repositories.campaign_repository import CampaignRepository
from campaignnarrator.repositories.encounter_repository import EncounterRepository
from campaignnarrator.repositories.memory_repository import MemoryRepository
from campaignnarrator.repositories.module_repository import ModuleRepository


@dataclass(frozen=True)
class ModuleOrchestratorRepositories:
    """All repositories required by ModuleOrchestrator."""

    campaign: CampaignRepository
    module: ModuleRepository
    encounter: EncounterRepository
    actor: ActorRepository
    memory: MemoryRepository


@dataclass(frozen=True)
class ModuleOrchestratorAgents:
    """All agents required by ModuleOrchestrator."""

    narrator: NarratorAgent
    module_generator: ModuleGeneratorAgent


class ModuleOrchestrator:
    """Own the encounter loop within a module.

    Single caller of EncounterOrchestrator.run_encounter() and single writer
    of encounter summaries to MemoryRepository. Callers pass campaign and player
    at run() time — not at construction — so this can be built eagerly by
    ApplicationFactory.
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

    def run(self, *, campaign: CampaignState, player: ActorState) -> None:
        """Detect module state and run the encounter loop."""
        module = self._repos.module.load(campaign.current_module_id)
        if module is None:
            return

        self._run_loop(campaign=campaign, player=player, module=module, depth=0)

    def _run_loop(
        self,
        *,
        campaign: CampaignState,
        player: ActorState,
        module: ModuleState,
        depth: int = 0,
    ) -> None:
        """Inner loop: check encounter → archive if complete → plan → create → run."""
        active = self._repos.encounter.load_active()

        # No active encounter — proceed to planning
        if active is None:
            self._plan_and_run(
                campaign=campaign,
                player=player,
                module=module,
                last_outcome="",
                depth=depth,
            )
            return

        # Encounter already complete — archive then plan
        if active.phase == EncounterPhase.ENCOUNTER_COMPLETE:
            module = self._archive_encounter(
                encounter=active, module=module, campaign=campaign
            )
            self._plan_and_run(
                campaign=campaign,
                player=player,
                module=module,
                last_outcome=active.outcome or "",
                depth=depth,
            )
            return

        # Encounter in progress — resume it; output is displayed live during the loop
        self._encounter_orchestrator.run_encounter(encounter_id=active.encounter_id)

        # Reload to detect natural completion vs player quit
        reloaded = self._repos.encounter.load_active()
        if reloaded is not None and reloaded.phase == EncounterPhase.ENCOUNTER_COMPLETE:
            module = self._archive_encounter(
                encounter=reloaded, module=module, campaign=campaign
            )
            self._plan_and_run(
                campaign=campaign,
                player=player,
                module=module,
                last_outcome=reloaded.outcome or "",
                depth=depth,
            )
        # else: player quit — save state as-is and return

    def _archive_encounter(
        self,
        *,
        encounter: EncounterState,
        module: ModuleState,
        campaign: CampaignState,
    ) -> ModuleState:
        """Summarize, store narrative, update module log, clear active encounter."""
        summary = self._agents.narrator.summarize_encounter(encounter, module, campaign)
        self._repos.memory.store_narrative(
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
            next_encounter_seed=None,
        )
        self._repos.module.save(updated_module)
        self._repos.encounter.clear()
        return updated_module

    def _plan_and_run(
        self,
        *,
        campaign: CampaignState,
        player: ActorState,
        module: ModuleState,
        last_outcome: str,
        depth: int = 0,
    ) -> None:
        """Plan the next encounter (if not already planned) and run it."""
        # No encounter seed yet — ask narrator to plan
        if module.next_encounter_seed is None:
            milestone = campaign.milestones[campaign.current_milestone_index]
            plan = self._agents.narrator.plan_next_encounter(
                campaign=campaign,
                module=module,
                milestone=milestone,
                player=player,
                last_outcome=last_outcome,
            )
            if plan.milestone_achieved:
                self._advance_module(
                    campaign=campaign,
                    player=player,
                    module=module,
                    depth=depth,
                )
                return
            module = replace(module, next_encounter_seed=plan.seed)
            self._repos.module.save(module)

        # Seed ready — create and run the next encounter
        self._create_and_run_encounter(campaign=campaign, player=player, module=module)

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
            next_encounter_seed=module_result.opening_encounter_seed,
        )
        self._repos.module.save(new_module)

        updated_campaign = replace(
            campaign,
            current_milestone_index=new_index,
            current_module_id=new_module_id,
        )
        self._repos.campaign.save(updated_campaign)

        # Recurse into new module
        self._run_loop(
            campaign=updated_campaign,
            player=player,
            module=new_module,
            depth=depth + 1,
        )

    def _create_and_run_encounter(
        self,
        *,
        campaign: CampaignState,
        player: ActorState,
        module: ModuleState,
    ) -> None:
        """Create an EncounterState and delegate to EncounterOrchestrator."""
        encounter_id = (
            f"{module.module_id}-enc-{len(module.completed_encounter_ids) + 1:03d}"
        )
        encounter = EncounterState(
            encounter_id=encounter_id,
            phase=EncounterPhase.SCENE_OPENING,
            setting=module.next_encounter_seed or "",
            actors={player.actor_id: player},
        )
        self._repos.encounter.save(encounter)
        # Output is displayed live during run_encounter(); return value not used here.
        self._encounter_orchestrator.run_encounter(encounter_id=encounter_id)

        # After return, check phase to detect natural completion.
        # Only archive if the encounter that completed is the one we just created.
        reloaded = self._repos.encounter.load_active()
        if (
            reloaded is not None
            and reloaded.encounter_id == encounter_id
            and reloaded.phase == EncounterPhase.ENCOUNTER_COMPLETE
        ):
            updated_module = self._archive_encounter(
                encounter=reloaded, module=module, campaign=campaign
            )
            self._plan_and_run(
                campaign=campaign,
                player=player,
                module=updated_module,
                last_outcome=reloaded.outcome or "",
            )
