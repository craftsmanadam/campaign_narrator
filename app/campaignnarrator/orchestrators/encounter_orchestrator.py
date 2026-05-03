"""Encounter-loop orchestrator."""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace

from campaignnarrator.agents.narrator_agent import NarratorAgent
from campaignnarrator.agents.player_intent_agent import PlayerIntentAgent
from campaignnarrator.agents.rules_agent import RulesAgent
from campaignnarrator.domain.models import (
    ActorState,
    CombatState,
    CombatStatus,
    EncounterPhase,
    EncounterState,
    GameState,
    InitiativeTurn,
    IntentCategory,
    Narration,
    NarrationFrame,
    NpcPresenceStatus,
    PlayerInput,
    PlayerIntent,
    PlayerIO,
    RollVisibility,
    RulesAdjudication,
    RulesAdjudicationRequest,
    StateEffect,
    TurnOrder,
    TurnResources,
)
from campaignnarrator.orchestrators.combat_orchestrator import CombatOrchestrator
from campaignnarrator.repositories.game_state_repository import GameStateRepository
from campaignnarrator.repositories.narrative_memory_repository import (
    NarrativeMemoryRepository,
)
from campaignnarrator.tools.dice import roll
from campaignnarrator.tools.state_updates import require_int

_log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OrchestratorRepositories:
    """Repository dependencies for EncounterOrchestrator."""

    memory: NarrativeMemoryRepository
    game_state: GameStateRepository


@dataclass(frozen=True, slots=True)
class OrchestratorAgents:
    """Agent dependencies for EncounterOrchestrator."""

    rules: RulesAgent
    narrator: NarratorAgent


