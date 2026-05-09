"""CombatOrchestrator: manages the player combat turn loop."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Protocol

from pydantic_ai import Agent

from campaignnarrator.domain.models import (
    ActorState,
    ActorType,
    CombatAssessment,
    CombatIntent,
    CombatStatus,
    EncounterPhase,
    GameState,
    Narration,
    NarrationFrame,
    NpcPresenceStatus,
    PlayerIO,
    ResourceUnavailableError,
    RollVisibility,
    RulesAdjudication,
    RulesAdjudicationRequest,
    StateEffect,
    TurnResources,
    WeaponState,
)
from campaignnarrator.repositories.game_state_repository import GameStateRepository
from campaignnarrator.repositories.narrative_memory_repository import (
    NarrativeMemoryRepository,
)
from campaignnarrator.tools.dice import roll
from campaignnarrator.tools.state_updates import require_int

_logger = logging.getLogger(__name__)

# Death save display thresholds — D&D 5e core rules (also defined in GameState)
_DEATH_SAVE_NAT_TWENTY = 20
_DEATH_SAVE_MIN_SUCCESS_ROLL = 10


@dataclass(frozen=True)
class _TurnResult:
    """Internal per-turn return value.

    narration is None when the turn was skipped (dead/incapacitated actor).
    player_input is empty for NPC turns and skipped turns.
    game_state.combat_state.status encodes terminal conditions:
      SAVED_AND_QUIT means player exited; anything non-ACTIVE breaks the loop.
    """

    game_state: GameState
    narration: str | None
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
    """Format a weapon's attack and damage stats as a single-line context string."""
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
    """Format an actor's identity and combat stats as a single-line context string."""
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
    registry,  # ActorRegistry — avoid circular import; duck-typed
    effect: StateEffect,
    attack_total: int,
    damage_total: int | None,
) -> StateEffect | None:
    """Resolve one change_hp effect against target AC; return None to drop it."""
    target_actor = registry.actors.get(effect.target)
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


def _roll_heal_dice(expression: str) -> int:
    """Roll a heal dice expression like '2d6+3' and return the HP restored."""
    match_result = re.match(r"^(\d+)d(\d+)([+-]\d+)?$", expression)
    if not match_result:
        msg = f"Invalid heal dice expression: {expression!r}"
        raise ValueError(msg)
    num_dice = int(match_result.group(1))
    die_size = int(match_result.group(2))
    modifier = int(match_result.group(3) or "0")
    return sum(roll(f"1d{die_size}") for _ in range(num_dice)) + modifier


def _apply_encounter_state_effects(
    game_state: GameState, effect: StateEffect
) -> GameState:
    """Apply encounter-level state effects (phase, outcome, events, NPC status)."""
    match effect.effect_type:
        case "set_phase":
            return game_state.set_phase(EncounterPhase(str(effect.value)))
        case "set_encounter_outcome":
            return game_state.set_encounter_outcome(str(effect.value))
        case "append_public_event":
            return game_state.append_public_event(str(effect.value))
        case "set_npc_status":
            return game_state.set_npc_status(
                effect.target, NpcPresenceStatus(str(effect.value))
            )
        case _:
            return game_state


def _apply_combat_effects(
    game_state: GameState, effects: tuple[StateEffect, ...]
) -> GameState:
    """Apply player combat effects via GameState methods."""
    for effect in effects:
        match effect.effect_type:
            case "change_hp":
                game_state = game_state.adjust_hit_points(
                    effect.target, require_int(effect.value, "hp delta")
                )
            case "heal":
                game_state = game_state.adjust_hit_points(
                    effect.target, _roll_heal_dice(str(effect.value))
                )
            case "add_condition":
                game_state = game_state.add_condition(effect.target, str(effect.value))
            case "remove_condition":
                game_state = game_state.remove_condition(
                    effect.target, str(effect.value)
                )
            case "inventory_spent":
                game_state = game_state.spend_inventory(
                    effect.target, str(effect.value)
                )
            case _:
                prev = game_state
                game_state = _apply_encounter_state_effects(game_state, effect)
                if game_state is prev:
                    _logger.warning(
                        "Unknown effect type in combat: %s", effect.effect_type
                    )
    return game_state


