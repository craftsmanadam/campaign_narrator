"""Campaign encounter-loop orchestrator."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace

from campaignnarrator.agents.narrator_agent import NarratorAgent
from campaignnarrator.agents.rules_agent import RulesAgent
from campaignnarrator.domain.models import (
    ActorState,
    EncounterPhase,
    EncounterState,
    Narration,
    NarrationFrame,
    OrchestrationDecision,
    PlayerInput,
    RollRequest,
    RollVisibility,
    RulesAdjudication,
    RulesAdjudicationRequest,
    StateEffect,
)
from campaignnarrator.repositories.memory_repository import MemoryRepository
from campaignnarrator.repositories.state_repository import StateRepository
from campaignnarrator.tools.state_updates import apply_state_effects

_ALLOWED_SOCIAL_NEXT_STEPS = {
    "npc_dialogue",
    "narrate_scene",
    "adjudicate_social_check",
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


class CampaignOrchestrator:
    """Coordinate player input, rules adjudication, state, and narration."""

    def __init__(  # noqa: PLR0913
        self,
        *,
        state_repository: StateRepository,
        rules_agent: RulesAgent,
        narrator_agent: NarratorAgent,
        roll_dice: Callable[[str], int],
        decision_adapter: object | None = None,
        memory_repository: MemoryRepository | None = None,
    ) -> None:
        self._state_repository = state_repository
        self._rules_agent = rules_agent
        self._narrator_agent = narrator_agent
        self._roll_dice = roll_dice
        self._decision_adapter = decision_adapter or getattr(
            rules_agent,
            "_adapter",
            None,
        )
        self._memory_repository = memory_repository

    def run(self, player_input: str) -> Narration:
        """Temporary compatibility wrapper for the legacy CLI entry point."""

        result = self.run_encounter(
            encounter_id="goblin-camp",
            player_inputs=(player_input,),
        )
        return Narration(text=result.output_text, audience="player")

    def run_encounter(
        self,
        *,
        encounter_id: str,
        player_inputs: Iterable[str],
    ) -> EncounterRunResult:
        """Run player inputs through the encounter loop."""

        state = self._state_repository.load_encounter(encounter_id)
        output: list[str] = []

        if state.phase is EncounterPhase.SCENE_OPENING:
            opening = self._narrate(_frame(state, "scene_opening"))
            output.append(opening.text)
            state = replace(state, phase=EncounterPhase.SOCIAL)

        for raw_input in player_inputs:
            player_input = PlayerInput(raw_text=raw_input)
            normalized = player_input.normalized
            if not normalized:
                continue
            if normalized == "exit":
                break

            if normalized == "status":
                narration = self._narrate(_status_frame(state))
                output.append(narration.text)
                continue

            if normalized == "what happened":
                narration = self._narrate(_recap_frame(state))
                output.append(narration.text)
                continue

            if normalized == "look around":
                narration = self._narrate(_look_frame(state))
                output.append(narration.text)
                continue

            if state.phase is EncounterPhase.COMBAT:
                if _is_combat_attack(normalized):
                    state, narration = self._handle_combat_attack(state, player_input)
                    output.append(narration.text)
                    continue
                raise ValueError("unsupported combat input")  # noqa: TRY003

            state, narration = self._handle_non_combat_action(state, player_input)
            output.append(narration.text)

        return EncounterRunResult(
            encounter_id=encounter_id,
            output_text="\n".join(output),
            completed=state.phase is EncounterPhase.ENCOUNTER_COMPLETE,
        )

    def current_state(self, encounter_id: str) -> EncounterState:
        """Return the current persisted encounter state."""

        return self._state_repository.load_encounter(encounter_id)

    def _handle_non_combat_action(
        self,
        state: EncounterState,
        player_input: PlayerInput,
    ) -> tuple[EncounterState, Narration]:
        payload = self._generate_orchestration_decision(state, player_input)
        decision = _parse_decision(payload)
        if decision.next_step not in _ALLOWED_SOCIAL_NEXT_STEPS:
            raise ValueError(  # noqa: TRY003
                f"invalid orchestration next_step: {decision.next_step}"
            )

        if decision.next_step == "adjudicate_social_check":
            return self._handle_social_check(state, player_input, decision)

        if decision.next_step in {"roll_initiative", "enter_combat"}:
            return self._enter_combat(state)

        if decision.next_step == "complete_encounter":
            return self._complete_encounter(state, payload, decision, player_input)

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

    def _handle_social_check(
        self,
        state: EncounterState,
        player_input: PlayerInput,
        decision: OrchestrationDecision,
    ) -> tuple[EncounterState, Narration]:
        request = RulesAdjudicationRequest(
            actor_id=state.player_actor_id,
            intent=player_input.raw_text,
            phase=state.phase,
            allowed_outcomes=("success", "failure", "complication", "peaceful"),
            rules_context=_non_empty_tuple((decision.recommended_check,)),
        )
        adjudication = self._rules_agent.adjudicate(request)
        updated_state, roll_events = self._apply_adjudication(state, adjudication)
        self._state_repository.save_encounter(updated_state)
        narration = self._narrate(
            _frame(
                updated_state,
                "social_resolution",
                resolved_outcomes=(*roll_events, adjudication.summary),
            )
        )
        return updated_state, narration

    def _enter_combat(self, state: EncounterState) -> tuple[EncounterState, Narration]:
        talia_roll = self._roll_dice("1d20+2")
        goblin_roll = self._roll_dice("1d20+2")
        initiative = (
            ("pc:talia", "Talia", talia_roll),
            ("npc:goblin-scout", "Goblin Scout", goblin_roll),
        )
        ordered = tuple(
            actor_id
            for actor_id, _name, _roll in sorted(
                initiative,
                key=lambda entry: entry[2],
                reverse=True,
            )
        )
        event = f"Initiative: Talia {talia_roll}, Goblin Scout {goblin_roll}."
        updated_state = replace(
            state,
            phase=EncounterPhase.COMBAT,
            initiative_order=ordered,
            outcome="combat",
            public_events=(*state.public_events, event),
        )
        self._state_repository.save_encounter(updated_state)
        narration = self._narrate(
            _frame(updated_state, "combat_start", resolved_outcomes=(event,))
        )
        return updated_state, narration

    def _complete_encounter(
        self,
        state: EncounterState,
        payload: Mapping[str, object],
        decision: OrchestrationDecision,
        player_input: PlayerInput,
    ) -> tuple[EncounterState, Narration]:
        outcome = _completion_outcome(payload, decision, player_input)
        updated_state = apply_state_effects(
            replace(state, phase=EncounterPhase.ENCOUNTER_COMPLETE),
            (
                StateEffect(
                    "set_encounter_outcome",
                    f"encounter:{state.encounter_id}",
                    outcome,
                ),
            ),
        )
        self._state_repository.save_encounter(updated_state)
        narration = self._narrate(
            _frame(
                updated_state,
                "complete_encounter",
                resolved_outcomes=(outcome,),
            )
        )
        return updated_state, narration

    def _handle_combat_attack(
        self,
        state: EncounterState,
        player_input: PlayerInput,
    ) -> tuple[EncounterState, Narration]:
        request = RulesAdjudicationRequest(
            actor_id=state.player_actor_id,
            intent=player_input.raw_text,
            phase=EncounterPhase.COMBAT,
            allowed_outcomes=("hit", "miss", "damage", "defeated"),
        )
        adjudication = self._rules_agent.adjudicate(request)
        updated_state, roll_events = self._apply_adjudication(state, adjudication)
        self._state_repository.save_encounter(updated_state)
        narration = self._narrate(
            _frame(
                updated_state,
                "combat_turn_result",
                resolved_outcomes=(*roll_events, adjudication.summary),
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
                "append_public_event",
                f"encounter:{state.encounter_id}",
                event,
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
    ) -> Mapping[str, object]:
        if self._decision_adapter is None:
            raise ValueError("missing decision adapter")  # noqa: TRY003
        payload = self._decision_adapter.generate_structured_json(
            instructions=(
                "Choose the next encounter orchestration step. Return only JSON. "
                "Allowed next_step values are npc_dialogue, narrate_scene, "
                "adjudicate_social_check, roll_initiative, enter_combat, and "
                "complete_encounter. Do not resolve rules yourself."
            ),
            input_text=json.dumps(
                {
                    "phase": state.phase.value,
                    "setting": state.setting,
                    "public_actor_summaries": _public_actor_summaries(state),
                    "hidden_facts": dict(state.hidden_facts),
                    "recent_public_events": state.public_events[-5:],
                    "latest_input": player_input.raw_text,
                    "allowed_next_steps": sorted(_ALLOWED_SOCIAL_NEXT_STEPS),
                },
                indent=2,
                sort_keys=True,
            ),
        )
        if not isinstance(payload, Mapping):
            raise TypeError("invalid orchestration decision payload")  # noqa: TRY003
        return payload

    def _narrate(self, frame: NarrationFrame) -> Narration:
        return self._narrator_agent.narrate(frame)


def _parse_decision(payload: Mapping[str, object]) -> OrchestrationDecision:
    return OrchestrationDecision(
        next_step=_require_string(payload, "next_step"),
        next_actor=_optional_string(payload, "next_actor"),
        requires_rules_resolution=_require_bool(
            payload,
            "requires_rules_resolution",
        ),
        recommended_check=_optional_string(payload, "recommended_check"),
        phase_transition=_optional_string(payload, "phase_transition"),
        player_prompt=_optional_string(payload, "player_prompt"),
        reason_summary=_require_string(payload, "reason_summary"),
    )


def _completion_outcome(
    payload: Mapping[str, object],
    decision: OrchestrationDecision,
    player_input: PlayerInput,
) -> str:
    outcome = payload.get("outcome")
    if isinstance(outcome, str) and outcome.strip():
        return outcome
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
    )


def _public_actor_summaries(state: EncounterState) -> tuple[str, ...]:
    return tuple(_actor_summary(actor) for actor in state.actors.values())


def _visible_npc_summaries(state: EncounterState) -> tuple[str, ...]:
    return tuple(
        _actor_summary(actor)
        for actor in state.actors.values()
        if actor.kind == "npc" and actor.is_visible
    )


def _actor_summary(actor: ActorState) -> str:
    inventory = ", ".join(actor.inventory) if actor.inventory else "none"
    return (
        f"{actor.name} HP {actor.hp_current}/{actor.hp_max}, "
        f"AC {actor.armor_class}, inventory: {inventory}"
    )


def _public_roll_event(roll_request: RollRequest, total: int) -> str:
    purpose = roll_request.purpose or roll_request.expression
    return f"Roll: {purpose} = {total}."


def _is_combat_attack(normalized_input: str) -> bool:
    attack_terms = ("attack", "swing", "strike")
    return any(term in normalized_input for term in attack_terms)


def _non_empty_tuple(values: tuple[str | None, ...]) -> tuple[str, ...]:
    return tuple(value for value in values if value)


def _require_string(payload: Mapping[str, object], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str):
        raise TypeError(f"invalid orchestration {field}")  # noqa: TRY003
    return value


def _optional_string(payload: Mapping[str, object], field: str) -> str | None:
    value = payload.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"invalid orchestration {field}")  # noqa: TRY003
    return value


def _require_bool(payload: Mapping[str, object], field: str) -> bool:
    value = payload.get(field)
    if not isinstance(value, bool):
        raise ValueError(f"invalid orchestration {field}")  # noqa: TRY003, TRY004
    return value