class EncounterOrchestrator:
    """Coordinate player input, rules adjudication, state, and narration."""

    def __init__(
        self,
        *,
        repositories: OrchestratorRepositories,
        agents: OrchestratorAgents,
        io: PlayerIO,
        adapter: object | None = None,
        _player_intent_agent: object | None = None,
        _combat_intent_agent: object | None = None,
    ) -> None:
        self._rules_agent = agents.rules
        self._narrator_agent = agents.narrator
        self._io = io
        self._memory_repository = repositories.memory
        self._game_state_repo = repositories.game_state
        self._adapter = adapter
        self._combat_intent_agent = _combat_intent_agent
        if _player_intent_agent is not None:
            self._player_intent_agent = _player_intent_agent
        else:
            if adapter is None:
                msg = (
                    "EncounterOrchestrator requires adapter= or "
                    "_player_intent_agent= to be set"
                )
                raise ValueError(msg)
            self._player_intent_agent = PlayerIntentAgent(adapter=adapter)

    def run(
        self,
        game_state: GameState,
    ) -> GameState:
        """Primary interface: run the encounter loop and return updated GameState.

        Uses GameStateRepository for all state persistence. Callers must
        guarantee game_state.encounter and game_state.campaign are not None.
        """
        state = game_state.encounter  # type: ignore[assignment]
        cid = game_state.campaign.campaign_id  # type: ignore[union-attr]
        self._narrator_agent.set_campaign_context(cid)

        if state.phase is EncounterPhase.SCENE_OPENING:
            opening, game_state = self._narrate(
                _frame(game_state, "scene_opening"),
                game_state,
            )
            updated = replace(
                game_state.encounter,
                phase=EncounterPhase.SOCIAL,
                scene_tone=opening.scene_tone,
            )
            game_state = game_state.with_encounter(updated)
            self._io.display(opening.text)
            self._game_state_repo.persist(game_state)
            self._memory_repository.update_exchange("", opening.text)
        elif self._memory_repository.get_exchange_buffer():
            self._io.display("--- Resuming session ---")
            for entry in self._memory_repository.get_exchange_buffer():
                self._io.display(entry)
            self._io.display("---")
            state = game_state.encounter
            prior_context = self._retrieve_prior_context(
                state.current_location or state.setting,
                campaign_id=game_state.campaign.campaign_id,  # type: ignore[union-attr]
            )
            resume_frame = replace(
                _frame(
                    game_state,
                    "session_resume",
                    resolved_outcomes=state.public_events,
                ),
                prior_narrative_context=prior_context,
            )
            resume_narration, game_state = self._narrate(resume_frame, game_state)
            self._io.display(resume_narration.text)

        if game_state.encounter.phase is EncounterPhase.ENCOUNTER_COMPLETE:
            self._game_state_repo.persist(game_state)
            return game_state

        game_state = self._run_loop(game_state)
        self._game_state_repo.persist(game_state)
        return game_state

    def _run_loop(
        self,
        game_state: GameState,
    ) -> GameState:
        """Main interaction loop — runs until combat, quit, or encounter complete."""
        while True:
            if game_state.encounter.phase is EncounterPhase.COMBAT:
                game_state = self._run_combat(game_state)
                break

            if game_state.encounter.phase is EncounterPhase.ENCOUNTER_COMPLETE:
                break

            raw_input = self._io.prompt("> ")
            player_input = PlayerInput(raw_text=raw_input)
            if not player_input.normalized:
                continue

            intent = self._classify_intent(game_state, player_input)

            match intent.category:
                case IntentCategory.SAVE_EXIT:
                    partial_summary = self._narrator_agent.summarize_encounter_partial(
                        game_state.encounter
                    )
                    self._memory_repository.stage_narration(
                        partial_summary,
                        {
                            "event_type": "encounter_partial_summary",
                            "encounter_id": game_state.encounter.encounter_id,
                            "campaign_id": game_state.campaign.campaign_id,
                            "module_id": "",
                        },
                    )
                    self._game_state_repo.persist(game_state)
                    msg = "Game saved. You can resume this encounter later."
                    self._io.display(msg)
                    self._append_event(
                        {
                            "type": "encounter_saved",
                            "encounter_id": game_state.encounter.encounter_id,
                            "phase": game_state.encounter.phase.value,
                            "outcome": game_state.encounter.outcome,
                        }
                    )
                    break
                case IntentCategory.STATUS:
                    narration, game_state = self._narrate(
                        _status_frame(game_state),
                        game_state,
                    )
                    self._io.display(narration.text)
                    continue
                case IntentCategory.RECAP:
                    narration, game_state = self._narrate(
                        _recap_frame(game_state),
                        game_state,
                    )
                    self._io.display(narration.text)
                    continue
                case IntentCategory.LOOK_AROUND:
                    narration, game_state = self._narrate(
                        _look_frame(game_state),
                        game_state,
                    )
                    self._io.display(narration.text)
                    continue

            self._io.display("\n...\n")
            game_state = self._apply_action(game_state, player_input, intent)
        return game_state

    def _classify_intent(
        self,
        game_state: GameState,
        player_input: PlayerInput,
    ) -> PlayerIntent:
        result = self._player_intent_agent.classify(
            player_input.raw_text,
            phase=game_state.encounter.phase,
            setting=game_state.encounter.setting,
            recent_events=game_state.encounter.public_events[-5:],
            actor_summaries=game_state.public_actor_summaries(),
            npc_presences=game_state.encounter.npc_presences,
        )
        _log.debug(
            "Intent classified: category=%s check_hint=%r reason=%r input=%r",
            result.category,
            result.check_hint,
            result.reason,
            player_input.raw_text,
        )
        return result

    def _apply_action(
        self,
        game_state: GameState,
        player_input: PlayerInput,
        intent: PlayerIntent,
    ) -> GameState:
        """Apply a non-combat player action; return updated GameState."""
        try:
            game_state, narration = self._handle_non_combat_action(
                game_state, player_input, intent
            )
        except ValueError:
            raise
        except Exception as exc:
            _log.exception("Action processing failed")
            msg = f"\n[Narrator encountered an error ({exc}). Please try again.]\n"
            self._io.display(msg)
            return game_state

        self._io.display(narration.text)
        self._game_state_repo.persist(game_state)
        self._memory_repository.update_exchange(player_input.raw_text, narration.text)
        return game_state

    def _run_combat(self, game_state: GameState) -> GameState:
        """Delegate the combat turn loop to CombatOrchestrator."""
        orchestrator = CombatOrchestrator(
            rules_agent=self._rules_agent,
            narrator_agent=self._narrator_agent,
            io=self._io,
            adapter=self._adapter,
            _intent_agent=self._combat_intent_agent,
            memory_repository=self._memory_repository,
            game_state_repository=self._game_state_repo,
        )
        game_state = orchestrator.run(game_state)
        status = (
            game_state.combat_state.status
            if game_state.combat_state is not None
            else CombatStatus.COMPLETE
        )
        if status is CombatStatus.COMPLETE:
            game_state = game_state.set_phase(EncounterPhase.ENCOUNTER_COMPLETE)
        self._game_state_repo.persist(game_state)
        if status is CombatStatus.SAVED_AND_QUIT:
            self._io.display("Game saved. You can resume this encounter later.")
            if game_state.encounter is not None:
                self._append_event(
                    {
                        "type": "encounter_saved",
                        "encounter_id": game_state.encounter.encounter_id,
                        "phase": game_state.encounter.phase.value,
                        "outcome": game_state.encounter.outcome,
                    }
                )
        return game_state

    def _handle_non_combat_action(
        self,
        game_state: GameState,
        player_input: PlayerInput,
        intent: PlayerIntent,
    ) -> tuple[GameState, Narration]:
        """Dispatch non-combat action by intent category; return updated GameState."""
        player = game_state.get_player()
        compendium_context = player.references
        match intent.category:
            case IntentCategory.HOSTILE_ACTION:
                game_state = _clear_player_hidden(game_state)
                game_state, narration = self._enter_combat(game_state)
                return game_state, narration
            case IntentCategory.SKILL_CHECK:
                return self._handle_action(
                    game_state,
                    player_input,
                    intent,
                    compendium_context,
                )
            case IntentCategory.NPC_DIALOGUE:
                game_state = _clear_player_hidden(game_state)
                narration, game_state = self._narrate(
                    replace(
                        _frame(
                            game_state,
                            "npc_dialogue",
                        ),
                        player_action=player_input.raw_text,
                    ),
                    game_state,
                )
                if narration.npc_interaction_summary and intent.target_npc_id:
                    updated_enc = game_state.encounter.update_npc_interaction(
                        intent.target_npc_id,
                        narration.npc_interaction_summary,
                    )
                    game_state = game_state.with_encounter(updated_enc)
                return game_state, narration
            case IntentCategory.SCENE_OBSERVATION:
                narration, game_state = self._narrate(
                    replace(
                        _frame(game_state, "scene_response"),
                        player_action=player_input.raw_text,
                    ),
                    game_state,
                )
                return game_state, narration
            case _:
                _log.warning(
                    "Unhandled intent category in narrative path: %s", intent.category
                )
                narration, game_state = self._narrate(
                    replace(
                        _frame(game_state, "scene_response"),
                        player_action=player_input.raw_text,
                    ),
                    game_state,
                )
                return game_state, narration

    def _handle_action(
        self,
        game_state: GameState,
        player_input: PlayerInput,
        intent: PlayerIntent,
        compendium_context: tuple[str, ...],
    ) -> tuple[GameState, Narration]:
        state = game_state.encounter
        player = game_state.get_player()
        request = RulesAdjudicationRequest(
            actor_id=state.player_actor_id,
            encounter_id=state.encounter_id,
            intent=player_input.raw_text,
            phase=state.phase,
            allowed_outcomes=("success", "failure", "complication", "peaceful"),
            check_hints=_non_empty_tuple((intent.check_hint,)),
            compendium_context=compendium_context,
            actor_modifiers=player.as_modifiers(),
        )
        self._io.display("\nConsidering the rules...\n")
        adjudication = self._rules_agent.adjudicate(request)
        game_state, roll_events, resolved_action_type = self._apply_adjudication(
            game_state, adjudication, player
        )
        for event in roll_events:
            self._io.display(event)
        if game_state.encounter.outcome is not None:
            self._append_event(
                {
                    "type": "encounter_completed",
                    "encounter_id": game_state.encounter.encounter_id,
                    "outcome": game_state.encounter.outcome,
                }
            )
        has_dc_roll = resolved_action_type is not None
        resolved_outcomes = (
            *roll_events,
            *([] if has_dc_roll else [adjudication.summary]),
        )
        narration, game_state = self._narrate(
            replace(
                _frame(
                    game_state,
                    "social_resolution",
                    resolved_outcomes=resolved_outcomes,
                    compendium_context=compendium_context,
                ),
                player_action=player_input.raw_text,
            ),
            game_state,
        )
        return game_state, narration

    def _enter_combat(
        self,
        game_state: GameState,
    ) -> tuple[GameState, Narration]:
        """Roll initiative and narrate combat opening.

        Returns the updated GameState (COMBAT phase, CombatState set) and narration.
        """
        state = game_state.encounter
        registry = game_state.actor_registry
        rolls = [
            (
                actor_id,
                registry.actors[actor_id].name,
                roll(f"1d20+{registry.actors[actor_id].initiative_bonus}"),
            )
            for actor_id in state.actor_ids
            if actor_id in registry.actors
        ]
        sorted_rolls = sorted(rolls, key=lambda entry: entry[2], reverse=True)
        ordered = tuple(
            InitiativeTurn(actor_id=actor_id, initiative_roll=r)
            for actor_id, _name, r in sorted_rolls
        )
        event = (
            "Initiative: "
            + ", ".join(f"{name} {r}" for _, name, r in sorted_rolls)
            + "."
        )
        game_state = game_state.set_phase(EncounterPhase.COMBAT)
        game_state = game_state.set_encounter_outcome("combat")
        game_state = game_state.append_public_event(event)
        initial_actor = game_state.actor_registry.actors.get(
            ordered[0].actor_id if ordered else ""
        )
        initial_resources = (
            initial_actor.get_turn_resources()
            if initial_actor is not None
            else TurnResources()
        )
        game_state = game_state.with_combat_state(
            CombatState(
                turn_order=TurnOrder(turns=ordered),
                current_turn_resources=initial_resources,
            )
        )
        self._io.display(event)
        self._append_event(
            {
                "type": "encounter_completed",
                "encounter_id": game_state.encounter.encounter_id,
                "outcome": "combat",
            }
        )
        narration, game_state = self._narrate(
            _frame(game_state, "combat_start", resolved_outcomes=(event,)),
            game_state,
        )
        return game_state, narration

    def _apply_adjudication(
        self,
        game_state: GameState,
        adjudication: RulesAdjudication,
        player: ActorState,
    ) -> tuple[GameState, tuple[str, ...], str | None]:
        resolved_action_type: str | None = None
        roll_events: list[str] = []

        for roll_request in adjudication.roll_requests:
            if roll_request.visibility is not RollVisibility.PUBLIC:
                continue
            result = roll_request.roll(player)
            _log.info("%s", result)
            roll_events.append(str(result))
            if result.difficulty_class is not None and resolved_action_type is None:
                resolved_action_type = "success" if result.evaluate() else "failure"

        # Append roll results as public events directly — no StateEffect intermediary
        for event in roll_events:
            game_state = game_state.append_public_event(event)

        if resolved_action_type is not None:
            effects_to_apply = [
                e
                for e in adjudication.state_effects
                if e.apply_on in ("always", resolved_action_type)
            ]
        else:
            effects_to_apply = list(adjudication.state_effects)

        for effect in effects_to_apply:
            game_state = _apply_single_effect(game_state, effect)

        return game_state, tuple(roll_events), resolved_action_type

    def _retrieve_prior_context(self, query: str, *, campaign_id: str) -> str:
        """Query memory for prior session context including recent exchanges."""
        parts: list[str] = self._memory_repository.retrieve_relevant(
            query, campaign_id=campaign_id, limit=3
        )
        exchange = self._memory_repository.get_exchange_buffer()
        if exchange:
            parts.append("Recent exchanges:\n" + "\n".join(exchange))
        return "\n\n".join(parts)

    def _narrate(
        self,
        frame: NarrationFrame,
        game_state: GameState,
    ) -> tuple[Narration, GameState]:
        state = game_state.encounter
        narration = self._narrator_agent.narrate(frame)
        self._memory_repository.store_narrative(
            narration.text,
            {
                "event_type": "narration",
                "encounter_id": state.encounter_id,
                "campaign_id": game_state.campaign.campaign_id,
                "module_id": "",
            },
        )
        if narration.current_location is not None:
            state = state.with_current_location(narration.current_location)
        if narration.encounter_complete and self._completion_is_allowed(
            state, narration, frame
        ):
            _log.info(
                "Narrator closed encounter %s: %s → %s",
                state.encounter_id,
                narration.completion_reason,
                narration.next_location_hint,
            )
            validated_traveling = _validate_traveling_actor_ids(
                narration.traveling_actor_ids, state
            )
            state = (
                state.with_traveling_actor_ids(validated_traveling)
                .with_next_location_hint(narration.next_location_hint)
                .with_phase(EncounterPhase.ENCOUNTER_COMPLETE)
            )
        return narration, game_state.with_encounter(state)

    def _completion_is_allowed(
        self,
        state: EncounterState,
        narration: Narration,
        frame: NarrationFrame,
    ) -> bool:
        """Validate narrator encounter_complete signal before applying phase transition.

        Requires next_location_hint (proxy for intentional signal), non-COMBAT phase,
        and an action-driven frame purpose to reject meta-calls and skill-check
        narrations.
        """
        if not narration.next_location_hint:
            _log.warning(
                "Narrator signaled encounter_complete with no next_location_hint"
                " — ignoring"
            )
            return False
        if state.phase is EncounterPhase.COMBAT:
            _log.warning(
                "Narrator signaled encounter_complete during COMBAT phase — ignoring"
            )
            return False
        if frame.purpose not in ("scene_response", "npc_dialogue"):
            _log.warning(
                "Narrator signaled encounter_complete for purpose=%r — ignoring",
                frame.purpose,
            )
            return False
        return True

    def _append_event(self, event: dict[str, object]) -> None:
        self._memory_repository.append_event(event)


