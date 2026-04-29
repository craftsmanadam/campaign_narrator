"""Encounter-loop orchestrator."""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace

from campaignnarrator.agents.narrator_agent import NarratorAgent
from campaignnarrator.agents.player_intent_agent import PlayerIntentAgent
from campaignnarrator.agents.rules_agent import RulesAgent
from campaignnarrator.domain.models import (
    ActorRegistry,
    ActorState,
    CombatResult,
    CombatStatus,
    EncounterPhase,
    EncounterState,
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
    get_player,
    public_actor_summaries,
)
from campaignnarrator.orchestrators.combat_orchestrator import CombatOrchestrator
from campaignnarrator.repositories.memory_repository import MemoryRepository
from campaignnarrator.tools.dice import roll
from campaignnarrator.tools.state_updates import apply_state_effects

_log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EncounterRunResult:
    """Result of running one batch of player inputs through an encounter."""

    encounter_id: str
    output_text: str
    completed: bool


@dataclass(frozen=True, slots=True)
class OrchestratorRepositories:
    """Repository dependencies for EncounterOrchestrator."""

    memory: MemoryRepository


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

    def run_encounter(self, *, encounter_id: str) -> EncounterRunResult:
        """Run the encounter loop until an end condition is reached."""
        game_state = self._memory_repository.load_game_state()
        if game_state.encounter is None:
            msg = "no active encounter"
            raise ValueError(msg)
        registry = game_state.actor_registry
        player = get_player(registry, game_state.encounter.player_actor_id)
        output: list[str] = []
        state = game_state.encounter

        if state.phase is EncounterPhase.SCENE_OPENING:
            opening, state, registry = self._narrate(
                _frame(state, registry, "scene_opening"), state, registry
            )
            state = replace(
                state, phase=EncounterPhase.SOCIAL, scene_tone=opening.scene_tone
            )
            self._io.display(opening.text)
            output.append(opening.text)
            self._memory_repository.update_game_state(
                replace(game_state, encounter=state, actor_registry=registry)
            )
            self._memory_repository.update_exchange("", opening.text)
        elif self._memory_repository.get_exchange_buffer():
            self._io.display("--- Resuming session ---")
            for entry in self._memory_repository.get_exchange_buffer():
                self._io.display(entry)
            self._io.display("---")
            prior_context = self._retrieve_prior_context(
                state.current_location or state.setting
            )
            resume_frame = replace(
                _frame(
                    state,
                    registry,
                    "session_resume",
                    resolved_outcomes=state.public_events,
                ),
                prior_narrative_context=prior_context,
            )
            resume_narration, state, registry = self._narrate(
                resume_frame, state, registry
            )
            self._io.display(resume_narration.text)
            output.append(resume_narration.text)

        if state.phase is EncounterPhase.ENCOUNTER_COMPLETE:
            return EncounterRunResult(
                encounter_id=state.encounter_id,
                output_text="\n".join(output),
                completed=True,
            )

        state = self._run_loop(state, player, registry, output)
        return EncounterRunResult(
            encounter_id=state.encounter_id,
            output_text="\n".join(output),
            completed=state.phase is EncounterPhase.ENCOUNTER_COMPLETE,
        )

    def _run_loop(
        self,
        state: EncounterState,
        player: ActorState,
        registry: ActorRegistry,
        output: list[str],
    ) -> EncounterState:
        """Main interaction loop — runs until combat, quit, or encounter complete."""
        while True:
            if state.phase is EncounterPhase.COMBAT:
                combat_result = self._run_combat(state, registry, player)
                state = combat_result.final_state
                break

            if state.phase is EncounterPhase.ENCOUNTER_COMPLETE:
                break

            raw_input = self._io.prompt("> ")
            player_input = PlayerInput(raw_text=raw_input)
            if not player_input.normalized:
                continue

            intent = self._classify_intent(state, registry, player_input)

            match intent.category:
                case IntentCategory.SAVE_EXIT:
                    partial_summary = self._narrator_agent.summarize_encounter_partial(
                        state
                    )
                    self._memory_repository.stage_narration(
                        partial_summary,
                        {
                            "event_type": "encounter_partial_summary",
                            "encounter_id": state.encounter_id,
                            "campaign_id": "",
                            "module_id": "",
                        },
                    )
                    gs = self._memory_repository.load_game_state()
                    self._memory_repository.update_game_state(
                        replace(gs, encounter=state, actor_registry=registry)
                    )
                    msg = "Game saved. You can resume this encounter later."
                    self._io.display(msg)
                    output.append(msg)
                    self._append_event(
                        {
                            "type": "encounter_saved",
                            "encounter_id": state.encounter_id,
                            "phase": state.phase.value,
                            "outcome": state.outcome,
                        }
                    )
                    break
                case IntentCategory.STATUS:
                    narration, state, registry = self._narrate(
                        _status_frame(state, registry), state, registry
                    )
                    self._io.display(narration.text)
                    output.append(narration.text)
                    continue
                case IntentCategory.RECAP:
                    narration, state, registry = self._narrate(
                        _recap_frame(state, registry), state, registry
                    )
                    self._io.display(narration.text)
                    output.append(narration.text)
                    continue
                case IntentCategory.LOOK_AROUND:
                    narration, state, registry = self._narrate(
                        _look_frame(state, registry), state, registry
                    )
                    self._io.display(narration.text)
                    output.append(narration.text)
                    continue

            self._io.display("\n...\n")
            state, registry = self._apply_action(
                state, player_input, intent, player, registry, output
            )
        return state

    def _classify_intent(
        self,
        state: EncounterState,
        registry: ActorRegistry,
        player_input: PlayerInput,
    ) -> PlayerIntent:
        result = self._player_intent_agent.classify(
            player_input.raw_text,
            phase=state.phase,
            setting=state.setting,
            recent_events=state.public_events[-5:],
            actor_summaries=public_actor_summaries(state, registry),
            npc_presences=state.npc_presences,
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
        state: EncounterState,
        player_input: PlayerInput,
        intent: PlayerIntent,
        player: ActorState,
        registry: ActorRegistry,
        output: list[str],
    ) -> tuple[EncounterState, ActorRegistry]:
        """Apply a non-combat player action; return updated state + registry."""
        try:
            state, registry, narration = self._handle_non_combat_action(
                state, player_input, intent, player, registry
            )
        except ValueError:
            raise
        except Exception as exc:
            _log.exception("Action processing failed")
            msg = f"\n[Narrator encountered an error ({exc}). Please try again.]\n"
            self._io.display(msg)
            output.append(msg)
            return state, registry

        self._io.display(narration.text)
        output.append(narration.text)
        gs = self._memory_repository.load_game_state()
        self._memory_repository.update_game_state(
            replace(gs, encounter=state, actor_registry=registry)
        )
        self._memory_repository.update_exchange(player_input.raw_text, narration.text)
        return state, registry

    def _run_combat(
        self, state: EncounterState, registry: ActorRegistry, player: ActorState
    ) -> CombatResult:
        """Delegate the combat turn loop to CombatOrchestrator."""
        orchestrator = CombatOrchestrator(
            rules_agent=self._rules_agent,
            narrator_agent=self._narrator_agent,
            io=self._io,
            adapter=self._adapter,
            _intent_agent=self._combat_intent_agent,
            memory_repository=self._memory_repository,
        )
        result = orchestrator.run(state, registry)
        final_registry = result.final_registry
        final_state = result.final_state
        if result.status is CombatStatus.COMPLETE:
            final_state, final_registry = apply_state_effects(
                final_state,
                final_registry,
                (
                    StateEffect(
                        effect_type="set_phase",
                        target=f"encounter:{final_state.encounter_id}",
                        value="encounter_complete",
                    ),
                ),
            )
            result = replace(
                result, final_state=final_state, final_registry=final_registry
            )
        gs = self._memory_repository.load_game_state()
        self._memory_repository.update_game_state(
            replace(gs, encounter=final_state, actor_registry=final_registry)
        )

        if result.status is CombatStatus.SAVED_AND_QUIT:
            self._io.display("Game saved. You can resume this encounter later.")
            self._append_event(
                {
                    "type": "encounter_saved",
                    "encounter_id": result.final_state.encounter_id,
                    "phase": result.final_state.phase.value,
                    "outcome": result.final_state.outcome,
                }
            )
        return result

    def current_state(self) -> EncounterState | None:
        """Return the current persisted encounter state."""

        return self._memory_repository.load_game_state().encounter

    def _handle_non_combat_action(
        self,
        state: EncounterState,
        player_input: PlayerInput,
        intent: PlayerIntent,
        player: ActorState,
        registry: ActorRegistry,
    ) -> tuple[EncounterState, ActorRegistry, Narration]:
        compendium_context = player.references
        match intent.category:
            case IntentCategory.HOSTILE_ACTION:
                state, registry = _clear_player_hidden(state, registry)
                updated_state, narration = self._enter_combat(state, registry)
                return updated_state, registry, narration
            case IntentCategory.SKILL_CHECK:
                state, registry, narration = self._handle_action(
                    state, player_input, intent, compendium_context, player, registry
                )
                return state, registry, narration
            case IntentCategory.NPC_DIALOGUE:
                state, registry = _clear_player_hidden(state, registry)
                narration, state, registry = self._narrate(
                    replace(
                        _frame(state, registry, "npc_dialogue"),
                        player_action=player_input.raw_text,
                    ),
                    state,
                    registry,
                )
                if narration.npc_interaction_summary and intent.target_npc_id:
                    state = self._update_npc_interaction(
                        state, intent.target_npc_id, narration.npc_interaction_summary
                    )
                return state, registry, narration
            case IntentCategory.SCENE_OBSERVATION:
                narration, state, registry = self._narrate(
                    replace(
                        _frame(state, registry, "scene_response"),
                        player_action=player_input.raw_text,
                    ),
                    state,
                    registry,
                )
                return state, registry, narration
            case _:
                _log.warning(
                    "Unhandled intent category in narrative path: %s", intent.category
                )
                narration, state, registry = self._narrate(
                    replace(
                        _frame(state, registry, "scene_response"),
                        player_action=player_input.raw_text,
                    ),
                    state,
                    registry,
                )
                return state, registry, narration

    def _handle_action(
        self,
        state: EncounterState,
        player_input: PlayerInput,
        intent: PlayerIntent,
        compendium_context: tuple[str, ...],
        player: ActorState,
        registry: ActorRegistry,
    ) -> tuple[EncounterState, ActorRegistry, Narration]:
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
        updated_state, updated_registry, roll_events, resolved_action_type = (
            self._apply_adjudication(state, adjudication, player, registry)
        )
        for event in roll_events:
            self._io.display(event)
        if updated_state.outcome is not None:
            self._append_event(
                {
                    "type": "encounter_completed",
                    "encounter_id": updated_state.encounter_id,
                    "outcome": updated_state.outcome,
                }
            )
        has_dc_roll = resolved_action_type is not None
        resolved_outcomes = (
            *roll_events,
            *([] if has_dc_roll else [adjudication.summary]),
        )
        narration, updated_state, updated_registry = self._narrate(
            replace(
                _frame(
                    updated_state,
                    updated_registry,
                    "social_resolution",
                    resolved_outcomes=resolved_outcomes,
                    compendium_context=compendium_context,
                ),
                player_action=player_input.raw_text,
            ),
            updated_state,
            updated_registry,
        )
        return updated_state, updated_registry, narration

    def _enter_combat(
        self, state: EncounterState, registry: ActorRegistry
    ) -> tuple[EncounterState, Narration]:
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
        updated_state = replace(
            state,
            phase=EncounterPhase.COMBAT,
            combat_turns=ordered,
            outcome="combat",
            public_events=(*state.public_events, event),
        )
        self._io.display(event)
        self._append_event(
            {
                "type": "encounter_completed",
                "encounter_id": updated_state.encounter_id,
                "outcome": "combat",
            }
        )
        narration, updated_state, _registry = self._narrate(
            _frame(updated_state, registry, "combat_start", resolved_outcomes=(event,)),
            updated_state,
            registry,
        )
        return updated_state, narration

    def _apply_adjudication(
        self,
        state: EncounterState,
        adjudication: RulesAdjudication,
        player: ActorState,
        registry: ActorRegistry,
    ) -> tuple[EncounterState, ActorRegistry, tuple[str, ...], str | None]:
        # returns (updated_state, updated_registry, roll_events, action_type | None)
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

        roll_effects = tuple(
            StateEffect(
                effect_type="append_public_event",
                target=f"encounter:{state.encounter_id}",
                value=event,
            )
            for event in roll_events
        )

        if resolved_action_type is not None:
            effects_to_apply: list[StateEffect] = [
                e
                for e in adjudication.state_effects
                if e.apply_on in ("always", resolved_action_type)
            ]
        else:
            effects_to_apply = list(adjudication.state_effects)

        updated_state, updated_registry = apply_state_effects(
            state, registry, (*roll_effects, *effects_to_apply)
        )
        return updated_state, updated_registry, tuple(roll_events), resolved_action_type

    def _retrieve_prior_context(self, query: str) -> str:
        """Query memory for prior session context including recent exchanges."""
        parts: list[str] = self._memory_repository.retrieve_relevant(query, limit=3)
        exchange = self._memory_repository.get_exchange_buffer()
        if exchange:
            parts.append("Recent exchanges:\n" + "\n".join(exchange))
        return "\n\n".join(parts)

    def _narrate(
        self, frame: NarrationFrame, state: EncounterState, registry: ActorRegistry
    ) -> tuple[Narration, EncounterState, ActorRegistry]:
        narration = self._narrator_agent.narrate(frame)
        self._memory_repository.store_narrative(
            narration.text,
            {
                "event_type": "narration",
                "encounter_id": state.encounter_id,
                "campaign_id": "",
                "module_id": "",
            },
        )
        if narration.current_location is not None:
            state = replace(state, current_location=narration.current_location)
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
            state = replace(
                state,
                traveling_actor_ids=validated_traveling,
                next_location_hint=narration.next_location_hint,
            )
            state, registry = apply_state_effects(
                state,
                registry,
                (
                    StateEffect(
                        effect_type="set_phase",
                        target=f"encounter:{state.encounter_id}",
                        value="encounter_complete",
                    ),
                ),
            )
        return narration, state, registry

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

    def _update_npc_interaction(
        self,
        state: EncounterState,
        target_npc_id: str,
        summary: str,
    ) -> EncounterState:
        """Mark NPC as INTERACTED and append summary to their interaction history.

        Returns state unchanged (with a warning) if no matching NpcPresence is found.
        """
        presences = list(state.npc_presences)
        for i, presence in enumerate(presences):
            if presence.actor_id == target_npc_id:
                presences[i] = replace(
                    presence,
                    status=NpcPresenceStatus.INTERACTED,
                    interaction_summaries=(*presence.interaction_summaries, summary),
                )
                return replace(state, npc_presences=tuple(presences))
        _log.warning(
            "NPC_DIALOGUE: no NpcPresence found for actor_id %r"
            " — skipping interaction update",
            target_npc_id,
        )
        return state

    def _append_event(self, event: dict[str, object]) -> None:
        self._memory_repository.append_event(event)


