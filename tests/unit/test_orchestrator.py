"""Unit tests for the encounter-loop campaign orchestrator."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import replace

import pytest
from campaignnarrator.domain.models import (
    EncounterPhase,
    Narration,
    NarrationFrame,
    RollRequest,
    RollVisibility,
    RulesAdjudication,
    RulesAdjudicationRequest,
    StateEffect,
)
from campaignnarrator.orchestrators.encounter_orchestrator import (
    EncounterOrchestrator,
    EncounterRunResult,
)
from campaignnarrator.repositories.state_repository import StateRepository

_DAMAGED_GOBLIN_HP = 2


class FakeMemoryRepository:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def append_event(self, event: Mapping[str, object]) -> None:
        self.events.append(dict(event))


class FakeDecisionAdapter:
    def __init__(self, decisions: Iterable[object]) -> None:
        self.decisions = list(decisions)
        self.calls: list[tuple[str, dict[str, object]]] = []

    def generate_structured_json(
        self,
        *,
        instructions: str,
        input_text: str,
    ) -> object:
        self.calls.append((instructions, json.loads(input_text)))
        return self.decisions.pop(0)


class FakeRulesAgent:
    def __init__(self, adjudications: Iterable[RulesAdjudication] = ()) -> None:
        self.adjudications = list(adjudications)
        self.requests: list[RulesAdjudicationRequest] = []

    def adjudicate(self, request: RulesAdjudicationRequest) -> RulesAdjudication:
        self.requests.append(request)
        return self.adjudications.pop(0)


class FakeNarratorAgent:
    def __init__(self) -> None:
        self.frames: list[NarrationFrame] = []

    def narrate(self, frame: NarrationFrame) -> Narration:
        self.frames.append(frame)
        outcomes = " ".join(frame.resolved_outcomes)
        return Narration(
            text=f"{frame.purpose}: {outcomes}".strip(),
            audience="player",
        )


class FakeDice:
    def __init__(self, totals: Iterable[int]) -> None:
        self.totals = list(totals)
        self.expressions: list[str] = []

    def __call__(self, expression: str) -> int:
        self.expressions.append(expression)
        return self.totals.pop(0)


def _decision(next_step: str, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "next_step": next_step,
        "next_actor": None,
        "requires_rules_resolution": False,
        "recommended_check": None,
        "phase_transition": None,
        "player_prompt": None,
        "reason_summary": "test decision",
    }
    payload.update(overrides)
    return payload


def _orchestrator(
    *,
    state_repository: StateRepository | None = None,
    decision_adapter: FakeDecisionAdapter | None = None,
    rules_agent: FakeRulesAgent | None = None,
    narrator_agent: FakeNarratorAgent | None = None,
    roll_dice: FakeDice | None = None,
) -> EncounterOrchestrator:
    return EncounterOrchestrator(
        state_repository=state_repository or StateRepository.from_default_encounter(),
        rules_agent=rules_agent or FakeRulesAgent(),
        narrator_agent=narrator_agent or FakeNarratorAgent(),
        roll_dice=roll_dice or FakeDice(()),
        decision_adapter=decision_adapter or FakeDecisionAdapter(()),
    )


def _social_repository() -> StateRepository:
    repository = StateRepository.from_default_encounter()
    state = repository.load_encounter("goblin-camp")
    repository.save_encounter(replace(state, phase=EncounterPhase.SOCIAL))
    return repository


def _combat_repository() -> StateRepository:
    repository = StateRepository.from_default_encounter()
    state = repository.load_encounter("goblin-camp")
    repository.save_encounter(
        replace(
            state,
            phase=EncounterPhase.COMBAT,
            initiative_order=("pc:talia", "npc:goblin-scout"),
            outcome="combat",
        )
    )
    return repository


def test_run_encounter_returns_peaceful_output_status_and_recap() -> None:
    decision_adapter = FakeDecisionAdapter(
        (_decision("complete_encounter", outcome="peaceful"),)
    )
    rules_agent = FakeRulesAgent()
    narrator_agent = FakeNarratorAgent()
    orchestrator = _orchestrator(
        decision_adapter=decision_adapter,
        rules_agent=rules_agent,
        narrator_agent=narrator_agent,
    )

    result = orchestrator.run_encounter(
        encounter_id="goblin-camp",
        player_inputs=[
            "Hello there. I do not want trouble.",
            "status",
            "what happened",
            "exit",
        ],
    )

    assert result == EncounterRunResult(
        encounter_id="goblin-camp",
        output_text=result.output_text,
        completed=True,
    )
    assert "complete_encounter: peaceful" in result.output_text
    assert "status_response:" in result.output_text
    assert "recap_response:" in result.output_text
    assert orchestrator.current_state("goblin-camp").outcome == "peaceful"
    assert rules_agent.requests == []


def test_status_routes_to_status_frame_without_rules_adjudication() -> None:
    rules_agent = FakeRulesAgent()
    narrator_agent = FakeNarratorAgent()
    orchestrator = _orchestrator(
        state_repository=_social_repository(),
        rules_agent=rules_agent,
        narrator_agent=narrator_agent,
    )

    result = orchestrator.run_encounter(
        encounter_id="goblin-camp",
        player_inputs=["status", "exit"],
    )

    assert "status_response:" in result.output_text
    assert rules_agent.requests == []
    assert narrator_agent.frames[-1].purpose == "status_response"
    assert any(
        "Talia HP 12/12" in summary
        for summary in narrator_agent.frames[-1].public_actor_summaries
    )


def test_empty_input_is_ignored_and_look_around_routes_to_visible_scene() -> None:
    rules_agent = FakeRulesAgent()
    narrator_agent = FakeNarratorAgent()
    orchestrator = _orchestrator(
        state_repository=_social_repository(),
        rules_agent=rules_agent,
        narrator_agent=narrator_agent,
    )

    result = orchestrator.run_encounter(
        encounter_id="goblin-camp",
        player_inputs=["", "   ", "look around", "exit"],
    )

    assert "status_response:" in result.output_text
    assert rules_agent.requests == []
    assert narrator_agent.frames[-1].resolved_outcomes[0] == "A ruined roadside camp."
    assert narrator_agent.frames[-1].allowed_disclosures == (
        "setting",
        "visible actors",
    )


def test_friendly_social_input_can_complete_peacefully_through_decision() -> None:
    orchestrator = _orchestrator(
        state_repository=_social_repository(),
        decision_adapter=FakeDecisionAdapter(
            (_decision("complete_encounter", outcome="peaceful"),)
        ),
    )

    result = orchestrator.run_encounter(
        encounter_id="goblin-camp",
        player_inputs=["I lower my weapon and ask to pass peacefully."],
    )

    assert result.completed is True
    assert "peaceful" in result.output_text
    assert orchestrator.current_state("goblin-camp").outcome == "peaceful"


def test_social_check_uses_rules_agent_and_applies_effects() -> None:
    rules_agent = FakeRulesAgent(
        (
            RulesAdjudication(
                is_legal=True,
                action_type="social_check",
                summary="The goblins accept the offer.",
                roll_requests=(
                    RollRequest(
                        owner="player",
                        visibility=RollVisibility.PUBLIC,
                        expression="1d20+1",
                        purpose="calm goblins",
                    ),
                ),
                state_effects=(
                    StateEffect(
                        "set_encounter_outcome",
                        "encounter:goblin-camp",
                        "de-escalated",
                    ),
                ),
                reasoning_summary="The check succeeds.",
            ),
        )
    )
    roll_dice = FakeDice((16,))
    narrator_agent = FakeNarratorAgent()
    orchestrator = _orchestrator(
        state_repository=_social_repository(),
        decision_adapter=FakeDecisionAdapter(
            (
                _decision(
                    "adjudicate_social_check",
                    requires_rules_resolution=True,
                    recommended_check="Persuasion",
                ),
            )
        ),
        rules_agent=rules_agent,
        narrator_agent=narrator_agent,
        roll_dice=roll_dice,
    )

    result = orchestrator.run_encounter(
        encounter_id="goblin-camp",
        player_inputs=["I try to calm them down."],
    )

    request = rules_agent.requests[0]
    state = orchestrator.current_state("goblin-camp")
    assert request.allowed_outcomes == (
        "success",
        "failure",
        "complication",
        "peaceful",
    )
    assert request.check_hints == ("Persuasion",)
    assert roll_dice.expressions == ["1d20+1"]
    assert state.outcome == "de-escalated"
    assert "Roll: calm goblins = 16." in narrator_agent.frames[-1].resolved_outcomes
    assert "social_resolution:" in result.output_text


def test_social_check_with_outcome_emits_encounter_completed_event() -> None:
    memory = FakeMemoryRepository()
    rules_agent = FakeRulesAgent(
        (
            RulesAdjudication(
                is_legal=True,
                action_type="social_check",
                summary="The goblins back away.",
                roll_requests=(),
                state_effects=(
                    StateEffect(
                        "set_encounter_outcome",
                        "encounter:goblin-camp",
                        "de-escalated",
                    ),
                ),
                reasoning_summary="The check succeeds.",
            ),
        )
    )
    orchestrator = EncounterOrchestrator(
        state_repository=_social_repository(),
        rules_agent=rules_agent,
        narrator_agent=FakeNarratorAgent(),
        roll_dice=FakeDice(()),
        decision_adapter=FakeDecisionAdapter(
            (_decision("adjudicate_social_check", requires_rules_resolution=True),)
        ),
        memory_repository=memory,
    )

    orchestrator.run_encounter(
        encounter_id="goblin-camp",
        player_inputs=["I try to calm them down."],
    )

    completed = [e for e in memory.events if e.get("type") == "encounter_completed"]
    assert len(completed) == 1
    assert completed[0]["outcome"] == "de-escalated"


def test_social_check_without_outcome_does_not_emit_encounter_completed_event() -> None:
    memory = FakeMemoryRepository()
    rules_agent = FakeRulesAgent(
        (
            RulesAdjudication(
                is_legal=True,
                action_type="social_check",
                summary="They look uncertain.",
                roll_requests=(),
                state_effects=(),
                reasoning_summary="Neutral outcome.",
            ),
        )
    )
    orchestrator = EncounterOrchestrator(
        state_repository=_social_repository(),
        rules_agent=rules_agent,
        narrator_agent=FakeNarratorAgent(),
        roll_dice=FakeDice(()),
        decision_adapter=FakeDecisionAdapter(
            (_decision("adjudicate_social_check", requires_rules_resolution=True),)
        ),
        memory_repository=memory,
    )

    orchestrator.run_encounter(
        encounter_id="goblin-camp",
        player_inputs=["I try to calm them down."],
    )

    completed = [e for e in memory.events if e.get("type") == "encounter_completed"]
    assert completed == []


@pytest.mark.parametrize(
    ("next_step", "purpose"),
    [("npc_dialogue", "npc_dialogue"), ("narrate_scene", "scene_response")],
)
def test_non_combat_narrative_decisions_route_to_narrator(
    next_step: str, purpose: str
) -> None:
    narrator_agent = FakeNarratorAgent()
    orchestrator = _orchestrator(
        state_repository=_social_repository(),
        decision_adapter=FakeDecisionAdapter(
            (_decision(next_step, reason_summary="The goblin answers."),)
        ),
        narrator_agent=narrator_agent,
    )

    result = orchestrator.run_encounter(
        encounter_id="goblin-camp",
        player_inputs=["I ask what they want."],
    )

    assert narrator_agent.frames[-1].purpose == purpose
    assert narrator_agent.frames[-1].resolved_outcomes == ("The goblin answers.",)
    assert f"{purpose}: The goblin answers." in result.output_text


def test_aggressive_input_rolls_initiative_enters_combat_and_records_event() -> None:
    roll_dice = FakeDice((18, 12))
    narrator_agent = FakeNarratorAgent()
    orchestrator = _orchestrator(
        state_repository=_social_repository(),
        decision_adapter=FakeDecisionAdapter((_decision("roll_initiative"),)),
        narrator_agent=narrator_agent,
        roll_dice=roll_dice,
    )

    result = orchestrator.run_encounter(
        encounter_id="goblin-camp",
        player_inputs=["I draw steel and rush the goblin."],
    )

    state = orchestrator.current_state("goblin-camp")
    assert result.completed is False
    assert state.phase is EncounterPhase.COMBAT
    assert state.outcome == "combat"
    assert state.initiative_order == ("pc:talia", "npc:goblin-scout")
    assert state.public_events[-1].startswith("Initiative: Talia 18, Goblin Scout 12.")
    assert roll_dice.expressions == ["1d20+2", "1d20+2"]
    assert narrator_agent.frames[-1].purpose == "combat_start"


def test_enter_combat_emits_encounter_completed_event() -> None:
    memory = FakeMemoryRepository()
    orchestrator = EncounterOrchestrator(
        state_repository=_social_repository(),
        rules_agent=FakeRulesAgent(),
        narrator_agent=FakeNarratorAgent(),
        roll_dice=FakeDice((18, 12)),
        decision_adapter=FakeDecisionAdapter((_decision("roll_initiative"),)),
        memory_repository=memory,
    )

    orchestrator.run_encounter(
        encounter_id="goblin-camp",
        player_inputs=["I draw steel and rush the goblin."],
    )

    completed_events = [
        e for e in memory.events if e.get("type") == "encounter_completed"
    ]
    assert len(completed_events) == 1
    assert completed_events[0]["outcome"] == "combat"
    assert completed_events[0]["encounter_id"] == "goblin-camp"


def test_invalid_orchestration_decision_raises_without_saving_mutated_state() -> None:
    repository = _social_repository()
    original_state = repository.load_encounter("goblin-camp")
    orchestrator = _orchestrator(
        state_repository=repository,
        decision_adapter=FakeDecisionAdapter((_decision("summon_dragon"),)),
    )

    with pytest.raises(
        ValueError,
        match="invalid orchestration next_step: summon_dragon",
    ):
        orchestrator.run_encounter(
            encounter_id="goblin-camp",
            player_inputs=["I try something confusing."],
        )

    assert repository.load_encounter("goblin-camp") == original_state


def test_invalid_decision_after_scene_opening_leaves_default_state_unchanged() -> None:
    repository = StateRepository.from_default_encounter()
    original_state = repository.load_encounter("goblin-camp")
    orchestrator = _orchestrator(
        state_repository=repository,
        decision_adapter=FakeDecisionAdapter((_decision("summon_dragon"),)),
    )

    with pytest.raises(
        ValueError,
        match="invalid orchestration next_step: summon_dragon",
    ):
        orchestrator.run_encounter(
            encounter_id="goblin-camp",
            player_inputs=["I try something confusing."],
        )

    assert repository.load_encounter("goblin-camp") == original_state


def test_missing_decision_adapter_fails_fast() -> None:
    orchestrator = EncounterOrchestrator(
        state_repository=_social_repository(),
        rules_agent=FakeRulesAgent(),
        narrator_agent=FakeNarratorAgent(),
        roll_dice=FakeDice(()),
        decision_adapter=None,
    )

    with pytest.raises(ValueError, match="missing decision adapter"):
        orchestrator.run_encounter(
            encounter_id="goblin-camp",
            player_inputs=["I talk to the goblins."],
        )


def test_non_mapping_decision_payload_is_rejected() -> None:
    orchestrator = _orchestrator(
        state_repository=_social_repository(),
        decision_adapter=FakeDecisionAdapter(("not-json-object",)),
    )

    with pytest.raises(TypeError, match="invalid orchestration decision payload"):
        orchestrator.run_encounter(
            encounter_id="goblin-camp",
            player_inputs=["I talk to the goblins."],
        )


@pytest.mark.parametrize(
    ("payload", "error_type", "match"),
    [
        (
            {
                "next_actor": None,
                "requires_rules_resolution": False,
                "recommended_check": None,
                "phase_transition": None,
                "player_prompt": None,
                "reason_summary": "missing step",
            },
            TypeError,
            "next_step",
        ),
        (
            _decision("narrate_scene", next_actor=42),
            TypeError,
            "next_actor",
        ),
        (
            _decision("narrate_scene", requires_rules_resolution="false"),
            ValueError,
            "requires_rules_resolution",
        ),
    ],
)
def test_malformed_decision_fields_are_rejected(
    payload: dict[str, object],
    error_type: type[Exception],
    match: str,
) -> None:
    orchestrator = _orchestrator(
        state_repository=_social_repository(),
        decision_adapter=FakeDecisionAdapter((payload,)),
    )

    with pytest.raises(error_type, match=match):
        orchestrator.run_encounter(
            encounter_id="goblin-camp",
            player_inputs=["I talk to the goblins."],
        )


@pytest.mark.parametrize(
    ("decision", "player_input", "expected_outcome"),
    [
        (
            _decision(
                "complete_encounter",
                outcome="",
                phase_transition="de-escalated",
            ),
            "I lower my weapon.",
            "de-escalated",
        ),
        (
            _decision(
                "complete_encounter",
                reason_summary="The offer of peace works.",
                outcome="",
            ),
            "I negotiate.",
            "peaceful",
        ),
        (
            _decision("complete_encounter", outcome=""),
            "I leave the ravine.",
            "complete",
        ),
    ],
)
def test_completion_outcome_fallbacks(
    decision: dict[str, object],
    player_input: str,
    expected_outcome: str,
) -> None:
    orchestrator = _orchestrator(
        state_repository=_social_repository(),
        decision_adapter=FakeDecisionAdapter((decision,)),
    )

    result = orchestrator.run_encounter(
        encounter_id="goblin-camp",
        player_inputs=[player_input],
    )

    assert result.completed is True
    assert orchestrator.current_state("goblin-camp").outcome == expected_outcome
    assert f"complete_encounter: {expected_outcome}" in result.output_text


def test_combat_attack_adjudicates_roll_effects_and_narrates_turn_result() -> None:
    rules_agent = FakeRulesAgent(
        (
            RulesAdjudication(
                is_legal=True,
                action_type="attack",
                summary="Talia hits the goblin scout for 5 damage.",
                roll_requests=(
                    RollRequest(
                        owner="player",
                        visibility=RollVisibility.PUBLIC,
                        expression="1d20+5",
                        purpose="longsword attack",
                    ),
                ),
                state_effects=(
                    StateEffect(
                        "append_public_event",
                        "encounter:goblin-camp",
                        "Talia hits the goblin scout for 5 damage.",
                    ),
                    StateEffect("change_hp", "npc:goblin-scout", -5),
                ),
                reasoning_summary="attack resolved",
            ),
        )
    )
    roll_dice = FakeDice((17,))
    narrator_agent = FakeNarratorAgent()
    orchestrator = _orchestrator(
        state_repository=_combat_repository(),
        rules_agent=rules_agent,
        narrator_agent=narrator_agent,
        roll_dice=roll_dice,
    )

    result = orchestrator.run_encounter(
        encounter_id="goblin-camp",
        player_inputs=["I attack the goblin scout."],
    )

    request = rules_agent.requests[0]
    state = orchestrator.current_state("goblin-camp")
    assert request.actor_id == "pc:talia"
    assert request.intent == "I attack the goblin scout."
    assert request.phase is EncounterPhase.COMBAT
    assert request.allowed_outcomes == ("hit", "miss", "damage", "defeated")
    assert roll_dice.expressions == ["1d20+5"]
    assert state.actors["npc:goblin-scout"].hp_current == _DAMAGED_GOBLIN_HP
    assert "Roll: longsword attack = 17." in state.public_events
    assert "Talia hits the goblin scout for 5 damage." in state.public_events
    assert narrator_agent.frames[-1].purpose == "combat_turn_result"
    assert "combat_turn_result:" in result.output_text


def test_combat_swing_routes_to_attack_adjudication() -> None:
    rules_agent = FakeRulesAgent(
        (
            RulesAdjudication(
                is_legal=True,
                action_type="attack",
                summary="Talia swings at the goblin scout.",
                reasoning_summary="attack resolved",
            ),
        )
    )
    orchestrator = _orchestrator(
        state_repository=_combat_repository(),
        rules_agent=rules_agent,
    )

    result = orchestrator.run_encounter(
        encounter_id="goblin-camp",
        player_inputs=["I swing my sword."],
    )

    assert rules_agent.requests[0].intent == "I swing my sword."
    assert "combat_turn_result:" in result.output_text


def test_unsupported_combat_input_fails_closed_without_decision_adapter() -> None:
    decision_adapter = FakeDecisionAdapter((_decision("complete_encounter"),))
    orchestrator = _orchestrator(
        state_repository=_combat_repository(),
        decision_adapter=decision_adapter,
    )

    with pytest.raises(ValueError, match="unsupported combat input"):
        orchestrator.run_encounter(
            encounter_id="goblin-camp",
            player_inputs=["I wait and watch."],
        )

    assert decision_adapter.calls == []


def test_save_and_quit_persists_active_encounter_and_records_event() -> None:
    memory_repository = FakeMemoryRepository()
    repository = _combat_repository()
    orchestrator = EncounterOrchestrator(
        state_repository=repository,
        rules_agent=FakeRulesAgent(),
        narrator_agent=FakeNarratorAgent(),
        roll_dice=FakeDice(()),
        decision_adapter=FakeDecisionAdapter(()),
        memory_repository=memory_repository,
    )

    result = orchestrator.run_encounter(
        encounter_id="goblin-camp",
        player_inputs=["save and quit"],
    )

    state = repository.load_encounter("goblin-camp")
    assert result.completed is False
    assert "saved" in result.output_text.lower()
    assert state.phase is EncounterPhase.COMBAT
    assert memory_repository.events == [
        {
            "type": "encounter_saved",
            "encounter_id": "goblin-camp",
            "phase": "combat",
            "outcome": "combat",
        }
    ]


def test_save_and_quit_without_memory_repository_does_not_raise() -> None:
    repository = _combat_repository()
    orchestrator = EncounterOrchestrator(
        state_repository=repository,
        rules_agent=FakeRulesAgent(),
        narrator_agent=FakeNarratorAgent(),
        roll_dice=FakeDice(()),
        decision_adapter=FakeDecisionAdapter(()),
        memory_repository=None,
    )

    result = orchestrator.run_encounter(
        encounter_id="goblin-camp",
        player_inputs=["save and quit"],
    )

    assert result.completed is False
    assert "saved" in result.output_text.lower()


def test_completed_encounter_records_durable_event() -> None:
    memory_repository = FakeMemoryRepository()
    orchestrator = EncounterOrchestrator(
        state_repository=_social_repository(),
        rules_agent=FakeRulesAgent(),
        narrator_agent=FakeNarratorAgent(),
        roll_dice=FakeDice(()),
        decision_adapter=FakeDecisionAdapter(
            (_decision("complete_encounter", outcome="peaceful"),)
        ),
        memory_repository=memory_repository,
    )

    orchestrator.run_encounter(
        encounter_id="goblin-camp",
        player_inputs=["I offer peace."],
    )

    assert memory_repository.events == [
        {
            "type": "encounter_completed",
            "encounter_id": "goblin-camp",
            "outcome": "peaceful",
        }
    ]
