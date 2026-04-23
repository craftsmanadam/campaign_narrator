"""Orchestrator that prepares a ready-to-run EncounterState before scene opening.

Single public method: prepare(module, campaign, player).
Returns EncounterReady | MilestoneAchieved.
Called by ModuleOrchestrator only when no active encounter exists.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, replace
from pathlib import Path

from campaignnarrator.agents.encounter_planner_agent import EncounterPlannerAgent
from campaignnarrator.domain.models import (
    ActorState,
    ActorType,
    CampaignState,
    DivergenceAssessment,
    EncounterNpc,
    EncounterPhase,
    EncounterReady,
    EncounterState,
    EncounterTemplate,
    MilestoneAchieved,
    ModuleState,
    NpcPresence,
)
from campaignnarrator.repositories.compendium_repository import CompendiumRepository
from campaignnarrator.repositories.encounter_repository import EncounterRepository
from campaignnarrator.repositories.memory_repository import MemoryRepository
from campaignnarrator.repositories.module_repository import ModuleRepository
from campaignnarrator.tools.cr_scaling import scale_encounter_npcs
from campaignnarrator.tools.monster_loader import load_by_name as _load_monster

_log = logging.getLogger(__name__)


class _OutOfBoundsTemplateError(ValueError):
    """Raised when the encounter index is out of bounds with viable status."""


_SIMPLE_NPC_HP = 1
_SIMPLE_NPC_AC = 10
_MAX_PREPARE_ATTEMPTS = 3


def _build_npc_actor(
    npc: EncounterNpc,
    actor_id: str,
    index_path: Path | None,
) -> ActorState:
    """Build an ActorState from an EncounterNpc planning-time definition.

    Uses compendium stats when stat_source='monster_compendium' and
    index_path is valid. Falls back to simple placeholder stats on any
    lookup failure.
    """
    if (
        npc.stat_source == "monster_compendium"
        and npc.monster_name
        and index_path is not None
        and index_path.exists()
    ):
        try:
            actor = _load_monster(npc.monster_name, index_path=index_path)
            return replace(actor, actor_id=actor_id, name=npc.display_name)
        except KeyError:
            _log.warning(
                "Monster %r not found in compendium; using simple NPC stats",
                npc.monster_name,
            )
        except FileNotFoundError:
            _log.warning(
                "Monster %r not found in compendium; using simple NPC stats",
                npc.monster_name,
            )
    return ActorState(
        actor_id=actor_id,
        name=npc.display_name,
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

        Retries up to _MAX_PREPARE_ATTEMPTS times on transient LLM failure.
        """
        last_exc: Exception | None = None
        for attempt in range(_MAX_PREPARE_ATTEMPTS):
            try:
                module = self._ensure_planned(
                    module=module, campaign=campaign, player=player
                )
                return self._diverge_and_instantiate(
                    module=module, campaign=campaign, player=player
                )
            except Exception as exc:
                last_exc = exc
                if attempt < _MAX_PREPARE_ATTEMPTS - 1:
                    wait = 2**attempt
                    _log.warning(
                        "prepare() attempt %d/%d failed: %s — retrying in %ds",
                        attempt + 1,
                        _MAX_PREPARE_ATTEMPTS,
                        exc,
                        wait,
                    )
                    time.sleep(wait)
        _log.error(
            "prepare() failed after %d attempts for module %s",
            _MAX_PREPARE_ATTEMPTS,
            module.module_id,
        )
        raise last_exc  # type: ignore[misc]

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
        """Steps 2-3: divergence check, optional recovery, then instantiation."""
        narrative_context = self._narrative_context(module=module)
        milestone = campaign.milestones[campaign.current_milestone_index]

        # Determine the next template (None if index is out of bounds)
        if module.next_encounter_index >= len(module.planned_encounters):
            template: EncounterTemplate | None = None
        else:
            template = module.planned_encounters[module.next_encounter_index]

        # Step 2: Divergence check
        assessment = self._agents.planner.assess_divergence(
            template=template,
            module=module,
            milestone=milestone,
            narrative_context=narrative_context,
            player=player,
        )

        if assessment.milestone_achieved:
            return MilestoneAchieved()

        # Step 2b: Recovery if needed
        module = self._recover_if_needed(
            assessment=assessment,
            module=module,
            campaign=campaign,
            narrative_context=narrative_context,
            player=player,
        )

        # Fetch template again after potential recovery.
        # Index may still be out-of-bounds (viable + out-of-bounds edge case).
        if module.next_encounter_index < len(module.planned_encounters):
            template = module.planned_encounters[module.next_encounter_index]

        if template is None:
            raise _OutOfBoundsTemplateError

        # Step 3: instantiation (Plan 3c)
        return self._instantiate(module=module, template=template, player=player)

    def _recover_if_needed(
        self,
        *,
        assessment: DivergenceAssessment,
        module: ModuleState,
        campaign: CampaignState,
        narrative_context: str,
        player: ActorState,
    ) -> ModuleState:
        """Apply recovery if assessment is not viable.

        Returns the (possibly updated) module.
        """
        if assessment.status == "viable":
            return module

        recovery_type_map = {
            "needs_bridge": "bridge_inserted",
            "needs_rebuild": "template_replaced",
            "needs_full_replan": "full_replan",
        }
        recovery_type = recovery_type_map[assessment.status]

        current_index = module.next_encounter_index
        remaining = module.planned_encounters[current_index:]

        recovery = self._agents.planner.recover_encounters(
            divergence_reason=assessment.reason,
            recovery_type=recovery_type,
            current_index=current_index,
            remaining_templates=remaining,
            module=module,
            campaign=campaign,
            narrative_context=narrative_context,
            player=player,
        )

        if not recovery.updated_templates:
            _log.warning(
                "Recovery for module %s returned empty templates"
                " — escalating to full replan",
                module.module_id,
            )
            recovery = self._agents.planner.recover_encounters(
                divergence_reason=(
                    f"Previous recovery returned empty list. {assessment.reason}"
                ),
                recovery_type="full_replan",
                current_index=current_index,
                remaining_templates=remaining,
                module=module,
                campaign=campaign,
                narrative_context=narrative_context,
                player=player,
            )

        completed = module.planned_encounters[:current_index]
        new_plans = tuple(completed) + tuple(recovery.updated_templates)
        module = replace(module, planned_encounters=new_plans)
        self._repos.module.save(module)
        return module

    def _instantiate(
        self,
        *,
        module: ModuleState,
        template: EncounterTemplate,
        player: ActorState,
    ) -> EncounterReady:
        """Build ActorState + NpcPresence for each NPC, assemble EncounterState."""
        index_path = self._repos.compendium.monster_index_path()

        scaled_npcs = scale_encounter_npcs(template.npcs, player_level=player.level)

        actors: dict[str, ActorState] = {player.actor_id: player}
        npc_presences: list[NpcPresence] = []

        for npc in scaled_npcs:
            actor_id = f"npc:{npc.template_npc_id}"
            npc_actor = _build_npc_actor(npc, actor_id=actor_id, index_path=index_path)
            actors[actor_id] = npc_actor
            npc_presences.append(
                NpcPresence(
                    actor_id=actor_id,
                    display_name=npc.display_name,
                    description=npc.description,
                    name_known=npc.name_known,
                    visible=True,
                )
            )

        encounter_id = f"{module.module_id}-enc-{module.next_encounter_index + 1:03d}"
        encounter = EncounterState(
            encounter_id=encounter_id,
            phase=EncounterPhase.SCENE_OPENING,
            setting=template.setting,
            scene_tone=template.scene_tone,
            actors=actors,
            npc_presences=tuple(npc_presences),
        )
        self._repos.encounter.save(encounter)

        return EncounterReady(encounter_state=encounter, module=module)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _narrative_context(self, *, module: ModuleState) -> str:
        """Retrieve recent narrative memory relevant to this module."""
        results = self._repos.memory.retrieve_relevant(module.title, limit=5)
        return "\n---\n".join(results) if results else "No prior narrative context."