def _status_frame(state: EncounterState, registry: ActorRegistry) -> NarrationFrame:
    return _frame(
        state,
        registry,
        "status_response",
        resolved_outcomes=("; ".join(public_actor_summaries(state, registry)),),
        allowed_disclosures=("player HP", "inventory", "visible actors"),
    )


def _recap_frame(state: EncounterState, registry: ActorRegistry) -> NarrationFrame:
    outcome = () if state.outcome is None else (f"Outcome: {state.outcome}",)
    return _frame(
        state,
        registry,
        "recap_response",
        resolved_outcomes=(*state.public_events, *outcome),
        allowed_disclosures=("public events", "encounter outcome"),
    )


def _look_frame(state: EncounterState, registry: ActorRegistry) -> NarrationFrame:
    return _frame(
        state,
        registry,
        "status_response",
        resolved_outcomes=(state.setting,),
        allowed_disclosures=("setting", "visible actors"),
    )


def _frame(
    state: EncounterState,
    registry: ActorRegistry,
    purpose: str,
    *,
    resolved_outcomes: tuple[str, ...] = (),
    allowed_disclosures: tuple[str, ...] = ("public encounter state",),
    compendium_context: tuple[str, ...] = (),
) -> NarrationFrame:
    return NarrationFrame(
        purpose=purpose,
        phase=state.phase,
        setting=state.current_location or state.setting,
        public_actor_summaries=public_actor_summaries(state, registry),
        npc_presences=tuple(
            p for p in state.npc_presences if p.status is not NpcPresenceStatus.DEPARTED
        ),
        recent_public_events=state.public_events[-5:],
        resolved_outcomes=resolved_outcomes,
        allowed_disclosures=allowed_disclosures,
        compendium_context=compendium_context,
        tone_guidance=state.scene_tone,
    )


def _non_empty_tuple(values: tuple[str | None, ...]) -> tuple[str, ...]:
    return tuple(value for value in values if value)


def _clear_player_hidden(
    state: EncounterState, registry: ActorRegistry
) -> tuple[EncounterState, ActorRegistry]:
    """Clear the hidden condition from the player actor when they reveal themselves."""
    player_id = state.player_actor_id
    player = registry.actors.get(player_id)
    if player is None or not player.has_condition("hidden"):
        return state, registry
    effect = StateEffect(
        effect_type="remove_condition", target=player_id, value="hidden"
    )
    return apply_state_effects(state, registry, (effect,))


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