def _apply_npc_combat_effects(
    game_state: GameState, effects: tuple[StateEffect, ...]
) -> GameState:
    """Apply NPC combat effects via GameState methods."""
    for effect in effects:
        match effect.effect_type:
            case "change_hp":
                game_state = game_state.adjust_hit_points(
                    effect.target, require_int(effect.value, "hp delta")
                )
            case "add_condition":
                game_state = game_state.add_condition(effect.target, str(effect.value))
            case "remove_condition":
                game_state = game_state.remove_condition(
                    effect.target, str(effect.value)
                )
            case "set_npc_status":
                game_state = game_state.set_npc_status(
                    effect.target, NpcPresenceStatus(str(effect.value))
                )
            case _:
                _logger.warning(
                    "Unknown effect type in NPC combat: %s", effect.effect_type
                )
    return game_state


class _RulesAgentProtocol(Protocol):
    """Structural protocol for the RulesAgent used by CombatOrchestrator."""

    def adjudicate(self, request: RulesAdjudicationRequest) -> RulesAdjudication: ...


class _NarratorAgentProtocol(Protocol):
    """Structural protocol for the NarratorAgent used by CombatOrchestrator."""

    def narrate(self, frame: NarrationFrame) -> Narration: ...
    def declare_npc_intent_from_json(self, context_json: str) -> str: ...
    def assess_combat_from_json(self, state_json: str) -> CombatAssessment: ...


