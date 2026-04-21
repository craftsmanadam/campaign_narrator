"""Module encounter loop orchestrator."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, replace
from pathlib import Path

from campaignnarrator.agents.module_generator_agent import ModuleGeneratorAgent
from campaignnarrator.agents.narrator_agent import NarratorAgent
from campaignnarrator.domain.models import (
    ActorState,
    ActorType,
    CampaignState,
    EncounterPhase,
    EncounterState,
    ModuleState,
    NarrationFrame,
    NpcPresence,
    NpcPresenceResult,
    PlayerIO,
)
from campaignnarrator.orchestrators.encounter_orchestrator import EncounterOrchestrator
from campaignnarrator.repositories.actor_repository import ActorRepository
from campaignnarrator.repositories.campaign_repository import CampaignRepository
from campaignnarrator.repositories.compendium_repository import CompendiumRepository
from campaignnarrator.repositories.encounter_repository import EncounterRepository
from campaignnarrator.repositories.memory_repository import MemoryRepository
from campaignnarrator.repositories.module_repository import ModuleRepository
from campaignnarrator.tools.monster_loader import load_by_name as _load_monster

_log = logging.getLogger(__name__)

_SIMPLE_NPC_HP = 1
_SIMPLE_NPC_AC = 10


def _slugify(name: str) -> str:
    slug = name.lower().replace(" ", "-")
    return re.sub(r"[^a-z0-9-]", "", slug)


def _make_scene_frame(player: ActorState, seed: str) -> NarrationFrame:
    return NarrationFrame(
        purpose="scene_opening",
        phase=EncounterPhase.SCENE_OPENING,
        setting=seed,
        public_actor_summaries=(f"{player.name} (player)",),
        recent_public_events=(),
        resolved_outcomes=(),
        allowed_disclosures=("public encounter state",),
    )


def _build_npc_actor(
    result: NpcPresenceResult,
    actor_id: str,
    index_path: Path | None,
) -> ActorState:
    if (
        result.stat_source == "monster_compendium"
        and result.monster_name
        and index_path is not None
        and index_path.exists()
    ):
        try:
            actor = _load_monster(result.monster_name, index_path=index_path)
            return replace(actor, actor_id=actor_id, name=result.display_name)
        except KeyError, FileNotFoundError:
            _log.warning(
                "Monster %r not found in compendium; using simple NPC stats",
                result.monster_name,
            )
    return ActorState(
        actor_id=actor_id,
        name=result.display_name,
        actor_type=ActorType.NPC,
        hp_max=_SIMPLE_NPC_HP,
        hp_current=_SIMPLE_NPC_HP,
        armor_class=_SIMPLE_NPC_AC,
        strength=10,
        dexterity=10,
        constitution=10,
        intelligence=10,
        wisdom=10,
        charisma=10,
        proficiency_bonus=2,
        initiative_bonus=0,
        speed=30,
        attacks_per_action=1,
        action_options=("Talk",),
        ac_breakdown=(),
    )


@dataclass(frozen=True)
class ModuleOrchestratorRepositories:
    """All repositories required by ModuleOrchestrator."""

    campaign: CampaignRepository
    module: ModuleRepository
    encounter: EncounterRepository
    actor: ActorRepository
    memory: MemoryRepository
    compendium: CompendiumRepository


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
        """Open the scene, seed NPCs, create EncounterState, then run the encounter."""
        seed = module.next_encounter_seed or ""
        encounter_id = (
            f"{module.module_id}-enc-{len(module.completed_encounter_ids) + 1:03d}"
        )

        # Step 1: Open the scene and get structured response with introduced NPCs.
        frame = _make_scene_frame(player, seed)
        scene_response = self._agents.narrator.open_scene(frame)
        self._io.display(scene_response.text)

        # Step 2: Seed NPC actors from the scene response.
        index_path = self._repos.compendium.monster_index_path()
        actors: dict[str, ActorState] = {player.actor_id: player}
        npc_presences: list[NpcPresence] = []
        for i, npc_result in enumerate(scene_response.introduced_npcs):
            actor_id = f"npc:{_slugify(npc_result.display_name)}-{i:03d}"
            npc_actor = _build_npc_actor(npc_result, actor_id, index_path)
            actors[actor_id] = npc_actor
            npc_presences.append(
                NpcPresence(
                    actor_id=actor_id,
                    display_name=npc_result.display_name,
                    description=npc_result.description,
                    name_known=npc_result.name_known,
                    visible=True,
                )
            )

        # Step 3: Create encounter with SOCIAL phase (scene already opened).
        encounter = EncounterState(
            encounter_id=encounter_id,
            phase=EncounterPhase.SOCIAL,
            setting=seed,
            scene_tone=scene_response.scene_tone,
            actors=actors,
            npc_presences=tuple(npc_presences),
        )
        self._repos.encounter.save(encounter)

        # Step 4: Run the encounter (phase is SOCIAL so _open_scene is skipped).
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