def _status_frame(game_state: GameState) -> NarrationFrame:
    return _frame(
        game_state,
        "status_response",
        resolved_outcomes=("; ".join(game_state.public_actor_summaries()),),
        allowed_disclosures=("player HP", "inventory", "visible actors"),
    )


def _recap_frame(game_state: GameState) -> NarrationFrame:
    enc = game_state.encounter
    outcome = () if enc.outcome is None else (f"Outcome: {enc.outcome}",)
    return _frame(
        game_state,
        "recap_response",
        resolved_outcomes=(*game_state.encounter.public_events, *outcome),
        allowed_disclosures=("public events", "encounter outcome"),
    )


def _look_frame(game_state: GameState) -> NarrationFrame:
    enc = game_state.encounter
    return _frame(
        game_state,
        "status_response",
        resolved_outcomes=(enc.current_location or enc.setting,),
        allowed_disclosures=("setting", "visible actors"),
    )


def _frame(
    game_state: GameState,
    purpose: str,
    *,
    resolved_outcomes: tuple[str, ...] = (),
    allowed_disclosures: tuple[str, ...] = ("public encounter state",),
    compendium_context: tuple[str, ...] = (),
) -> NarrationFrame:
    return NarrationFrame(
        purpose=purpose,
        phase=game_state.encounter.phase,
        setting=game_state.encounter.current_location or game_state.encounter.setting,
        public_actor_summaries=game_state.public_actor_summaries(),
        npc_presences=tuple(
            p
            for p in game_state.encounter.npc_presences
            if p.status is not NpcPresenceStatus.DEPARTED
        ),
        recent_public_events=game_state.encounter.public_events[-5:],
        resolved_outcomes=resolved_outcomes,
        allowed_disclosures=allowed_disclosures,
        compendium_context=compendium_context,
        tone_guidance=game_state.encounter.scene_tone,
    )


