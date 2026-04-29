"""CombatOrchestrator: manages the player combat turn loop."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, replace
from typing import Protocol

from pydantic_ai import Agent

from campaignnarrator.domain.models import (
    ActorState,
    ActorType,
    CombatAssessment,
    CombatIntent,
    CombatResult,
    CombatStatus,
    EncounterPhase,
    EncounterState,
    InitiativeTurn,
    Narration,
    NarrationFrame,
    PlayerIO,
    RecoveryPeriod,
    RollVisibility,
    RulesAdjudication,
    RulesAdjudicationRequest,
    StateEffect,
    TurnResources,
    WeaponState,
)
from campaignnarrator.repositories.memory_repository import MemoryRepository
from campaignnarrator.tools.dice import roll
from campaignnarrator.tools.state_updates import apply_state_effects, require_int

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _TurnResult:
    """Internal return value from _process_turn and its delegates.

    narration is None when the turn was skipped — no Narrator assessment called.
    session_ended is True only for player exit_session — never set by NPC turns.
    player_input is the raw combat action text; empty string for NPC/skipped turns.
    """

    state: EncounterState
    narration: str | None
    session_ended: bool = False
    player_input: str = ""


_COMBAT_INTENT_INSTRUCTIONS = (
    "Classify the player's input during a D&D 5e combat turn. "
    "Return only a JSON object with a single key 'intent'. "
    "Allowed values: "
    '"end_turn" — the player is done acting this turn (pass, done, finished, etc.); '
    '"query_status" — asking about HP, surroundings, what happened, or game state; '
    '"exit_session" — player wants to stop playing or save and quit; '
    '"combat_action" — any attack, spell, movement, or other combat action. '
    "Do not resolve the action — only classify it."
)

_COMBAT_ALLOWED_OUTCOMES = (
    "attack",
    "move",
    "bonus_action",
    "free_action",
    "clarifying_question",
    "impossible_action",
)

_NPC_COMBAT_ALLOWED_OUTCOMES = (
    "attack",
    "move",
    "flee",
    "disengage",
    "hide",
    "bonus_action",
)


def _format_weapon(weapon: WeaponState) -> str:
    damage = weapon.damage_dice
    if weapon.damage_bonus > 0:
        damage += f"+{weapon.damage_bonus}"
    elif weapon.damage_bonus < 0:
        damage += str(weapon.damage_bonus)
    return (
        f"Weapon — {weapon.name}: attack_bonus +{weapon.attack_bonus}, "
        f"damage {damage} {weapon.damage_type}"
    )


def _format_visible_actor(actor: ActorState) -> str:
    role = "player" if actor.actor_type == ActorType.PC else actor.actor_type.value
    return (
        f"Actor {actor.actor_id} — {actor.name} ({role}), "
        f"AC {actor.armor_class}, HP {actor.hp_current}/{actor.hp_max}"
    )


def _extract_roll_totals(
    roll_totals_by_purpose: dict[str, int],
) -> tuple[int | None, int | None]:
    """Return (attack_total, damage_total) from a purpose→total mapping."""
    attack_total: int | None = None
    damage_total: int | None = None
    for purpose, total in roll_totals_by_purpose.items():
        lower = purpose.lower()
        if lower.startswith("attack roll"):
            attack_total = total
        elif lower.startswith("damage"):
            damage_total = total
    return attack_total, damage_total


def _resolve_hp_effect(
    state: EncounterState,
    effect: StateEffect,
    attack_total: int,
    damage_total: int | None,
) -> StateEffect | None:
    """Resolve one change_hp effect against target AC; return None to drop it."""
    target_actor = state.actors.get(effect.target)
    if target_actor is None:
        return None
    if attack_total < target_actor.armor_class:
        return None  # miss: drop
    if effect.value == 0 and damage_total is not None:
        return StateEffect(
            effect_type="change_hp", target=effect.target, value=-damage_total
        )
    if effect.value != 0:
        return effect
    return None  # hit with no damage roll — skip


class _RulesAgentProtocol(Protocol):
    def adjudicate(self, request: RulesAdjudicationRequest) -> RulesAdjudication: ...


class _NarratorAgentProtocol(Protocol):
    def narrate(self, frame: NarrationFrame) -> Narration: ...
    def declare_npc_intent_from_json(self, context_json: str) -> str: ...
    def assess_combat_from_json(self, state_json: str) -> CombatAssessment: ...


class CombatOrchestrator:
    """Manage the combat turn loop for a single encounter.

    Processes combat_turns in order. Player turns run the freeform input loop.
    NPC turns declare intent via the NarratorAgent, adjudicate via the RulesAgent,
    and apply state effects including crit override. After each active turn the
    NarratorAgent assesses whether combat is still ongoing; player-down-no-allies
    is detected first and short-circuits the assessment.
    Returns CombatResult when combat ends.
    """

    def __init__(
        self,
        *,
        rules_agent: _RulesAgentProtocol,
        narrator_agent: _NarratorAgentProtocol,
        io: PlayerIO,
        adapter: object | None = None,
        _intent_agent: object | None = None,
        memory_repository: MemoryRepository | None = None,
    ) -> None:
        self._rules_agent = rules_agent
        self._narrator_agent = narrator_agent
        self._io = io
        self._memory_repository = memory_repository
        if _intent_agent is not None:
            self._intent_agent = _intent_agent
        elif adapter is not None:
            self._intent_agent = Agent(
                adapter.model,  # type: ignore[union-attr]
                output_type=CombatIntent,
                instructions=_COMBAT_INTENT_INSTRUCTIONS,
            )
        else:
            raise ValueError(  # noqa: TRY003
                "CombatOrchestrator requires adapter= or _intent_agent= to be set"
            )

    def run(self, state: EncounterState) -> CombatResult:
        """Run the combat loop until an end condition is reached."""
        while state.combat_turns:
            turn = state.combat_turns[0]
            result = self._process_turn(state, turn)
            state = result.state
            self._stage_turn_in_memory(state, result)

            if result.session_ended:
                self._flush_combat_memory()
                return CombatResult(
                    status=CombatStatus.SAVED_AND_QUIT,
                    final_state=state,
                    death_saves_remaining=None,
                )

            if result.narration is None:
                continue

            down_result = self._check_player_down_no_allies(state)
            if down_result is not None:
                self._flush_combat_memory()
                return down_result

            assessment = self._assess_combat(state, result.narration)
            if not assessment.combat_active:
                self._io.display(assessment.outcome.full_description)  # type: ignore[union-attr]
                self._flush_combat_memory()
                return CombatResult(
                    status=CombatStatus.COMPLETE,
                    final_state=state,
                    death_saves_remaining=None,
                )

        self._flush_combat_memory()
        return CombatResult(
            status=CombatStatus.COMPLETE,
            final_state=state,
            death_saves_remaining=None,
        )

    def _stage_turn_in_memory(self, state: EncounterState, result: _TurnResult) -> None:
        """Stage per-turn game state and exchange in memory repository."""
        if self._memory_repository is None:
            return
        gs = self._memory_repository.load_game_state()
        updated_registry = gs.actor_registry.with_actors(state.actors)
        self._memory_repository.update_game_state(
            replace(gs, encounter=state, actor_registry=updated_registry)
        )
        if result.narration is not None:
            self._memory_repository.log_combat_round(result.narration)
            self._memory_repository.update_exchange(
                result.player_input, result.narration
            )

    def _flush_combat_memory(self) -> None:
        """Clear staged combat logs at end of combat."""
        if self._memory_repository is not None:
            self._memory_repository.clear_combat_memory()

    def _process_turn(self, state: EncounterState, turn: InitiativeTurn) -> _TurnResult:
        actor = state.actors[turn.actor_id]

        if "dead" in actor.conditions or "incapacitated" in actor.conditions:
            return _TurnResult(state=self._rotate_turns(state), narration=None)

        if "unconscious" in actor.conditions:
            state = self._auto_death_save(state, actor)
            return _TurnResult(state=self._rotate_turns(state), narration=None)

        if actor.actor_type == ActorType.PC:
            result = self._run_player_turn(state, actor)
        elif actor.actor_type == ActorType.ALLY:
            return _TurnResult(state=self._rotate_turns(state), narration=None)
        else:
            result = self._run_npc_turn(state, actor)

        return _TurnResult(
            state=self._rotate_turns(result.state),
            narration=result.narration,
            session_ended=result.session_ended,
            player_input=result.player_input,
        )

    def _run_player_turn(self, state: EncounterState, actor: ActorState) -> _TurnResult:
        actor = self._reset_actor_per_turn_resources(actor)
        updated_actors = dict(state.actors)
        updated_actors[actor.actor_id] = actor
        state = replace(state, actors=updated_actors)

        resources = TurnResources(movement_remaining=actor.speed)
        self._io.display(f"--- {actor.name}'s turn ---")
        self._io.display(self._format_resources(resources))

        last_narration = ""
        last_player_input = ""
        while True:
            raw_input = self._io.prompt("> ")
            intent = self._classify_combat_intent(raw_input)

            if intent == "end_turn":
                break

            if intent == "exit_session":
                return _TurnResult(state=state, narration="", session_ended=True)

            if intent == "query_status":
                self._io.display(self._format_combat_status(state))
                continue

            # intent == "combat_action"
            state, resources, narration_text = self._handle_combat_action(
                state, actor, raw_input, resources
            )
            last_narration = narration_text
            last_player_input = raw_input

        return _TurnResult(
            state=state, narration=last_narration, player_input=last_player_input
        )

    def _handle_combat_action(
        self,
        state: EncounterState,
        actor: ActorState,
        raw_input: str,
        resources: TurnResources,
    ) -> tuple[EncounterState, TurnResources, str]:
        request = self._build_rules_request(state, actor, raw_input)
        self._io.display("\nConsidering the rules...\n")
        adjudication = self._rules_agent.adjudicate(request)

        if not adjudication.is_legal:
            narration = self._narrator_agent.narrate(
                self._build_narrator_frame(
                    state, actor, adjudication.summary, purpose="clarification"
                )
            )
            self._io.display(narration.text)
            return state, resources, narration.text

        resources, overspent = self._deduct_movement(adjudication, resources)
        if overspent:
            return state, resources, ""

        roll_event_strings: list[str] = []
        roll_totals_by_purpose: dict[str, int] = {}
        for rr in adjudication.roll_requests:
            if rr.visibility is RollVisibility.PUBLIC:
                result = rr.roll(actor)
                _logger.info("%s", result)
                roll_event_strings.append(str(result))
                if result.purpose:
                    roll_totals_by_purpose[result.purpose] = result.roll_total
        roll_events = tuple(roll_event_strings)
        for event in roll_events:
            self._io.display(event)

        actor_effects = tuple(
            e for e in adjudication.state_effects if e.effect_type != "movement"
        )
        resolved_effects = self._resolve_attack_effects(
            state, actor_effects, roll_totals_by_purpose
        )
        state = self._materialize_effects(state, resolved_effects)
        resources = self._consume_resource(resources, adjudication.action_type)
        narration = self._narrator_agent.narrate(
            self._build_narrator_frame(
                state,
                actor,
                adjudication.summary,
                purpose="combat_turn_result",
                roll_events=roll_events,
            )
        )
        self._io.display(narration.text)
        self._io.display(self._format_resources(resources))
        return state, resources, narration.text

    def _deduct_movement(
        self, adjudication: RulesAdjudication, resources: TurnResources
    ) -> tuple[TurnResources, bool]:
        for effect in adjudication.state_effects:
            if effect.effect_type == "movement":
                feet = require_int(effect.value, "movement feet")
                if feet > resources.movement_remaining:
                    self._io.display("You've used all your movement this turn.")
                    return resources, True
                resources = replace(
                    resources,
                    movement_remaining=resources.movement_remaining - feet,
                )
        return resources, False

    def _resolve_attack_effects(
        self,
        state: EncounterState,
        effects: tuple[StateEffect, ...],
        roll_totals_by_purpose: dict[str, int],
    ) -> tuple[StateEffect, ...]:
        """Resolve change_hp effects for attack actions against target AC.

        When an attack roll is present (purpose case-insensitively starts with
        "attack roll"), all change_hp effects are gated on the AC check:
        - Hit (attack_total >= target AC): placeholder (value=0) is replaced
          with -damage_total; non-zero change_hp is kept as-is.
        - Miss (attack_total < target AC): all change_hp effects are dropped.
        When no attack roll is present, effects pass through unchanged — this
        covers non-attack damage such as ongoing conditions.
        Purpose matching is case-insensitive.
        """
        attack_total, damage_total = _extract_roll_totals(roll_totals_by_purpose)
        if attack_total is None:
            return effects
        resolved: list[StateEffect] = []
        for effect in effects:
            if effect.effect_type != "change_hp":
                resolved.append(effect)
                continue
            hp_effect = _resolve_hp_effect(state, effect, attack_total, damage_total)
            if hp_effect is not None:
                resolved.append(hp_effect)
        return tuple(resolved)

    def _classify_combat_intent(self, raw_input: str) -> str:
        return self._intent_agent.run_sync(
            json.dumps({"player_input": raw_input})
        ).output.intent

    def _build_rules_request(
        self,
        state: EncounterState,
        actor: ActorState,
        intent: str,
        allowed_outcomes: tuple[str, ...] = _COMBAT_ALLOWED_OUTCOMES,
    ) -> RulesAdjudicationRequest:
        feat_context = tuple(
            f"Feat — {feat.name}: {feat.effect_summary}" for feat in actor.feats
        )
        inventory_context = tuple(
            f"Item — {inv.item} (item_id: {inv.item_id}, count: {inv.count})"
            for inv in actor.inventory
        )
        weapon_context = tuple(_format_weapon(w) for w in actor.equipped_weapons)
        visible_actors_context = tuple(
            _format_visible_actor(a) for a in state.actors.values()
        )
        return RulesAdjudicationRequest(
            actor_id=actor.actor_id,
            encounter_id=state.encounter_id,
            intent=intent,
            phase=EncounterPhase.COMBAT,
            allowed_outcomes=allowed_outcomes,
            compendium_context=feat_context + inventory_context + weapon_context,
            actor_modifiers=actor.as_modifiers(),
            visible_actors_context=visible_actors_context,
        )

    def _build_narrator_frame(
        self,
        state: EncounterState,
        actor: ActorState,
        summary: str,
        purpose: str,
        roll_events: tuple[str, ...] = (),
    ) -> NarrationFrame:
        return NarrationFrame(
            purpose=purpose,
            phase=EncounterPhase.COMBAT,
            setting=state.setting,
            public_actor_summaries=tuple(
                a.narrative_summary() for a in state.actors.values()
            ),
            recent_public_events=(),
            resolved_outcomes=(*roll_events, summary),
            allowed_disclosures=("public encounter state",),
            tone_guidance=state.scene_tone,
        )

    def _reset_actor_per_turn_resources(self, actor: ActorState) -> ActorState:
        updated = tuple(
            replace(r, current=r.max) if r.recovers_after == RecoveryPeriod.TURN else r
            for r in actor.resources
        )
        return replace(actor, resources=updated)

    @staticmethod
    def _apply_zero_hp_conditions(state: EncounterState) -> EncounterState:
        updated_actors = dict(state.actors)
        changed = False
        for actor_id, actor in updated_actors.items():
            if actor.hp_current > 0:
                continue
            if actor.actor_type in (ActorType.NPC, ActorType.ALLY):
                if "dead" not in actor.conditions:
                    updated_actors[actor_id] = replace(
                        actor, conditions=(*actor.conditions, "dead")
                    )
                    changed = True
            elif (
                actor.actor_type == ActorType.PC
                and "dead" not in actor.conditions
                and "unconscious" not in actor.conditions
            ):
                updated_actors[actor_id] = replace(
                    actor, conditions=(*actor.conditions, "unconscious")
                )
                changed = True
        if not changed:
            return state
        return replace(state, actors=updated_actors)

    def _materialize_effects(
        self,
        state: EncounterState,
        effects: tuple[StateEffect, ...],
    ) -> EncounterState:
        materialized: list[StateEffect] = []
        for effect in effects:
            if effect.effect_type == "heal":
                expression = str(effect.value)
                match = re.match(r"^(\d+)d(\d+)([+-]\d+)?$", expression)
                if not match:
                    raise ValueError(f"Invalid dice expression: {expression!r}")  # noqa: TRY003
                num_dice = int(match.group(1))
                die_size = int(match.group(2))
                modifier = int(match.group(3) or "0")
                total = sum(roll(f"1d{die_size}") for _ in range(num_dice)) + modifier
                materialized.append(
                    StateEffect(
                        effect_type="change_hp", target=effect.target, value=total
                    )
                )
            else:
                materialized.append(effect)
        updated_state = apply_state_effects(state, tuple(materialized))
        return self._apply_zero_hp_conditions(updated_state)

    def _run_npc_turn(self, state: EncounterState, actor: ActorState) -> _TurnResult:
        actor = self._reset_actor_per_turn_resources(actor)
        updated_actors = dict(state.actors)
        updated_actors[actor.actor_id] = actor
        state = replace(state, actors=updated_actors)

        intent_payload = {
            "actor_id": actor.actor_id,
            "name": actor.name,
            "hp_current": actor.hp_current,
            "hp_max": actor.hp_max,
            "conditions": list(actor.conditions),
            "visible_actors": [
                {
                    "actor_id": a.actor_id,
                    "name": a.name,
                    "hp_current": a.hp_current,
                    "hp_max": a.hp_max,
                    "actor_type": a.actor_type.value,
                    "conditions": list(a.conditions),
                }
                for a in state.actors.values()
                if a.actor_id != actor.actor_id
            ],
            "setting": state.setting,
        }
        intent_json = json.dumps(intent_payload, indent=2, sort_keys=True)
        intent_prose = self._narrator_agent.declare_npc_intent_from_json(intent_json)

        self._io.display("\nConsidering the rules...\n")
        adjudication = self._rules_agent.adjudicate(
            self._build_rules_request(
                state,
                actor,
                intent_prose,
                allowed_outcomes=_NPC_COMBAT_ALLOWED_OUTCOMES,
            )
        )

        roll_totals_by_purpose: dict[str, int] = {}
        for rr in adjudication.roll_requests:
            result = rr.roll(actor)
            _logger.info("%s", result)
            if result.purpose:
                roll_totals_by_purpose[result.purpose] = result.roll_total

        resolved_effects = self._resolve_attack_effects(
            state, adjudication.state_effects, roll_totals_by_purpose
        )
        state = self._materialize_effects(state, resolved_effects)

        narration = self._narrator_agent.narrate(
            self._build_narrator_frame(
                state, actor, adjudication.summary, purpose="npc_combat_action"
            )
        )
        self._io.display(narration.text)
        return _TurnResult(state=state, narration=narration.text)

    def _consume_resource(
        self, resources: TurnResources, action_type: str
    ) -> TurnResources:
        if action_type in ("attack", "free_action"):
            return replace(resources, action_available=False)
        if action_type == "bonus_action":
            return replace(resources, bonus_action_available=False)
        return resources  # move: deducted separately; other: no cost

    def _format_resources(self, resources: TurnResources) -> str:
        action = "available" if resources.action_available else "used"
        bonus = "available" if resources.bonus_action_available else "used"
        reaction = "available" if resources.reaction_available else "used"
        movement = (
            f"{resources.movement_remaining}ft remaining"
            if resources.movement_remaining > 0
            else "none remaining"
        )
        return (
            f"Action: {action} | Bonus Action: {bonus} | "
            f"Movement: {movement} | Reaction: {reaction}"
        )

    def _format_combat_status(self, state: EncounterState) -> str:
        summaries = [a.narrative_summary() for a in state.actors.values()]
        return " | ".join(summaries)

    def _rotate_turns(self, state: EncounterState) -> EncounterState:
        if not state.combat_turns:
            return state
        turns = state.combat_turns
        return replace(state, combat_turns=(*turns[1:], turns[0]))

    def _check_player_down_no_allies(
        self, state: EncounterState
    ) -> CombatResult | None:
        pc_actors = [a for a in state.actors.values() if a.actor_type == ActorType.PC]
        conscious_allies = [
            a
            for a in state.actors.values()
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
            saves_remaining = 3 - downed.death_save_failures
            return CombatResult(
                status=CombatStatus.PLAYER_DOWN_NO_ALLIES,
                final_state=state,
                death_saves_remaining=saves_remaining,
            )
        return None

    def _assess_combat(
        self, state: EncounterState, last_narration: str
    ) -> CombatAssessment:
        actor_summaries = [
            {
                "actor_id": a.actor_id,
                "name": a.name,
                "actor_type": a.actor_type.value,
                "hp_current": a.hp_current,
                "hp_max": a.hp_max,
                "conditions": list(a.conditions),
            }
            for a in state.actors.values()
        ]
        payload = {
            "actor_summaries": actor_summaries,
            "recent_events": list(state.public_events[-3:]),
            "last_narration": last_narration,
            "setting": state.setting,
        }
        return self._narrator_agent.assess_combat_from_json(
            json.dumps(payload, indent=2, sort_keys=True)
        )

    def _auto_death_save(
        self, state: EncounterState, actor: ActorState
    ) -> EncounterState:
        roll_result = roll("1d20")
        successes = actor.death_save_successes
        failures = actor.death_save_failures

        if roll_result == 1:
            failures += 2
        elif roll_result == 20:  # noqa: PLR2004
            successes += 2
        elif roll_result >= 10:  # noqa: PLR2004
            successes += 1
        else:
            failures += 1

        if successes >= 3:  # noqa: PLR2004
            updated = replace(
                actor,
                death_save_successes=3,
                death_save_failures=failures,
                conditions=(
                    *(c for c in actor.conditions if c != "unconscious"),
                    "stable",
                ),
            )
            self._io.display(f"{actor.name} stabilizes!")
        elif failures >= 3:  # noqa: PLR2004
            updated = replace(
                actor,
                death_save_successes=successes,
                death_save_failures=3,
                conditions=(
                    *(c for c in actor.conditions if c != "unconscious"),
                    "dead",
                ),
            )
            self._io.display(f"{actor.name} has died.")
        else:
            updated = replace(
                actor,
                death_save_successes=successes,
                death_save_failures=failures,
            )
            is_success = roll_result == 20 or roll_result >= 10  # noqa: PLR2004
            outcome = "success" if is_success else "failure"
            self._io.display(
                f"{actor.name} makes a death saving throw..."
                f" {outcome} (rolled {roll_result})."
            )

        updated_actors = dict(state.actors)
        updated_actors[actor.actor_id] = updated
        return replace(state, actors=updated_actors)
