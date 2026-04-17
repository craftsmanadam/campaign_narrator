"""CombatOrchestrator: manages the player combat turn loop."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import replace
from typing import Protocol

from pydantic_ai import Agent

from campaignnarrator.domain.models import (
    ActorState,
    ActorType,
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
    RulesAdjudication,
    RulesAdjudicationRequest,
    TurnResources,
)
from campaignnarrator.tools.state_updates import apply_state_effects

_logger = logging.getLogger(__name__)

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


class _RulesAgentProtocol(Protocol):
    def adjudicate(self, request: RulesAdjudicationRequest) -> RulesAdjudication: ...


class _NarratorAgentProtocol(Protocol):
    def narrate(self, frame: NarrationFrame) -> Narration: ...


class CombatOrchestrator:
    """Manage the combat turn loop for a single encounter.

    Processes combat_turns in order. Player turns run the freeform input loop.
    NPC turns are skipped with a warning — implemented in Pass 3.
    Returns CombatResult when combat ends.
    """

    def __init__(
        self,
        *,
        rules_agent: _RulesAgentProtocol,
        narrator_agent: _NarratorAgentProtocol,
        io: PlayerIO,
        roll_dice: Callable[[str], int],
        adapter: object | None = None,
        _intent_agent: object | None = None,
    ) -> None:
        self._rules_agent = rules_agent
        self._narrator_agent = narrator_agent
        self._io = io
        self._roll_dice = roll_dice
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
            state, session_ended = self._process_turn(state, turn)
            if session_ended:
                return CombatResult(
                    status=CombatStatus.SAVED_AND_QUIT,
                    final_state=state,
                    death_saves_remaining=None,
                )
            end = self._check_end_condition(state)
            if end is not None:
                return end
        return CombatResult(
            status=CombatStatus.COMPLETE,
            final_state=state,
            death_saves_remaining=None,
        )

    def _process_turn(
        self, state: EncounterState, turn: InitiativeTurn
    ) -> tuple[EncounterState, bool]:
        actor = state.actors[turn.actor_id]

        if "dead" in actor.conditions or "incapacitated" in actor.conditions:
            return self._rotate_turns(state), False

        if "unconscious" in actor.conditions:
            state = self._auto_death_save(state, actor)
            return self._rotate_turns(state), False

        session_ended = False
        if actor.actor_type == ActorType.PC:
            state, session_ended = self._run_player_turn(state, actor)
        else:
            _logger.warning(
                "NPC turns not yet implemented — skipping %s", actor.actor_id
            )

        return self._rotate_turns(state), session_ended

    def _run_player_turn(
        self, state: EncounterState, actor: ActorState
    ) -> tuple[EncounterState, bool]:
        actor = self._reset_actor_per_turn_resources(actor)
        updated_actors = dict(state.actors)
        updated_actors[actor.actor_id] = actor
        state = replace(state, actors=updated_actors)

        resources = TurnResources(movement_remaining=actor.speed)
        self._io.display(f"--- {actor.name}'s turn ---")
        self._io.display(self._format_resources(resources))

        while True:
            raw_input = self._io.prompt("> ")
            intent = self._classify_combat_intent(raw_input)

            if intent == "end_turn":
                break

            if intent == "exit_session":
                return state, True

            if intent == "query_status":
                self._io.display(self._format_combat_status(state))
                continue

            # intent == "combat_action"
            state, resources = self._handle_combat_action(
                state, actor, raw_input, resources
            )

        return state, False

    def _handle_combat_action(
        self,
        state: EncounterState,
        actor: ActorState,
        raw_input: str,
        resources: TurnResources,
    ) -> tuple[EncounterState, TurnResources]:
        request = self._build_rules_request(state, actor, raw_input)
        adjudication = self._rules_agent.adjudicate(request)

        if not adjudication.is_legal:
            narration = self._narrator_agent.narrate(
                self._build_narrator_frame(
                    state, actor, adjudication.summary, purpose="clarification"
                )
            )
            self._io.display(narration.text)
            return state, resources

        resources, overspent = self._deduct_movement(adjudication, resources)
        if overspent:
            return state, resources

        actor_effects = tuple(
            e for e in adjudication.state_effects if e.effect_type != "movement"
        )
        state = apply_state_effects(state, actor_effects)
        resources = self._consume_resource(resources, adjudication.action_type)
        narration = self._narrator_agent.narrate(
            self._build_narrator_frame(
                state, actor, adjudication.summary, purpose="combat_turn_result"
            )
        )
        self._io.display(narration.text)
        self._io.display(self._format_resources(resources))
        return state, resources

    def _deduct_movement(
        self, adjudication: RulesAdjudication, resources: TurnResources
    ) -> tuple[TurnResources, bool]:
        for effect in adjudication.state_effects:
            if effect.effect_type == "movement":
                feet = int(effect.value)  # type: ignore[arg-type]
                if feet > resources.movement_remaining:
                    self._io.display("You've used all your movement this turn.")
                    return resources, True
                resources = replace(
                    resources,
                    movement_remaining=resources.movement_remaining - feet,
                )
        return resources, False

    def _classify_combat_intent(self, raw_input: str) -> str:
        return self._intent_agent.run_sync(
            json.dumps({"player_input": raw_input})
        ).output.intent

    def _build_rules_request(
        self, state: EncounterState, actor: ActorState, intent: str
    ) -> RulesAdjudicationRequest:
        feat_context = tuple(
            f"Feat — {feat.name}: {feat.effect_summary}" for feat in actor.feats
        )
        return RulesAdjudicationRequest(
            actor_id=actor.actor_id,
            intent=intent,
            phase=EncounterPhase.COMBAT,
            allowed_outcomes=_COMBAT_ALLOWED_OUTCOMES,
            compendium_context=feat_context,
        )

    def _build_narrator_frame(
        self,
        state: EncounterState,
        actor: ActorState,
        summary: str,
        purpose: str,
    ) -> NarrationFrame:
        return NarrationFrame(
            purpose=purpose,
            phase=EncounterPhase.COMBAT,
            setting=state.setting,
            public_actor_summaries=tuple(
                f"{a.name} HP {a.hp_current}/{a.hp_max}" for a in state.actors.values()
            ),
            visible_npc_summaries=(),
            recent_public_events=(),
            resolved_outcomes=(summary,),
            allowed_disclosures=("public encounter state",),
            tone_guidance=state.scene_tone,
        )

    def _reset_actor_per_turn_resources(self, actor: ActorState) -> ActorState:
        updated = tuple(
            replace(r, current=r.max) if r.recovers_after == RecoveryPeriod.TURN else r
            for r in actor.resources
        )
        return replace(actor, resources=updated)

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
        summaries = [
            f"{a.name} HP {a.hp_current}/{a.hp_max}" for a in state.actors.values()
        ]
        return " | ".join(summaries)

    def _rotate_turns(self, state: EncounterState) -> EncounterState:
        if not state.combat_turns:
            return state
        turns = state.combat_turns
        return replace(state, combat_turns=(*turns[1:], turns[0]))

    def _check_end_condition(self, state: EncounterState) -> CombatResult | None:
        pc_actors = [a for a in state.actors.values() if a.actor_type == ActorType.PC]
        npc_actors = [
            a
            for a in state.actors.values()
            if a.actor_type in (ActorType.NPC, ActorType.ALLY)
        ]

        all_npcs_down = all(
            "dead" in a.conditions or a.hp_current <= 0 for a in npc_actors
        )
        if all_npcs_down and npc_actors:
            return CombatResult(
                status=CombatStatus.COMPLETE,
                final_state=state,
                death_saves_remaining=None,
            )

        conscious_allies = [
            a
            for a in state.actors.values()
            if a.actor_type in (ActorType.PC, ActorType.ALLY)
            and a.hp_current > 0
            and "dead" not in a.conditions
            and "unconscious" not in a.conditions
        ]
        # Include dead PCs so _auto_death_save → death triggers this end condition.
        downed_or_dead_pcs = [
            a for a in pc_actors if a.hp_current <= 0 or "dead" in a.conditions
        ]
        if downed_or_dead_pcs and not conscious_allies:
            # Prefer a still-downed (not yet dead) PC for death-save tracking.
            downed = next(
                (a for a in downed_or_dead_pcs if "dead" not in a.conditions),
                downed_or_dead_pcs[0],
            )
            saves_remaining = max(0, 3 - downed.death_save_failures)
            return CombatResult(
                status=CombatStatus.PLAYER_DOWN_NO_ALLIES,
                final_state=state,
                death_saves_remaining=saves_remaining,
            )

        return None

    def _auto_death_save(
        self, state: EncounterState, actor: ActorState
    ) -> EncounterState:
        roll = self._roll_dice("1d20")
        successes = actor.death_save_successes
        failures = actor.death_save_failures

        if roll == 1:
            failures += 2
        elif roll == 20:  # noqa: PLR2004
            successes += 2
        elif roll >= 10:  # noqa: PLR2004
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
            outcome = "success" if (roll == 20 or roll >= 10) else "failure"  # noqa: PLR2004
            self._io.display(
                f"{actor.name} makes a death saving throw... {outcome} (rolled {roll})."
            )

        updated_actors = dict(state.actors)
        updated_actors[actor.actor_id] = updated
        return replace(state, actors=updated_actors)
