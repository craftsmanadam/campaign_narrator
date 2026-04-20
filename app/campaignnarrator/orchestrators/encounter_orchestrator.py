"""Encounter-loop orchestrator."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, replace

from pydantic_ai import Agent

from campaignnarrator.agents.narrator_agent import NarratorAgent
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
    Narration,
    NarrationFrame,
    OrchestrationDecision,
    PlayerInput,
    PlayerIO,
    RollRequest,
    RollVisibility,
    RulesAdjudication,
    RulesAdjudicationRequest,
    StateEffect,
)
from campaignnarrator.orchestrators.combat_orchestrator import CombatOrchestrator
from campaignnarrator.repositories.memory_repository import MemoryRepository
from campaignnarrator.repositories.state_repository import StateRepository
from campaignnarrator.tools.state_updates import apply_state_effects

_ALLOWED_SOCIAL_NEXT_STEPS = {
    "npc_dialogue",
    "narrate_scene",
    "adjudicate_action",
    "roll_initiative",
    "enter_combat",
    "complete_encounter",
}


@dataclass(frozen=True, slots=True)
class EncounterRunResult:
    """Result of running one batch of player inputs through an encounter."""

    encounter_id: str
    output_text: str
    completed: bool


@dataclass(frozen=True, slots=True)
class OrchestratorRepositories:
    """Repository dependencies for EncounterOrchestrator."""

    state: StateRepository
    memory: MemoryRepository | None = None


@dataclass(frozen=True, slots=True)
class OrchestratorAgents:
    """Agent dependencies for EncounterOrchestrator."""

    rules: RulesAgent
    narrator: NarratorAgent


@dataclass(frozen=True, slots=True)
class OrchestratorTools:
    """Tool dependencies for EncounterOrchestrator."""

    roll_dice: Callable[[str], int]


class EncounterOrchestrator:
    """Coordinate player input, rules adjudication, state, and narration."""

    def __init__(
        self,
        *,
        repositories: OrchestratorRepositories,
        agents: OrchestratorAgents,
        tools: OrchestratorTools,
        io: PlayerIO,
        adapter: object | None = None,
        _decision_agent: object | None = None,
        _combat_intent_agent: object | None = None,
    ) -> None:
        self._state_repository = repositories.state
        self._rules_agent = agents.rules
        self._narrator_agent = agents.narrator
        self._roll_dice = tools.roll_dice
        self._io = io
        self._memory_repository = repositories.memory
        self._adapter = adapter
        self._combat_intent_agent = _combat_intent_agent
        if _decision_agent is not None:
            self._decision_agent = _decision_agent
        else:
            if adapter is None:
                raise ValueError(  # noqa: TRY003
                    "EncounterOrchestrator requires adapter= or "
                    "_decision_agent= to be set"
                )
            self._decision_agent = Agent(
                adapter.model,
                output_type=OrchestrationDecision,
                instructions=(
                    "Choose the next encounter orchestration step. "
                    "Allowed next_step values are npc_dialogue, narrate_scene, "
                    "adjudicate_action, roll_initiative, enter_combat, and "
                    "complete_encounter. Do not resolve rules yourself."
                ),
            )

    def run_encounter(self, *, encounter_id: str) -> EncounterRunResult:
        """Run the encounter loop until an end condition is reached."""

        game_state = self._state_repository.load()
        if game_state.encounter is None:
            raise ValueError("no active encounter")  # noqa: TRY003
        player = game_state.player
        output: list[str] = []

        try:
            state, scene_texts = self._open_scene(game_state.encounter)
        except Exception as exc:
            msg = f"\n[Scene narration unavailable ({exc}). Continuing...]\n"
            self._io.display(msg)
            output.append(msg)
            state = replace(game_state.encounter, phase=EncounterPhase.SOCIAL)
            scene_texts = []

        for text in scene_texts:
            self._io.display(text)
            output.append(text)

        # If loaded from a saved already-complete state, return immediately.
        if state.phase is EncounterPhase.ENCOUNTER_COMPLETE:
            return EncounterRunResult(
                encounter_id=state.encounter_id,
                output_text="\n".join(output),
                completed=True,
            )

        while True:
            if state.phase is EncounterPhase.COMBAT:
                # saves state internally; result not used here
                self._run_combat(state, player)
                break

            raw_input = self._io.prompt("> ")
            player_input = PlayerInput(raw_text=raw_input)
            normalized = player_input.normalized
            if not normalized:
                continue

            directive = self._handle_utility_command(normalized, state, output, player)
            if directive == "break":
                break
            if directive == "continue":
                continue

            # After utility commands, non-utility input is a no-op when complete.
            if state.phase is EncounterPhase.ENCOUNTER_COMPLETE:
                break

            try:
                state, narration = self._handle_non_combat_action(
                    state, player_input, player
                )
            except ValueError:
                raise
            except Exception as exc:
                msg = f"\n[Narrator encountered an error ({exc}). Please try again.]\n"
                self._io.display(msg)
                output.append(msg)
                continue

            self._io.display(narration.text)
            output.append(narration.text)
            if state.phase is EncounterPhase.ENCOUNTER_COMPLETE:
                continue

        return EncounterRunResult(
            encounter_id=state.encounter_id,
            output_text="\n".join(output),
            completed=state.phase is EncounterPhase.ENCOUNTER_COMPLETE,
        )

    def _open_scene(self, state: EncounterState) -> tuple[EncounterState, list[str]]:
        """Narrate scene opening if needed; return updated state and initial output."""
        output: list[str] = []
        if state.phase is EncounterPhase.SCENE_OPENING:
            opening = self._narrate(_frame(state, "scene_opening"))
            output.append(opening.text)
            state = replace(
                state,
                phase=EncounterPhase.SOCIAL,
                scene_tone=opening.scene_tone,
            )
        return state, output

    def _run_combat(self, state: EncounterState, player: ActorState) -> CombatResult:
        """Delegate the combat turn loop to CombatOrchestrator."""
        orchestrator = CombatOrchestrator(
            rules_agent=self._rules_agent,
            narrator_agent=self._narrator_agent,
            io=self._io,
            roll_dice=self._roll_dice,
            adapter=self._adapter,
            _intent_agent=self._combat_intent_agent,
        )
        result = orchestrator.run(state)
        self._state_repository.save(
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

    def _handle_utility_command(
        self,
        normalized: str,
        state: EncounterState,
        output: list[str],
        player: ActorState,
    ) -> str | None:
        """Handle built-in player commands. Returns 'break', 'continue', or None."""

        if normalized in ("exit", "save and quit"):
            if state.phase is not EncounterPhase.ENCOUNTER_COMPLETE:
                self._state_repository.save(GameState(player=player, encounter=state))
                self._append_event(
                    {
                        "type": "encounter_saved",
                        "encounter_id": state.encounter_id,
                        "phase": state.phase.value,
                        "outcome": state.outcome,
                    }
                )
                msg = "Game saved. You can resume this encounter later."
                self._io.display(msg)
                output.append(msg)
            return "break"
        if normalized == "status":
            text = self._narrate(_status_frame(state)).text
            self._io.display(text)
            output.append(text)
            return "continue"
        if normalized == "what happened":
            text = self._narrate(_recap_frame(state)).text
            self._io.display(text)
            output.append(text)
            return "continue"
        if normalized == "look around":
            text = self._narrate(_look_frame(state)).text
            self._io.display(text)
            output.append(text)
            return "continue"
        return None

    def current_state(self) -> EncounterState | None:
        """Return the current persisted encounter state."""

        return self._state_repository.load().encounter

    def _handle_non_combat_action(
        self,
        state: EncounterState,
        player_input: PlayerInput,
        player: ActorState,
    ) -> tuple[EncounterState, Narration]:
        compendium_context = player.references
        decision = self._generate_orchestration_decision(state, player_input)
        if decision.next_step not in _ALLOWED_SOCIAL_NEXT_STEPS:
            raise ValueError(  # noqa: TRY003
                f"invalid orchestration next_step: {decision.next_step}"
            )

        if decision.next_step == "adjudicate_action":
            return self._handle_action(
                state, player_input, decision, compendium_context, player
            )

        if decision.next_step in {"roll_initiative", "enter_combat"}:
            return self._enter_combat(state, player)

        if decision.next_step == "complete_encounter":
            return self._complete_encounter(state, decision, player_input, player)

        purpose = (
            "npc_dialogue" if decision.next_step == "npc_dialogue" else "scene_response"
        )
        narration = self._narrate(
            _frame(
                state,
                purpose,
                resolved_outcomes=(decision.reason_summary,),
            )
        )
        return state, narration

    def _handle_action(
        self,
        state: EncounterState,
        player_input: PlayerInput,
        decision: OrchestrationDecision,
        compendium_context: tuple[str, ...],
        player: ActorState,
    ) -> tuple[EncounterState, Narration]:
        request = RulesAdjudicationRequest(
            actor_id=state.player_actor_id,
            intent=player_input.raw_text,
            phase=state.phase,
            allowed_outcomes=("success", "failure", "complication", "peaceful"),
            check_hints=_non_empty_tuple((decision.recommended_check,)),
            compendium_context=compendium_context,
        )
        adjudication = self._rules_agent.adjudicate(request)
        updated_state, roll_events = self._apply_adjudication(state, adjudication)
        self._state_repository.save(GameState(player=player, encounter=updated_state))
        if updated_state.outcome is not None:
            self._append_event(
                {
                    "type": "encounter_completed",
                    "encounter_id": updated_state.encounter_id,
                    "outcome": updated_state.outcome,
                }
            )
        narration = self._narrate(
            _frame(
                updated_state,
                "social_resolution",
                resolved_outcomes=(*roll_events, adjudication.summary),
                compendium_context=compendium_context,
            )
        )
        return updated_state, narration

    def _enter_combat(
        self, state: EncounterState, player: ActorState
    ) -> tuple[EncounterState, Narration]:
        rolls = [
            (actor_id, actor.name, self._roll_dice(f"1d20+{actor.initiative_bonus}"))
            for actor_id, actor in sorted(state.actors.items())
        ]
        sorted_rolls = sorted(rolls, key=lambda entry: entry[2], reverse=True)
        ordered = tuple(
            InitiativeTurn(actor_id=actor_id, initiative_roll=roll)
            for actor_id, _name, roll in sorted_rolls
        )
        event = "Initiative: " + ", ".join(
            f"{name} {roll}" for _, name, roll in sorted_rolls
        ) + "."
        updated_state = replace(
            state,
            phase=EncounterPhase.COMBAT,
            combat_turns=ordered,
            outcome="combat",
            public_events=(*state.public_events, event),
        )
        self._state_repository.save(GameState(player=player, encounter=updated_state))
        self._append_event(
            {
                "type": "encounter_completed",
                "encounter_id": updated_state.encounter_id,
                "outcome": "combat",
            }
        )
        narration = self._narrate(
            _frame(updated_state, "combat_start", resolved_outcomes=(event,))
        )
        return updated_state, narration

    def _complete_encounter(
        self,
        state: EncounterState,
        decision: OrchestrationDecision,
        player_input: PlayerInput,
        player: ActorState,
    ) -> tuple[EncounterState, Narration]:
        outcome = _completion_outcome(decision, player_input)
        updated_state = apply_state_effects(
            replace(state, phase=EncounterPhase.ENCOUNTER_COMPLETE),
            (
                StateEffect(
                    effect_type="set_encounter_outcome",
                    target=f"encounter:{state.encounter_id}",
                    value=outcome,
                ),
            ),
        )
        self._state_repository.save(GameState(player=player, encounter=updated_state))
        self._append_event(
            {
                "type": "encounter_completed",
                "encounter_id": updated_state.encounter_id,
                "outcome": outcome,
            }
        )
        narration = self._narrate(
            _frame(
                updated_state,
                "complete_encounter",
                resolved_outcomes=(outcome,),
            )
        )
        return updated_state, narration

    def _apply_adjudication(
        self,
        state: EncounterState,
        adjudication: RulesAdjudication,
    ) -> tuple[EncounterState, tuple[str, ...]]:
        roll_events = tuple(
            _public_roll_event(roll_request, self._roll_dice(roll_request.expression))
            for roll_request in adjudication.roll_requests
            if roll_request.visibility is RollVisibility.PUBLIC
        )
        roll_effects = tuple(
            StateEffect(
                effect_type="append_public_event",
                target=f"encounter:{state.encounter_id}",
                value=event,
            )
            for event in roll_events
        )
        return (
            apply_state_effects(state, (*roll_effects, *adjudication.state_effects)),
            roll_events,
        )

    def _generate_orchestration_decision(
        self,
        state: EncounterState,
        player_input: PlayerInput,
    ) -> OrchestrationDecision:
        return self._decision_agent.run_sync(
            json.dumps(
                {
                    "phase": state.phase.value,
                    "setting": state.setting,
                    "public_actor_summaries": _public_actor_summaries(state),
                    "hidden_facts": dict(state.hidden_facts),
                    "recent_public_events": list(state.public_events[-5:]),
                    "latest_input": player_input.raw_text,
                    "allowed_next_steps": sorted(_ALLOWED_SOCIAL_NEXT_STEPS),
                },
                indent=2,
                sort_keys=True,
            )
        ).output

    def _narrate(self, frame: NarrationFrame) -> Narration:
        return self._narrator_agent.narrate(frame)

    def _append_event(self, event: dict[str, object]) -> None:
        if self._memory_repository is not None:
            self._memory_repository.append_event(event)


def _completion_outcome(
    decision: OrchestrationDecision,
    player_input: PlayerInput,
) -> str:
    if (
        decision.phase_transition is not None
        and decision.phase_transition != EncounterPhase.ENCOUNTER_COMPLETE.value
    ):
        return decision.phase_transition
    peaceful_signals = (
        decision.reason_summary,
        decision.player_prompt or "",
        player_input.raw_text,
    )
    if any("peace" in signal.lower() for signal in peaceful_signals):
        return "peaceful"
    return "complete"


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
        resolved_outcomes=(state.setting, *_visible_npc_summaries(state)),
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
        setting=state.setting,
        public_actor_summaries=_public_actor_summaries(state),
        visible_npc_summaries=_visible_npc_summaries(state),
        recent_public_events=state.public_events[-5:],
        resolved_outcomes=resolved_outcomes,
        allowed_disclosures=allowed_disclosures,
        compendium_context=compendium_context,
        tone_guidance=state.scene_tone,
    )


def _public_actor_summaries(state: EncounterState) -> tuple[str, ...]:
    return tuple(_actor_summary(actor) for actor in state.actors.values())


def _visible_npc_summaries(state: EncounterState) -> tuple[str, ...]:
    return tuple(
        _actor_summary(actor)
        for actor in state.actors.values()
        if actor.actor_type == ActorType.NPC and actor.is_visible
    )


def _actor_summary(actor: ActorState) -> str:
    return f"{actor.name} HP {actor.hp_current}/{actor.hp_max}, AC {actor.armor_class}"


def _public_roll_event(roll_request: RollRequest, total: int) -> str:
    purpose = roll_request.purpose or roll_request.expression
    return f"Roll: {purpose} = {total}."


def _non_empty_tuple(values: tuple[str | None, ...]) -> tuple[str, ...]:
    return tuple(value for value in values if value)
