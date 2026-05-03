"""Top-level game state and planner result types."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from .actor_registry import ActorRegistry
from .actor_state import ActorState, ActorType, ResourceUnavailableError, TurnResources
from .campaign_state import CampaignState, Milestone, ModuleState
from .combat import CombatStatus
from .combat_state import CombatState
from .encounter_state import EncounterPhase, EncounterState
from .encounter_template import EncounterTemplate
from .npc_presence import NpcPresenceStatus

__all__ = [
    "ActorState",
    "ActorType",
    "CampaignState",
    "CombatState",
    "EncounterPhase",
    "EncounterReady",
    "EncounterState",
    "GameState",
    "MilestoneAchieved",
    "ResourceUnavailableError",
    "TurnResources",
]

_log = logging.getLogger(__name__)

# Death saving throw thresholds
_DEATH_SAVE_NAT_ONE = 1
_DEATH_SAVE_NAT_TWENTY = 20
_DEATH_SAVE_MIN_SUCCESS_ROLL = 10
_DEATH_SAVE_SUCCESS_THRESHOLD = 3
_DEATH_SAVE_FAILURE_THRESHOLD = 3


class _PlayerNotFoundError(RuntimeError):
    """Player actor was not found in the registry."""

    def __init__(self, player_actor_id: str) -> None:
        super().__init__(
            f"Player actor '{player_actor_id}' not found in registry. "
            "Registry may not have been bootstrapped before this call."
        )


_ACTIVE_NPC_STATUSES = frozenset(
    {
        NpcPresenceStatus.AVAILABLE,
        NpcPresenceStatus.PRESENT,
        NpcPresenceStatus.INTERACTED,
        NpcPresenceStatus.CONCEALED,
    }
)


class _InvalidCampaignSeedError(TypeError):
    """Raised when a campaign seed is not a valid mapping."""


class _InvalidMilestoneSeedError(TypeError):
    """Raised when a milestone seed is not a valid mapping."""


class _InvalidModuleSeedError(TypeError):
    """Raised when a module seed is not a valid mapping."""


@dataclass(frozen=True)
class GameState:
    """Top-level game state. Player lives in actor_registry."""

    campaign: CampaignState | None = None
    module: ModuleState | None = None
    encounter: EncounterState | None = None
    actor_registry: ActorRegistry = field(default_factory=ActorRegistry)
    combat_state: CombatState | None = None

    def with_campaign(self, campaign: CampaignState) -> GameState:
        """Return a copy with campaign replaced."""
        return replace(self, campaign=campaign)

    def with_module(self, module: ModuleState) -> GameState:
        """Return a copy with module replaced."""
        return replace(self, module=module)

    def with_encounter(self, encounter: EncounterState) -> GameState:
        """Return a copy with encounter set."""
        return replace(self, encounter=encounter)

    def clear_encounter(self) -> GameState:
        """Return a copy with encounter cleared to None."""
        return replace(self, encounter=None)

    def with_actor_registry(self, registry: ActorRegistry) -> GameState:
        """Return a copy with actor_registry replaced."""
        return replace(self, actor_registry=registry)

    def with_combat_state(self, combat_state: CombatState | None) -> GameState:
        """Return a copy with combat_state replaced."""
        return replace(self, combat_state=combat_state)

    def with_combat_status(self, status: CombatStatus) -> GameState:
        """Return a copy with combat_state.status updated.

        No-op if combat_state is None.
        """
        if self.combat_state is None:
            return self
        return replace(self, combat_state=replace(self.combat_state, status=status))

    def advance_turn(self) -> GameState:
        """Rotate the turn order and initialize fresh TurnResources for the next actor.

        Atomically rotates TurnOrder AND seeds current_turn_resources from the incoming
        actor's speed. No-op if combat_state is None.
        """
        if self.combat_state is None:
            return self
        new_turn_order = self.combat_state.turn_order.end_turn()
        incoming_actor = self.actor_registry.actors.get(new_turn_order.current_actor_id)
        fresh_resources = (
            incoming_actor.get_turn_resources()
            if incoming_actor is not None
            else TurnResources()
        )
        return replace(
            self,
            combat_state=replace(
                self.combat_state,
                turn_order=new_turn_order,
                current_turn_resources=fresh_resources,
            ),
        )

    def spend_turn_resource(self, resource_type: str, amount: int = 1) -> GameState:
        """Deduct a turn resource. Raises ResourceUnavailableError if exhausted.

        No-op if combat_state is None.
        Valid resource_type: "action", "bonus_action", "reaction", "movement".
        """
        if self.combat_state is None:
            return self
        new_resources = self.combat_state.current_turn_resources.deduct(
            resource_type, amount
        )
        return replace(
            self,
            combat_state=replace(
                self.combat_state, current_turn_resources=new_resources
            ),
        )

    def adjust_hit_points(self, actor_id: str, delta: int) -> GameState:
        """Apply a HP delta to actor_id, clamped to [0, hp_max].

        Raises KeyError if actor_id is not in the registry — do not call for
        unknown actors.
        """
        actor = self.actor_registry.actors[actor_id]
        return replace(
            self,
            actor_registry=self.actor_registry.with_actor(actor.apply_change_hp(delta)),
        )

    def add_condition(self, actor_id: str, condition: str) -> GameState:
        """Add condition to actor_id. No-op if already present."""
        actor = self.actor_registry.actors[actor_id]
        return replace(
            self,
            actor_registry=self.actor_registry.with_actor(
                actor.with_condition(condition)
            ),
        )

    def remove_condition(self, actor_id: str, condition: str) -> GameState:
        """Remove condition from actor_id. No-op if not present."""
        actor = self.actor_registry.actors[actor_id]
        return replace(
            self,
            actor_registry=self.actor_registry.with_actor(
                actor.without_condition(condition)
            ),
        )

    def spend_inventory(self, actor_id: str, item_id: str) -> GameState:
        """Consume one unit of item_id from actor_id's inventory.

        Raises ValueError if item not found (delegates to
        ActorState.apply_inventory_spent).

        """
        actor = self.actor_registry.actors[actor_id]
        return replace(
            self,
            actor_registry=self.actor_registry.with_actor(
                actor.apply_inventory_spent(item_id)
            ),
        )

    def set_phase(self, phase: EncounterPhase) -> GameState:
        """Return a copy with the encounter's phase updated.

        No-op if encounter is None.
        """
        if self.encounter is None:
            return self
        return replace(self, encounter=self.encounter.with_phase(phase))

    def set_encounter_outcome(self, outcome: str) -> GameState:
        """Return a copy with the encounter's outcome set.

        No-op if encounter is None.
        """
        if self.encounter is None:
            return self
        return replace(self, encounter=self.encounter.with_outcome(outcome))

    def append_public_event(self, event: str) -> GameState:
        """Append event to encounter.public_events. No-op if encounter is None."""
        if self.encounter is None:
            return self
        return replace(self, encounter=self.encounter.append_public_event(event))

    def set_npc_status(self, actor_id: str, status: NpcPresenceStatus) -> GameState:
        """Update NPC presence status.

        Logs and returns self if actor_id not in presences.
        """
        if self.encounter is None:
            return self
        if not any(p.actor_id == actor_id for p in self.encounter.npc_presences):
            _log.warning(
                "set_npc_status: no NpcPresence for %r — effect ignored", actor_id
            )
            return self
        return replace(self, encounter=self.encounter.with_npc_status(actor_id, status))

    def apply_zero_hp_conditions(self) -> GameState:
        """Apply dead/unconscious to zero-HP actors in the current encounter.

        NPCs and allies at 0 HP get "dead".
        PCs at 0 HP (not already dead or unconscious) get "unconscious".
        No-op if encounter is None.
        """
        if self.encounter is None:
            return self
        updated_actors = dict(self.actor_registry.actors)
        changed = False
        for actor_id in self.encounter.actor_ids:
            actor = updated_actors.get(actor_id)
            if actor is None or actor.hp_current > 0:
                continue
            if actor.actor_type in (ActorType.NPC, ActorType.ALLY):
                if "dead" not in actor.conditions:
                    updated_actors[actor_id] = actor.with_condition("dead")
                    changed = True
            elif (
                actor.actor_type == ActorType.PC
                and "dead" not in actor.conditions
                and "unconscious" not in actor.conditions
            ):
                updated_actors[actor_id] = actor.with_condition("unconscious")
                changed = True
        if not changed:
            return self
        return replace(
            self, actor_registry=self.actor_registry.with_actors(updated_actors)
        )

    def evaluate_combat_end_conditions(self) -> GameState:
        """Check if the player-down-no-allies condition is met and update status.

        If a PC is at 0 HP (not dead or stable) and there are no conscious allied
        actors, sets combat_state.status to PLAYER_DOWN_NO_ALLIES and records
        death_saves_remaining. Returns self unchanged if the condition is not met,
        or if encounter/combat_state is None.
        """
        if self.encounter is None or self.combat_state is None:
            return self
        encounter_actors = [
            self.actor_registry.actors[aid]
            for aid in self.encounter.actor_ids
            if aid in self.actor_registry.actors
        ]
        pc_actors = [a for a in encounter_actors if a.actor_type == ActorType.PC]
        conscious_allies = [
            a
            for a in encounter_actors
            if a.actor_type in (ActorType.PC, ActorType.ALLY)
            and a.hp_current > 0
            and "dead" not in a.conditions
            and "unconscious" not in a.conditions
        ]
        downed_pcs = [
            a
            for a in pc_actors
            if a.hp_current <= 0
            and "dead" not in a.conditions
            and "stable" not in a.conditions
        ]
        if downed_pcs and not conscious_allies:
            downed = downed_pcs[0]
            return replace(
                self,
                combat_state=replace(
                    self.combat_state,
                    status=CombatStatus.PLAYER_DOWN_NO_ALLIES,
                    death_saves_remaining=3 - downed.death_save_failures,
                ),
            )
        return self

    def apply_death_save(self, actor_id: str, roll_result: int) -> GameState:
        """Apply a death saving throw roll to actor_id and return updated GameState.

        - Natural 1: +2 failures
        - Natural 20: +2 successes
        - 10-19: +1 success
        - 2-9: +1 failure
        - 3+ successes: actor gains "stable", loses "unconscious"
        - 3+ failures: actor gains "dead", loses "unconscious"

        Raises KeyError if actor_id not in registry.
        """
        actor = self.actor_registry.actors[actor_id]
        successes = actor.death_save_successes
        failures = actor.death_save_failures

        if roll_result == _DEATH_SAVE_NAT_ONE:
            failures += 2
        elif roll_result == _DEATH_SAVE_NAT_TWENTY:
            successes += 2
        elif roll_result >= _DEATH_SAVE_MIN_SUCCESS_ROLL:
            successes += 1
        else:
            failures += 1

        if successes >= _DEATH_SAVE_SUCCESS_THRESHOLD:
            updated = replace(
                actor,
                death_save_successes=_DEATH_SAVE_SUCCESS_THRESHOLD,
                death_save_failures=failures,
                conditions=(
                    *(c for c in actor.conditions if c != "unconscious"),
                    "stable",
                ),
            )
        elif failures >= _DEATH_SAVE_FAILURE_THRESHOLD:
            updated = replace(
                actor,
                death_save_successes=successes,
                death_save_failures=_DEATH_SAVE_FAILURE_THRESHOLD,
                conditions=(
                    *(c for c in actor.conditions if c != "unconscious"),
                    "dead",
                ),
            )
        else:
            updated = replace(
                actor,
                death_save_successes=successes,
                death_save_failures=failures,
            )
        return replace(self, actor_registry=self.actor_registry.with_actor(updated))

    def get_player(self) -> ActorState:
        """Look up the player actor from the registry using campaign.player_actor_id."""
        player_actor_id = self.campaign.player_actor_id  # type: ignore[union-attr]
        player = self.actor_registry.actors.get(player_actor_id)
        if player is None:
            raise _PlayerNotFoundError(player_actor_id)
        return player

    def visible_actor_names(self) -> tuple[str, ...]:
        """Return visible actor names for actors in the current encounter."""
        state = self.encounter  # type: ignore[assignment]
        return tuple(
            self.actor_registry.actors[aid].name
            for aid in state.actor_ids
            if aid in self.actor_registry.actors
            and self.actor_registry.actors[aid].is_visible
        )

    def public_actor_summaries(self) -> tuple[str, ...]:
        """Return narration-safe summaries for actors visible in the current scene.

        When encounter.npc_presences is empty (old encounters or bare test fixtures) all
        encounter actors are included. When populated, only PCs and actively
        present NPCs appear. MENTIONED and DEPARTED NPCs are excluded.
        """
        state = self.encounter  # type: ignore[assignment]
        if not state.npc_presences:
            return tuple(
                self.actor_registry.actors[aid].narrative_summary()
                for aid in state.actor_ids
                if aid in self.actor_registry.actors
            )
        present_ids = {
            p.actor_id for p in state.npc_presences if p.status in _ACTIVE_NPC_STATUSES
        }
        return tuple(
            self.actor_registry.actors[aid].narrative_summary()
            for aid in state.actor_ids
            if aid in self.actor_registry.actors
            and (
                self.actor_registry.actors[aid].actor_type == ActorType.PC
                or aid in present_ids
            )
        )

    def to_json(self) -> dict[str, object]:
        """Serialise to a JSON-compatible dict.

        Faithfully serialises whatever actor_registry is present. The caller
        is responsible for stripping the player actor before writing to disk
        if the player is stored separately.
        """
        return {
            "campaign": _campaign_to_json(self.campaign)
            if self.campaign is not None
            else None,
            "module": _module_to_json(self.module) if self.module is not None else None,
            "encounter": self.encounter.to_dict()
            if self.encounter is not None
            else None,
            "actor_registry": self.actor_registry.to_dict(),
            "combat_state": (
                self.combat_state.to_dict() if self.combat_state is not None else None
            ),
        }

    @classmethod
    def from_json(cls, raw: dict[str, object]) -> GameState:
        """Deserialise from a JSON-compatible dict.

        Faithfully reconstructs whatever was serialised. The caller is
        responsible for merging the player back into actor_registry if the
        player was stored separately.
        """
        campaign = _campaign_from_seed(raw["campaign"]) if raw.get("campaign") else None
        module = _module_from_seed(raw["module"]) if raw.get("module") else None
        encounter = (
            EncounterState.from_dict(raw["encounter"]) if raw.get("encounter") else None
        )
        actor_registry = ActorRegistry.from_dict(
            raw.get("actor_registry") or {"actors": {}}
        )
        combat_state_raw = raw.get("combat_state")
        combat_state = (
            CombatState.from_dict(combat_state_raw)
            if isinstance(combat_state_raw, dict)
            else None
        )
        return cls(
            campaign=campaign,
            module=module,
            encounter=encounter,
            actor_registry=actor_registry,
            combat_state=combat_state,
        )


@dataclass(frozen=True)
class EncounterReady:
    """Returned by EncounterPlannerOrchestrator.prepare() on success.

    module may differ from the input module if recovery occurred.
    Callers must use EncounterReady.module, not their local reference.
    """

    encounter_state: EncounterState
    module: ModuleState


@dataclass(frozen=True)
class MilestoneAchieved:
    """Returned by EncounterPlannerOrchestrator.prepare() when milestone is complete.

    Signals ModuleOrchestrator to advance to the next module.
    """


# --- Campaign serialisation helpers ---


def _campaign_to_json(c: CampaignState) -> dict[str, object]:
    return {
        "campaign_id": c.campaign_id,
        "name": c.name,
        "setting": c.setting,
        "narrator_personality": c.narrator_personality,
        "hidden_goal": c.hidden_goal,
        "bbeg_name": c.bbeg_name,
        "bbeg_description": c.bbeg_description,
        "milestones": [_milestone_to_json(m) for m in c.milestones],
        "current_milestone_index": c.current_milestone_index,
        "starting_level": c.starting_level,
        "target_level": c.target_level,
        "player_brief": c.player_brief,
        "player_actor_id": c.player_actor_id,
        "bbeg_actor_id": c.bbeg_actor_id,
        "current_module_id": c.current_module_id,
    }


def _milestone_to_json(m: Milestone) -> dict[str, object]:
    return {
        "milestone_id": m.milestone_id,
        "title": m.title,
        "description": m.description,
        "completed": m.completed,
    }


def _campaign_from_seed(seed: object) -> CampaignState:
    if not isinstance(seed, Mapping):
        raise _InvalidCampaignSeedError()
    return CampaignState(
        campaign_id=str(seed["campaign_id"]),
        name=str(seed["name"]),
        setting=str(seed["setting"]),
        narrator_personality=str(seed["narrator_personality"]),
        hidden_goal=str(seed["hidden_goal"]),
        bbeg_name=str(seed["bbeg_name"]),
        bbeg_description=str(seed["bbeg_description"]),
        milestones=tuple(_milestone_from_seed(m) for m in seed.get("milestones", [])),
        current_milestone_index=int(seed["current_milestone_index"]),
        starting_level=int(seed["starting_level"]),
        target_level=int(seed["target_level"]),
        player_brief=str(seed["player_brief"]),
        player_actor_id=str(seed["player_actor_id"]),
        bbeg_actor_id=(
            str(seed["bbeg_actor_id"])
            if seed.get("bbeg_actor_id") is not None
            else None
        ),
        current_module_id=(
            str(seed["current_module_id"])
            if seed.get("current_module_id") is not None
            else None
        ),
    )


def _milestone_from_seed(seed: object) -> Milestone:
    if not isinstance(seed, Mapping):
        raise _InvalidMilestoneSeedError()
    return Milestone(
        milestone_id=str(seed["milestone_id"]),
        title=str(seed["title"]),
        description=str(seed["description"]),
        completed=bool(seed.get("completed", False)),
    )


# --- Module serialisation helpers ---


def _module_to_json(m: ModuleState) -> dict[str, object]:
    return {
        "module_id": m.module_id,
        "campaign_id": m.campaign_id,
        "title": m.title,
        "summary": m.summary,
        "guiding_milestone_id": m.guiding_milestone_id,
        "completed_encounter_ids": list(m.completed_encounter_ids),
        "completed_encounter_summaries": list(m.completed_encounter_summaries),
        "completed": m.completed,
        "planned_encounters": [t.model_dump() for t in m.planned_encounters],
        "next_encounter_index": m.next_encounter_index,
    }


def _module_from_seed(seed: object) -> ModuleState:
    if not isinstance(seed, Mapping):
        raise _InvalidModuleSeedError()
    raw = dict(seed)
    raw.pop("next_encounter_seed", None)
    planned_raw = raw.pop("planned_encounters", [])
    return ModuleState(
        module_id=str(raw["module_id"]),
        campaign_id=str(raw["campaign_id"]),
        title=str(raw["title"]),
        summary=str(raw["summary"]),
        guiding_milestone_id=str(raw["guiding_milestone_id"]),
        completed_encounter_ids=tuple(
            str(e) for e in raw.get("completed_encounter_ids", [])
        ),
        completed_encounter_summaries=tuple(
            str(s) for s in raw.get("completed_encounter_summaries", [])
        ),
        completed=bool(raw.get("completed", False)),
        planned_encounters=tuple(
            EncounterTemplate.model_validate(t) for t in planned_raw
        ),
        next_encounter_index=int(raw.get("next_encounter_index", 0)),
    )