def _non_empty_tuple(values: tuple[str | None, ...]) -> tuple[str, ...]:
    return tuple(value for value in values if value)


def _clear_player_hidden(game_state: GameState) -> GameState:
    """Clear the hidden condition from the player actor when they reveal themselves."""
    if game_state.encounter is None:
        return game_state
    player_id = game_state.encounter.player_actor_id
    player = game_state.actor_registry.actors.get(player_id)
    if player is None or not player.has_condition("hidden"):
        return game_state
    return game_state.remove_condition(player_id, "hidden")


def _apply_single_effect(game_state: GameState, effect: StateEffect) -> GameState:
    """Apply one StateEffect to game_state and return the updated GameState."""
    match effect.effect_type:
        case "set_phase":
            game_state = game_state.set_phase(EncounterPhase(str(effect.value)))
        case "set_encounter_outcome":
            game_state = game_state.set_encounter_outcome(str(effect.value))
        case "change_hp":
            game_state = game_state.adjust_hit_points(
                effect.target, require_int(effect.value, "hp delta")
            )
        case "add_condition":
            game_state = game_state.add_condition(effect.target, str(effect.value))
        case "remove_condition":
            game_state = game_state.remove_condition(effect.target, str(effect.value))
        case "set_npc_status":
            game_state = game_state.set_npc_status(
                effect.target, NpcPresenceStatus(str(effect.value))
            )
        case "inventory_spent":
            game_state = game_state.spend_inventory(effect.target, str(effect.value))
        case _:
            _log.warning("Unknown effect type in adjudication: %s", effect.effect_type)
    return game_state


def _validate_traveling_actor_ids(
    requested_ids: tuple[str, ...],
    state: EncounterState,
) -> tuple[str, ...]:
    """Validate narrator-returned actor IDs against active NpcPresences. Exclude player.

    Only AVAILABLE and INTERACTED NPCs are eligible to travel with the player.
    IDs not found in active presences or matching the player are silently dropped
    with a warning log.
    """
    valid_ids = {
        p.actor_id
        for p in state.npc_presences
        if p.status in {NpcPresenceStatus.AVAILABLE, NpcPresenceStatus.INTERACTED}
    }
    valid_ids.discard(state.player_actor_id)
    validated = tuple(aid for aid in requested_ids if aid in valid_ids)
    ignored = tuple(aid for aid in requested_ids if aid not in valid_ids)
    if ignored:
        _log.warning("Ignoring invalid traveling_actor_ids: %s", ignored)
    return validated