class CombatOrchestrator:
    """Manage the combat turn loop for a single encounter.

    Processes the TurnOrder in CombatState. Player turns run the freeform input loop.
    NPC turns declare intent via the NarratorAgent, adjudicate via the RulesAgent,
    and apply state effects. After each active turn the NarratorAgent assesses whether
    combat is still ongoing; player-down-no-allies is detected first and short-circuits
    the assessment. Returns GameState when combat ends.
    """

    def __init__(
        self,
        *,
        rules_agent: _RulesAgentProtocol,
        narrator_agent: _NarratorAgentProtocol,
        io: PlayerIO,
        adapter: object | None = None,
        _intent_agent: object | None = None,
        memory_repository: NarrativeMemoryRepository | None = None,
        game_state_repository: GameStateRepository | None = None,
    ) -> None:
        """Store agents; build CombatIntent agent from adapter or test double."""
        self._rules_agent = rules_agent
        self._narrator_agent = narrator_agent
        self._io = io
        self._memory_repository = memory_repository
        self._game_state_repo = game_state_repository
        if _intent_agent is not None:
            self._intent_agent = _intent_agent
        elif adapter is not None:
            self._intent_agent = Agent(
                adapter.model,  # type: ignore[union-attr]
                output_type=CombatIntent,
                instructions=_COMBAT_INTENT_INSTRUCTIONS,
            )
        else:
            msg = "CombatOrchestrator requires adapter= or _intent_agent= to be set"
            raise ValueError(msg)

    def run(self, game_state: GameState) -> GameState:
        """Run the combat loop until a terminal CombatStatus is reached."""
        while (
            game_state.combat_state is not None
            and game_state.combat_state.status == CombatStatus.ACTIVE
        ):
            result = self._process_turn(game_state)
            game_state = result.game_state
            self._stage_turn_in_memory(game_state, result)

            if (
                game_state.combat_state is None
                or game_state.combat_state.status != CombatStatus.ACTIVE
            ):
                self._flush_combat_memory()
                return game_state

            if result.narration is None:
                continue

            game_state = game_state.evaluate_combat_end_conditions()
            if game_state.combat_state.status != CombatStatus.ACTIVE:
                self._flush_combat_memory()
                return game_state

            assessment = self._assess_combat(game_state, result.narration)
            if not assessment.combat_active:
                self._io.display(assessment.outcome.full_description)  # type: ignore[union-attr]
                self._flush_combat_memory()
                return game_state.with_combat_status(CombatStatus.COMPLETE)

        self._flush_combat_memory()
        return game_state

    def _stage_turn_in_memory(self, game_state: GameState, result: _TurnResult) -> None:
        """Persist per-turn state and log narration exchange."""
        if self._game_state_repo is not None:
            self._game_state_repo.persist(game_state)
        if self._memory_repository is not None and result.narration is not None:
            self._memory_repository.log_combat_round(result.narration)
            self._memory_repository.update_exchange(
                result.player_input, result.narration
            )

    def _flush_combat_memory(self) -> None:
        """Clear staged combat logs at end of combat."""
        if self._memory_repository is not None:
            self._memory_repository.clear_combat_memory()

    def _process_turn(self, game_state: GameState) -> _TurnResult:
        """Dispatch the current actor's turn: skip dead, death-save unconscious, run."""
        if game_state.combat_state is None:
            return _TurnResult(game_state=game_state, narration=None)

        actor_id = game_state.combat_state.turn_order.current_actor_id
        actor = game_state.actor_registry.actors[actor_id]  # KeyError = bug — fail fast

        if "dead" in actor.conditions or "incapacitated" in actor.conditions:
            return _TurnResult(game_state=game_state.advance_turn(), narration=None)

        if "unconscious" in actor.conditions:
            game_state = self._handle_unconscious_turn(game_state, actor)
            return _TurnResult(game_state=game_state.advance_turn(), narration=None)

        if actor.actor_type == ActorType.PC:
            result = self._run_player_turn(game_state, actor)
            # Don't advance turn if player saved/quit mid-turn — resume here next time
            if (
                result.game_state.combat_state is not None
                and result.game_state.combat_state.status != CombatStatus.ACTIVE
            ):
                return result
        elif actor.actor_type == ActorType.ALLY:
            return _TurnResult(game_state=game_state.advance_turn(), narration=None)
        else:
            result = self._run_npc_turn(game_state, actor)

        return _TurnResult(
            game_state=result.game_state.advance_turn(),
            narration=result.narration,
            player_input=result.player_input,
        )

    def _handle_unconscious_turn(
        self, game_state: GameState, actor: ActorState
    ) -> GameState:
        """Roll a death save for actor, update game_state, and display the result."""
        roll_result = roll("1d20")
        game_state = game_state.apply_death_save(actor.actor_id, roll_result)
        actor_after = game_state.actor_registry.actors[actor.actor_id]
        if "stable" in actor_after.conditions and "stable" not in actor.conditions:
            self._io.display(f"{actor.name} stabilizes!")
        elif "dead" in actor_after.conditions and "dead" not in actor.conditions:
            self._io.display(f"{actor.name} has died.")
        else:
            is_success = (
                roll_result == _DEATH_SAVE_NAT_TWENTY
                or roll_result >= _DEATH_SAVE_MIN_SUCCESS_ROLL
            )
            outcome = "success" if is_success else "failure"
            self._io.display(
                f"{actor.name} makes a death saving throw..."
                f" {outcome} (rolled {roll_result})."
            )
        return game_state

    def _run_player_turn(self, game_state: GameState, actor: ActorState) -> _TurnResult:
        """Run the player's action loop until they end their turn or exit."""
        actor = actor.reset_turn_resources()
        game_state = game_state.with_actor_registry(
            game_state.actor_registry.with_actor(actor)
        )
        if game_state.combat_state is not None:
            game_state = game_state.with_combat_state(
                game_state.combat_state.with_current_turn_resources(
                    actor.get_turn_resources()
                )
            )

        self._io.display(f"--- {actor.name}'s turn ---")
        self._io.display(f"HP: {actor.hp_current}/{actor.hp_max}")
        resources = (
            game_state.combat_state.current_turn_resources
            if game_state.combat_state
            else TurnResources(movement_remaining=actor.speed)
        )
        self._io.display(self._format_resources(resources))

        last_narration = ""
        last_player_input = ""
        player_actor_id = actor.actor_id
        while True:
            # Always read fresh actor state — stale local var may miss HP mutations
            actor = game_state.actor_registry.actors[player_actor_id]
            raw_input = self._io.prompt("> ")
            intent = self._classify_combat_intent(raw_input)

            if intent == "end_turn":
                break

            if intent == "exit_session":
                return _TurnResult(
                    game_state=game_state.with_combat_status(
                        CombatStatus.SAVED_AND_QUIT
                    ),
                    narration="",
                )

            if intent == "query_status":
                self._io.display(self._format_combat_status(game_state))
                continue

            # intent == "combat_action"
            game_state, narration_text = self._handle_combat_action(
                game_state, actor, raw_input
            )
            last_narration = narration_text
            last_player_input = raw_input

        return _TurnResult(
            game_state=game_state,
            narration=last_narration,
            player_input=last_player_input,
        )

    def _handle_combat_action(
        self,
        game_state: GameState,
        actor: ActorState,
        raw_input: str,
    ) -> tuple[GameState, str]:
        """Adjudicate raw_input as a combat action and apply resulting state effects."""
        state = game_state.encounter  # type: ignore[assignment]
        registry = game_state.actor_registry
        request = self._build_rules_request(state, registry, actor, raw_input)
        self._io.display("\nConsidering the rules...\n")
        adjudication = self._rules_agent.adjudicate(request)

        if not adjudication.is_legal:
            narration = self._narrator_agent.narrate(
                self._build_narrator_frame(
                    state,
                    registry,
                    actor,
                    adjudication.summary,
                    purpose="clarification",
                )
            )
            self._io.display(narration.text)
            return game_state, narration.text

        # Deduct movement first — bail out early if exhausted
        for effect in adjudication.state_effects:
            if effect.effect_type == "movement":
                feet = require_int(effect.value, "movement feet")
                try:
                    game_state = game_state.spend_turn_resource("movement", feet)
                except ResourceUnavailableError:
                    self._io.display("You've used all your movement this turn.")
                    return game_state, ""

        roll_events, roll_totals_by_purpose = self._roll_public_dice(
            adjudication.roll_requests, actor
        )

        # Resolve attack effects against target AC
        actor_effects = tuple(
            e for e in adjudication.state_effects if e.effect_type != "movement"
        )
        resolved_effects = self._resolve_attack_effects(
            game_state.actor_registry, actor_effects, roll_totals_by_purpose
        )

        game_state = _apply_combat_effects(game_state, resolved_effects)
        game_state = game_state.apply_zero_hp_conditions()
        game_state = self._consume_action_resource(game_state, adjudication.action_type)

        resources = (
            game_state.combat_state.current_turn_resources
            if game_state.combat_state
            else TurnResources()
        )
        # Re-read actor from registry for narration (HP may have changed)
        actor = game_state.actor_registry.actors[actor.actor_id]
        narration = self._narrator_agent.narrate(
            self._build_narrator_frame(
                game_state.encounter,  # type: ignore[arg-type]
                game_state.actor_registry,
                actor,
                adjudication.summary,
                purpose="combat_turn_result",
                roll_events=roll_events,
            )
        )
        self._io.display(narration.text)
        self._io.display(self._format_resources(resources))
        return game_state, narration.text

    def _roll_public_dice(
        self,
        roll_requests: tuple,  # tuple[RollRequest, ...]
        actor: ActorState,
    ) -> tuple[tuple[str, ...], dict[str, int]]:
        """Roll PUBLIC dice, display results, return (events, totals_by_purpose)."""
        roll_event_strings: list[str] = []
        roll_totals_by_purpose: dict[str, int] = {}
        for rr in roll_requests:
            if rr.visibility is RollVisibility.PUBLIC:
                result = rr.roll(actor)
                _logger.info("%s", result)
                roll_event_strings.append(str(result))
                if result.purpose:
                    roll_totals_by_purpose[result.purpose] = result.roll_total
        roll_events = tuple(roll_event_strings)
        for event in roll_events:
            self._io.display(event)
        return roll_events, roll_totals_by_purpose

    def _consume_action_resource(
        self, game_state: GameState, action_type: str
    ) -> GameState:
        """Deduct the action economy resource consumed by action_type.

        free_action intentionally consumes nothing. ResourceUnavailableError
        after an approved adjudication is a rules-agent inconsistency — log it
        but do not abort the turn.
        """
        if action_type == "attack":
            try:
                game_state = game_state.spend_turn_resource("action")
            except ResourceUnavailableError:
                _logger.warning(
                    "Rules agent approved %r but action resource already spent",
                    action_type,
                )
        elif action_type == "bonus_action":
            try:
                game_state = game_state.spend_turn_resource("bonus_action")
            except ResourceUnavailableError:
                _logger.warning(
                    "Rules agent approved %r but bonus_action resource already spent",
                    action_type,
                )
        return game_state

    def _run_npc_turn(self, game_state: GameState, actor: ActorState) -> _TurnResult:
        """Declare NPC intent, adjudicate it, apply effects, and narrate."""
        actor = actor.reset_turn_resources()
        game_state = game_state.with_actor_registry(
            game_state.actor_registry.with_actor(actor)
        )
        # Read-only extraction for LLM context building
        state = game_state.encounter  # type: ignore[assignment]
        registry = game_state.actor_registry

        intent_payload = {
            "actor_id": actor.actor_id,
            "name": actor.name,
            "hp_current": actor.hp_current,
            "hp_max": actor.hp_max,
            "conditions": list(actor.conditions),
            "visible_actors": [
                {
                    "actor_id": registry.actors[aid].actor_id,
                    "name": registry.actors[aid].name,
                    "hp_current": registry.actors[aid].hp_current,
                    "hp_max": registry.actors[aid].hp_max,
                    "actor_type": registry.actors[aid].actor_type.value,
                    "conditions": list(registry.actors[aid].conditions),
                }
                for aid in state.actor_ids
                if aid in registry.actors and aid != actor.actor_id
            ],
            "setting": state.setting,
        }
        intent_prose = self._narrator_agent.declare_npc_intent_from_json(
            json.dumps(intent_payload, indent=2, sort_keys=True)
        )

        self._io.display("\nConsidering the rules...\n")
        adjudication = self._rules_agent.adjudicate(
            self._build_rules_request(
                state,
                registry,
                actor,
                intent_prose,
                allowed_outcomes=_NPC_COMBAT_ALLOWED_OUTCOMES,
            )
        )

        roll_event_strings: list[str] = []
        roll_totals_by_purpose: dict[str, int] = {}
        # NPC rolls: collect all roll totals (including hidden) for attack resolution,
        # but display only PUBLIC rolls to the player.
        for rr in adjudication.roll_requests:
            result = rr.roll(actor)
            _logger.info("%s", result)
            if result.purpose:
                roll_totals_by_purpose[result.purpose] = result.roll_total
            if rr.visibility is RollVisibility.PUBLIC:
                roll_event_strings.append(str(result))
        for event in roll_event_strings:
            self._io.display(event)
        roll_events = tuple(roll_event_strings)

        resolved_effects = self._resolve_attack_effects(
            registry, adjudication.state_effects, roll_totals_by_purpose
        )

        # Apply each effect via specific GameState methods
        game_state = _apply_npc_combat_effects(game_state, resolved_effects)
        game_state = game_state.apply_zero_hp_conditions()

        narration = self._narrator_agent.narrate(
            self._build_narrator_frame(
                game_state.encounter,  # type: ignore[arg-type]
                game_state.actor_registry,
                actor,
                adjudication.summary,
                purpose="npc_combat_action",
                roll_events=roll_events,
            )
        )
        self._io.display(narration.text)
        return _TurnResult(game_state=game_state, narration=narration.text)

    def _resolve_attack_effects(
        self,
        registry,  # ActorRegistry — duck-typed to avoid import
        effects: tuple[StateEffect, ...],
        roll_totals_by_purpose: dict[str, int],
    ) -> tuple[StateEffect, ...]:
        """Resolve change_hp effects for attack actions against target AC."""
        attack_total, damage_total = _extract_roll_totals(roll_totals_by_purpose)
        if attack_total is None:
            return effects
        resolved: list[StateEffect] = []
        for effect in effects:
            if effect.effect_type != "change_hp":
                resolved.append(effect)
                continue
            hp_effect = _resolve_hp_effect(registry, effect, attack_total, damage_total)
            if hp_effect is not None:
                resolved.append(hp_effect)
        return tuple(resolved)

    def _classify_combat_intent(self, raw_input: str) -> str:
        """Return the intent category string for the player's raw combat input."""
        return self._intent_agent.run_sync(
            json.dumps({"player_input": raw_input})
        ).output.intent

    def _build_rules_request(
        self,
        state,  # EncounterState — duck-typed
        registry,  # ActorRegistry — duck-typed
        actor: ActorState,
        intent: str,
        allowed_outcomes: tuple[str, ...] = _COMBAT_ALLOWED_OUTCOMES,
    ) -> RulesAdjudicationRequest:
        """Assemble a RulesAdjudicationRequest for the given actor's intent."""
        feat_context = tuple(
            f"Feat — {feat.name}: {feat.effect_summary}" for feat in actor.feats
        )
        inventory_context = tuple(
            f"Item — {inv.item} (item_id: {inv.item_id}, count: {inv.count})"
            for inv in actor.inventory
        )
        weapon_context = tuple(_format_weapon(w) for w in actor.equipped_weapons)
        visible_actors_context = tuple(
            _format_visible_actor(registry.actors[aid])
            for aid in state.actor_ids
            if aid in registry.actors
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
        state,  # EncounterState — duck-typed
        registry,  # ActorRegistry — duck-typed
        actor: ActorState,
        summary: str,
        purpose: str,
        roll_events: tuple[str, ...] = (),
    ) -> NarrationFrame:
        """Assemble a NarrationFrame for a combat turn result or clarification."""
        return NarrationFrame(
            purpose=purpose,
            phase=EncounterPhase.COMBAT,
            setting=state.setting,
            public_actor_summaries=tuple(
                registry.actors[aid].narrative_summary()
                for aid in state.actor_ids
                if aid in registry.actors
            ),
            recent_public_events=(),
            resolved_outcomes=(*roll_events, summary),
            allowed_disclosures=("public encounter state",),
            tone_guidance=state.scene_tone,
        )

    def _assess_combat(
        self, game_state: GameState, last_narration: str
    ) -> CombatAssessment:
        """Ask the NarratorAgent whether combat should continue after this turn."""
        state = game_state.encounter  # type: ignore[assignment]
        registry = game_state.actor_registry
        actor_summaries = [
            {
                "actor_id": registry.actors[aid].actor_id,
                "name": registry.actors[aid].name,
                "actor_type": registry.actors[aid].actor_type.value,
                "hp_current": registry.actors[aid].hp_current,
                "hp_max": registry.actors[aid].hp_max,
                "conditions": list(registry.actors[aid].conditions),
            }
            for aid in state.actor_ids
            if aid in registry.actors
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

    def _format_resources(self, resources: TurnResources) -> str:
        """Return a single-line string showing available action economy resources."""
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

    def _format_combat_status(self, game_state: GameState) -> str:
        """Return pipe-separated narrative summaries for all encounter actors."""
        if game_state.encounter is None:
            return ""
        summaries = [
            game_state.actor_registry.actors[aid].narrative_summary()
            for aid in game_state.encounter.actor_ids
            if aid in game_state.actor_registry.actors
        ]
        return " | ".join(summaries)
