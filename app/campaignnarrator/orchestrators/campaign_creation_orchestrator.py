"""Orchestrator for new campaign creation."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace

from campaignnarrator.agents.campaign_generator_agent import CampaignGeneratorAgent
from campaignnarrator.agents.module_generator_agent import ModuleGeneratorAgent
from campaignnarrator.domain.models import (
    ActorState,
    CampaignState,
    Milestone,
    ModuleState,
    PlayerIO,
)
from campaignnarrator.orchestrators.module_orchestrator import ModuleOrchestrator
from campaignnarrator.repositories.game_state_repository import GameStateRepository
from campaignnarrator.repositories.narrative_memory_repository import (
    NarrativeMemoryRepository,
)

_BRIEF_PROMPT = (
    "\nBefore we begin, tell me the kind of story you wish to live.\n\n"
    "Describe the world you want to inhabit, where your journey starts, what drives "
    "your character, and what enemies you hope to face. Speak freely — the more you "
    "tell me, the richer your tale will be.\n\n"
    "You can write as much as you like — press Ctrl+D when done.\n\n"
    "> "
)


@dataclass(frozen=True)
class CampaignCreationRepositories:
    """All repositories required by CampaignCreationOrchestrator."""

    narrative: NarrativeMemoryRepository
    game_state: GameStateRepository


@dataclass(frozen=True)
class CampaignCreationAgents:
    """All agents required by CampaignCreationOrchestrator."""

    campaign_generator: CampaignGeneratorAgent
    module_generator: ModuleGeneratorAgent


class CampaignCreationOrchestrator:
    """Generate and persist a campaign and first module, then delegate further.

    Delegates the encounter loop to the ModuleOrchestrator after saving state.
    """

    def __init__(
        self,
        *,
        io: PlayerIO,
        player: ActorState,
        repositories: CampaignCreationRepositories,
        agents: CampaignCreationAgents,
        module_orchestrator: ModuleOrchestrator,
    ) -> None:
        self._io = io
        self._player = player
        self._repos = repositories
        self._agents = agents
        self._module_orchestrator = module_orchestrator

    def run(self) -> None:
        """Collect player brief, generate campaign and first module, run encounter loop.

        Writes campaign setting to narrative memory before delegating.
        """
        player_brief = self._io.prompt_multiline(_BRIEF_PROMPT).strip()

        self._io.display("\nBuilding your world. This may take a few minutes...\n")
        campaign_result = self._agents.campaign_generator.generate(
            player_brief=player_brief,
            character_name=self._player.name,
            race=self._player.race or "Unknown",
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
        module_id = "module-001"
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
            current_module_id=module_id,
        )
        # Write campaign setting to narrative memory
        self._repos.narrative.store_narrative(
            f"Campaign: {campaign.name}. Setting: {campaign.setting}.",
            {"event_type": "campaign_setting", "campaign_id": campaign_id},
        )

        # Generate Module 1
        milestone_dicts = [
            {
                "milestone_id": m.milestone_id,
                "title": m.title,
                "description": m.description,
            }
            for m in milestones
        ]
        module_result = self._agents.module_generator.generate(
            campaign_name=campaign.name,
            setting=campaign.setting,
            milestones=milestone_dicts,
            current_milestone_index=0,
            completed_module_summaries=[],
        )
        module = ModuleState(
            module_id=module_id,
            campaign_id=campaign_id,
            title=module_result.title,
            summary=module_result.summary,
            guiding_milestone_id=module_result.guiding_milestone_id,
        )
        # Persist campaign + module together through the state facade
        gs = self._repos.game_state.load()
        persisted_gs = replace(gs, campaign=campaign, module=module)
        self._repos.game_state.persist(persisted_gs)

        # Delegate encounter loop to ModuleOrchestrator
        self._module_orchestrator.run(game_state=persisted_gs)
