"""Encounter-loop orchestrator."""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace

from campaignnarrator.agents.narrator_agent import NarratorAgent
from campaignnarrator.agents.player_intent_agent import PlayerIntentAgent
from campaignnarrator.agents.rules_agent import RulesAgent
from campaignnarrator.domain.models import (
    ActorState,
    ActorType,
    CombatResult,
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
)
from campaignnarrator.orchestrators.actor_summaries import (
    actor_modifiers,
    actor_narrative_summary,
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
                raise ValueError(  # noqa: TRY003
                    "EncounterOrchestrator requires adapter= or "
                    "_player_intent_agent= to be set"
                )
            self._player_intent_agent = PlayerIntentAgent(adapter=adapter)

    def run_encounter(self, *, encounter_id: str) -> EncounterRunResult:
        """Run the encounter loop until an end condition is reached."""

        game_state = self._memory_repository.load_game_state()
        if game_state.encounter is None:
            raise ValueError("no active encounter")  # noqa: TRY003
        player = game_state.player
        output: list[str] = []
        state = game_state.encounter

        if state.phase is EncounterPhase.SCENE_OPENING:
            opening, state = self._narrate(_frame(state, "scene_opening"), state)
            state = replace(
                state, phase=EncounterPhase.SOCIAL, scene_tone=opening.scene_tone
            )
            self._io.display(opening.text)
            output.append(opening.text)
            self._memory_repository.update_game_state(
                GameState(player=player, encounter=state)
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
                _frame(state, "session_resume", resolved_outcomes=state.public_events),
                prior_narrative_context=prior_context,
            )
            resume_narration, state = self._narrate(resume_frame, state)
            self._io.display(resume_narration.text)
            output.append(resume_narration.text)

        if state.phase is EncounterPhase.ENCOUNTER_COMPLETE:
            return EncounterRunResult(
                encounter_id=state.encounter_id,
                output_text="\n".join(output),
                completed=True,
            )

        state = self._run_loop(state, player, output)
        return EncounterRunResult(
            encounter_id=state.encounter_id,
            output_text="\n".join(output),
            completed=state.phase is EncounterPhase.ENCOUNTER_COMPLETE,
        )

    def _run_loop(
        self, state: EncounterState, player: ActorState, output: list[str]
    ) -> EncounterState:
        """Main interaction loop — runs until combat, quit, or encounter complete."""
        while True:
            if state.phase is EncounterPhase.COMBAT:
                self._run_combat(state, player)
                break

            if state.phase is EncounterPhase.ENCOUNTER_COMPLETE:
                break

            raw_input = self._io.prompt("> ")
            player_input = PlayerInput(raw_text=raw_input)
            if not player_input.normalized:
                continue

            intent = self._classify_intent(state, player_input)

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
                    self._memory_repository.update_game_state(
                        GameState(player=player, encounter=state)
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
                    narration, state = self._narrate(_status_frame(state), state)
                    self._io.display(narration.text)
                    output.append(narration.text)
                    continue
                case IntentCategory.RECAP:
                    narration, state = self._narrate(_recap_frame(state), state)
                    self._io.display(narration.text)
                    output.append(narration.text)
                    continue
                case IntentCategory.LOOK_AROUND:
                    narration, state = self._narrate(_look_frame(state), state)
                    self._io.display(narration.text)
                    output.append(narration.text)
                    continue

            self._io.display("\n...\n")
            state = self._apply_action(state, player_input, intent, player, output)
        return state

    def _classify_intent(
        self,
        state: EncounterState,
        player_input: PlayerInput,
    ) -> PlayerIntent:
        result = self._player_intent_agent.classify(
            player_input.raw_text,
            phase=state.phase,
            setting=state.setting,
            recent_events=state.public_events[-5:],
            actor_summaries=_public_actor_summaries(state),
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
        output: list[str],
    ) -> EncounterState:
        """Apply a non-combat player action; display narration; return updated state."""
        try:
            state, narration = self._handle_non_combat_action(
                state, player_input, intent, player
            )
        except ValueError:
            raise
        except Exception as exc:
            _log.exception("Action processing failed")
            msg = f"\n[Narrator encountered an error ({exc}). Please try again.]\n"
            self._io.display(msg)
            output.append(msg)
            return state

        self._io.display(narration.text)
        output.append(narration.text)
        self._memory_repository.update_game_state(
            GameState(player=player, encounter=state)
        )
        self._memory_repository.update_exchange(player_input.raw_text, narration.text)
        return state

    def _run_combat(self, state: EncounterState, player: ActorState) -> CombatResult:
        """Delegate the combat turn loop to CombatOrchestrator."""
        orchestrator = CombatOrchestrator(
            rules_agent=self._rules_agent,
            narrator_agent=self._narrator_agent,
            io=self._io,
            adapter=self._adapter,
            _intent_agent=self._combat_intent_agent,
            memory_repository=self._memory_repository,
        )
        result = orchestrator.run(state)
        self._memory_repository.update_game_state(
            GameState(player=player, encounter=result.final_state)
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
    ) -> tuple[EncounterState, Narration]:
        compendium_context = player.references
        match intent.category:
            case IntentCategory.HOSTILE_ACTION:
                return self._enter_combat(_clear_player_hidden(state), player)
            case IntentCategory.SKILL_CHECK:
                return self._handle_action(
                    state, player_input, intent, compendium_context, player
                )
            case IntentCategory.NPC_DIALOGUE:
                state = _clear_player_hidden(state)
                narration, state = self._narrate(
                    replace(
                        _frame(state, "npc_dialogue"),
                        player_action=player_input.raw_text,
                    ),
                    state,
                )
                return state, narration
            case IntentCategory.SCENE_OBSERVATION:
                narration, state = self._narrate(
                    replace(
                        _frame(state, "scene_response"),
                        player_action=player_input.raw_text,
                    ),
                    state,
                )
                return state, narration
            case _:
                _log.warning(
                    "Unhandled intent category in narrative path: %s", intent.category
                )
                narration, state = self._narrate(
                    replace(
                        _frame(state, "scene_response"),
                        player_action=player_input.raw_text,
                    ),
                    state,
                )
                return state, narration

    def _handle_action(
        self,
        state: EncounterState,
        player_input: PlayerInput,
        intent: PlayerIntent,
        compendium_context: tuple[str, ...],
        player: ActorState,
    ) -> tuple[EncounterState, Narration]:
        request = RulesAdjudicationRequest(
            actor_id=state.player_actor_id,
            encounter_id=state.encounter_id,
            intent=player_input.raw_text,
            phase=state.phase,
            allowed_outcomes=("success", "failure", "complication", "peaceful"),
            check_hints=_non_empty_tuple((intent.check_hint,)),
            compendium_context=compendium_context,
            actor_modifiers=actor_modifiers(player),
        )
        self._io.display("\nConsidering the rules...\n")
        adjudication = self._rules_agent.adjudicate(request)
        updated_state, roll_events, resolved_action_type = self._apply_adjudication(
            state, adjudication, player
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
        narration, updated_state = self._narrate(
            replace(
                _frame(
                    updated_state,
                    "social_resolution",
                    resolved_outcomes=resolved_outcomes,
                    compendium_context=compendium_context,
                ),
                player_action=player_input.raw_text,
            ),
            updated_state,
        )
        return updated_state, narration

    def _enter_combat(
        self, state: EncounterState, player: ActorState
    ) -> tuple[EncounterState, Narration]:
        rolls = [
            (actor_id, actor.name, roll(f"1d20+{actor.initiative_bonus}"))
            for actor_id, actor in sorted(state.actors.items())
        ]
        sorted_rolls = sorted(rolls, key=lambda entry: entry[2], reverse=True)
        ordered = tuple(
            InitiativeTurn(actor_id=actor_id, initiative_roll=roll)
            for actor_id, _name, roll in sorted_rolls
        )
        event = (
            "Initiative: "
            + ", ".join(f"{name} {roll}" for _, name, roll in sorted_rolls)
            + "."
        )
        updated_state = replace(
            state,
            phase=EncounterPhase.COMBAT,
            combat_turns=ordered,
            outcome="combat",
            public_events=(*state.public_events, event),
        )
        self._append_event(
            {
                "type": "encounter_completed",
                "encounter_id": updated_state.encounter_id,
                "outcome": "combat",
            }
        )
        narration, updated_state = self._narrate(
            _frame(updated_state, "combat_start", resolved_outcomes=(event,)),
            updated_state,
        )
        return updated_state, narration

    def _apply_adjudication(
        self,
        state: EncounterState,
        adjudication: RulesAdjudication,
        player: ActorState,
    ) -> tuple[EncounterState, tuple[str, ...], str | None]:
        # returns (updated_state, roll_events, resolved_action_type_or_none)
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

        return (
            apply_state_effects(state, (*roll_effects, *effects_to_apply)),
            tuple(roll_events),
            resolved_action_type,
        )

    def _retrieve_prior_context(self, query: str) -> str:
        """Query memory for prior session context including recent exchanges."""
        parts: list[str] = self._memory_repository.retrieve_relevant(query, limit=3)
        exchange = self._memory_repository.get_exchange_buffer()
        if exchange:
            parts.append("Recent exchanges:\n" + "\n".join(exchange))
        return "\n\n".join(parts)

    def _narrate(
        self, frame: NarrationFrame, state: EncounterState
    ) -> tuple[Narration, EncounterState]:
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
        return narration, state

    def _append_event(self, event: dict[str, object]) -> None:
        self._memory_repository.append_event(event)


def _status_frame(state: EncounterState) -> NarrationFrame:
    return _frame(
        state,
        "status_response",
        resolved_outcomes=("; ".join(_public_actor_summaries(state)),),
        allowed_disclosures=("player HP", "inventory", "visible actors"),
    )


def _recap_frame(state: EncounterState) -> NarrationFrame:
    outcome = () if state.outcome is None else (f"Outcome: {state.outcome}",)
    return _frame(
        state,
        "recap_response",
        resolved_outcomes=(*state.public_events, *outcome),
        allowed_disclosures=("public events", "encounter outcome"),
    )


def _look_frame(state: EncounterState) -> NarrationFrame:
    return _frame(
        state,
        "status_response",
        resolved_outcomes=(state.setting,),
        allowed_disclosures=("setting", "visible actors"),
    )


def _frame(
    state: EncounterState,
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
        public_actor_summaries=_public_actor_summaries(state),
        npc_presences=tuple(
            p for p in state.npc_presences if p.status is not NpcPresenceStatus.DEPARTED
        ),
        recent_public_events=state.public_events[-5:],
        resolved_outcomes=resolved_outcomes,
        allowed_disclosures=allowed_disclosures,
        compendium_context=compendium_context,
        tone_guidance=state.scene_tone,
    )


def _public_actor_summaries(state: EncounterState) -> tuple[str, ...]:
    if not state.npc_presences:
        # No presence list — old encounter or unit-test fixture; include everyone.
        return tuple(actor_narrative_summary(actor) for actor in state.actors.values())
    present_ids = {
        p.actor_id
        for p in state.npc_presences
        if p.status is not NpcPresenceStatus.DEPARTED
    }
    return tuple(
        actor_narrative_summary(actor)
        for actor in state.actors.values()
        if actor.actor_type == ActorType.PC or actor.actor_id in present_ids
    )


def _non_empty_tuple(values: tuple[str | None, ...]) -> tuple[str, ...]:
    return tuple(value for value in values if value)


def _clear_player_hidden(state: EncounterState) -> EncounterState:
    """Clear the hidden condition from the player actor when they reveal themselves."""
    player_id = state.player_actor_id
    if not state.actors[player_id].has_condition("hidden"):
        return state
    effect = StateEffect(
        effect_type="remove_condition", target=player_id, value="hidden"
    )
    return apply_state_effects(state, (effect,))
