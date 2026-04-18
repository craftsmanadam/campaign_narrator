"""Orchestrator for new campaign creation."""

from __future__ import annotations

import uuid

from campaignnarrator.agents.campaign_generator_agent import CampaignGeneratorAgent
from campaignnarrator.agents.module_generator_agent import ModuleGeneratorAgent
from campaignnarrator.domain.models import (
    ActorState,
    CampaignState,
    EncounterPhase,
    EncounterState,
    Milestone,
    ModuleState,
    PlayerIO,
)
from campaignnarrator.orchestrators.encounter_orchestrator import EncounterOrchestrator
from campaignnarrator.repositories.campaign_repository import CampaignRepository
from campaignnarrator.repositories.encounter_repository import EncounterRepository
from campaignnarrator.repositories.module_repository import ModuleRepository

_BRIEF_PROMPT = (
    "\nBefore we begin, tell me the kind of story you wish to live.\n\n"
    "Describe the world you want to inhabit, where your journey starts, what drives "
    "your character, and what enemies you hope to face. Speak freely — the more you "
    "tell me, the richer your tale will be.\n\n"
    "> "
)


class CampaignCreationOrchestrator:
    """Generate and persist a campaign, module, and first encounter, then run it."""

    def __init__(  # noqa: PLR0913
        self,
        *,
        io: PlayerIO,
        player: ActorState,
        campaign_repository: CampaignRepository,
        module_repository: ModuleRepository,
        encounter_repository: EncounterRepository,
        campaign_agent: CampaignGeneratorAgent,
        module_agent: ModuleGeneratorAgent,
        encounter_orchestrator: EncounterOrchestrator,
    ) -> None:
        self._io = io
        self._player = player
        self._campaign_repo = campaign_repository
        self._module_repo = module_repository
        self._encounter_repo = encounter_repository
        self._campaign_agent = campaign_agent
        self._module_agent = module_agent
        self._encounter_orchestrator = encounter_orchestrator

    def run(self) -> None:
        """Collect player brief, generate campaign, create first encounter, run it."""
        player_brief = self._io.prompt(_BRIEF_PROMPT).strip()

        # Generate campaign skeleton (narrator-only fields stay out of player context)
        campaign_result = self._campaign_agent.generate(
            player_brief=player_brief,
            character_name=self._player.name,
            race=self._player.race or "Unknown",
            # NOTE: actor_id used as class proxy; ActorState has no class_name field
            class_name=self._player.actor_id,
            background=self._player.background or "",
        )

        campaign_id = str(uuid.uuid4())
        milestones = tuple(
            Milestone(
                milestone_id=m.milestone_id,
                title=m.title,
                description=m.description,
            )
            for m in campaign_result.milestones
        )

        # NARRATOR-ONLY: hidden_goal, bbeg_name, bbeg_description, milestones
        campaign = CampaignState(
            campaign_id=campaign_id,
            name=campaign_result.name,
            setting=campaign_result.setting,
            narrator_personality=campaign_result.narrator_personality,
            hidden_goal=campaign_result.hidden_goal,
            bbeg_name=campaign_result.bbeg_name,
            bbeg_description=campaign_result.bbeg_description,
            milestones=milestones,
            current_milestone_index=0,
            starting_level=1,
            target_level=min(campaign_result.target_level, 20),
            player_brief=player_brief,
            player_actor_id=self._player.actor_id,
        )
        self._campaign_repo.save(campaign)

        # Generate Module 1
        milestone_dicts = [
            {
                "milestone_id": m.milestone_id,
                "title": m.title,
                "description": m.description,
            }
            for m in milestones
        ]
        module_result = self._module_agent.generate(
            campaign_name=campaign.name,
            setting=campaign.setting,
            milestones=milestone_dicts,
            current_milestone_index=0,
            completed_module_summaries=[],
        )

        module_id = "module-001"
        encounter_id = f"{module_id}-enc-001"

        module = ModuleState(
            module_id=module_id,
            campaign_id=campaign_id,
            title=module_result.title,
            summary=module_result.summary,
            guiding_milestone_id=module_result.guiding_milestone_id,
            encounters=(encounter_id,),
            current_encounter_index=0,
        )
        self._module_repo.save(module)

        # Create first EncounterState from the opening seed
        encounter = EncounterState(
            encounter_id=encounter_id,
            phase=EncounterPhase.SCENE_OPENING,
            setting=module_result.opening_encounter_seed,
            actors={self._player.actor_id: self._player},
        )
        self._encounter_repo.save(encounter)

        # Hand off to EncounterOrchestrator — it narrates the opening scene
        result = self._encounter_orchestrator.run_encounter(encounter_id=encounter_id)
        if result.output_text:
            self._io.display(result.output_text)
