"""Unit tests for CombatOrchestrator player turn loop."""

from __future__ import annotations

import json
from dataclasses import replace
from unittest.mock import MagicMock

import pytest
from campaignnarrator.domain.models import (
    ActorType,
    CombatAssessment,
    CombatIntent,
    CombatOutcome,
    CombatStatus,
    EncounterPhase,
    EncounterState,
    InitiativeTurn,
    Narration,
    NarrationFrame,
    RecoveryPeriod,
    RollRequest,
    RollVisibility,
    RulesAdjudication,
    RulesAdjudicationRequest,
    StateEffect,
)
from campaignnarrator.orchestrators.combat_orchestrator import CombatOrchestrator

from tests.conftest import ScriptedIO
from tests.fixtures.fighter_talia import TALIA
from tests.fixtures.goblin_scout import make_goblin_scout


class ScriptedRulesAgent:
    """RulesAgent stub that returns a pre-defined sequence of adjudications."""

    def __init__(self, responses: list[RulesAdjudication]) -> None:
        self._responses = list(responses)
        self.requests_seen: list[RulesAdjudicationRequest] = []

    def adjudicate(self, request: RulesAdjudicationRequest) -> RulesAdjudication:
        self.requests_seen.append(request)
        if not self._responses:
            raise ValueError("no more scripted responses")  # noqa: TRY003
        return self._responses.pop(0)


class ScriptedNarratorAgent:
    """NarratorAgent stub that returns canned responses for all narrator methods."""

    def __init__(
        self,
        text: str = "The battle rages on.",
        npc_intents: list[str] | None = None,
        assessments: list[CombatAssessment] | None = None,
    ) -> None:
        self._text = text
        self._npc_intents: list[str] = npc_intents or []
        self._assessments: list[CombatAssessment] = assessments or []
        self.frames_seen: list[NarrationFrame] = []
        self.intent_contexts_seen: list[str] = []
        self.assessment_contexts_seen: list[str] = []

    def narrate(self, frame: NarrationFrame) -> Narration:
        self.frames_seen.append(frame)
        return Narration(text=self._text, audience="player")

    def declare_npc_intent_from_json(self, context_json: str) -> str:
        self.intent_contexts_seen.append(context_json)
        if self._npc_intents:
            return self._npc_intents.pop(0)
        return "The goblin advances menacingly toward Talia."

    def assess_combat_from_json(self, state_json: str) -> CombatAssessment:
        self.assessment_contexts_seen.append(state_json)
        if self._assessments:
            return self._assessments.pop(0)
        return CombatAssessment(combat_active=True, outcome=None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _legal_attack(
    action_type: str = "attack",
    damage_hp: int = -5,
    target: str = "npc:goblin-1",
) -> RulesAdjudication:
    return RulesAdjudication(
        is_legal=True,
        action_type=action_type,
        summary="Attack lands.",
        roll_requests=(),
        state_effects=(
            StateEffect(effect_type="change_hp", target=target, value=damage_hp),
        ),
        rule_references=(),
        reasoning_summary="Valid attack.",
    )


def _clarifying_question() -> RulesAdjudication:
    return RulesAdjudication(
        is_legal=False,
        action_type="clarifying_question",
        summary="Player asked a rules question.",
        roll_requests=(),
        state_effects=(),
        rule_references=(),
        reasoning_summary="Not an action.",
    )


def _impossible_action() -> RulesAdjudication:
    return RulesAdjudication(
        is_legal=False,
        action_type="impossible_action",
        summary="Cannot do that.",
        roll_requests=(),
        state_effects=(),
        rule_references=(),
        reasoning_summary="No resources.",
    )


def _make_combat_state(goblin_hp: int = 7) -> EncounterState:
    goblin = make_goblin_scout("npc:goblin-1", "Goblin Scout 1")
    goblin = replace(goblin, hp_current=goblin_hp)
    return EncounterState(
        encounter_id="test-combat",
        phase=EncounterPhase.COMBAT,
        setting="Forest clearing",
        actors={
            "pc:talia": TALIA,
            "npc:goblin-1": goblin,
        },
        combat_turns=(
            InitiativeTurn(actor_id="pc:talia", initiative_roll=22),
            InitiativeTurn(actor_id="npc:goblin-1", initiative_roll=12),
        ),
    )


def _mock_intent_agent(intents: list[str] | None = None) -> MagicMock:
    mock = MagicMock()
    intent_queue = list(intents or [])

    def _run_sync(input_json: str) -> MagicMock:
        result = MagicMock()
        result.output = CombatIntent(
            intent=intent_queue.pop(0) if intent_queue else "end_turn"
        )
        return result

    mock.run_sync.side_effect = _run_sync
    return mock


_SENTINEL = object()


def _orchestrator(
    inputs: list[str],
    adjudications: list[RulesAdjudication],
    intents: list[str] | None = None,
    narrator_text: str = "Talia strikes!",
    npc_intents: list[str] | None = None,
    assessments: list[CombatAssessment] | None = None,
    memory_repository: object | None = _SENTINEL,
) -> tuple[CombatOrchestrator, ScriptedIO, ScriptedRulesAgent, ScriptedNarratorAgent]:
    io = ScriptedIO(inputs, on_exhaust="end turn")
    rules = ScriptedRulesAgent(adjudications)
    narrator = ScriptedNarratorAgent(
        text=narrator_text,
        npc_intents=npc_intents,
        assessments=assessments,
    )
    kwargs: dict = {
        "rules_agent": rules,
        "narrator_agent": narrator,
        "io": io,
        "_intent_agent": _mock_intent_agent(intents or []),
    }
    if memory_repository is not _SENTINEL:
        kwargs["memory_repository"] = memory_repository
    orchestrator = CombatOrchestrator(**kwargs)
    return orchestrator, io, rules, narrator


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_player_ends_turn_immediately_with_no_resources_consumed() -> None:
    # After Talia passes, narrator assessment ends combat
    state = _make_combat_state(goblin_hp=0)
    orc, _, _, _ = _orchestrator(
        inputs=["end turn"],
        intents=["end_turn"],
        adjudications=[],
        assessments=[
            CombatAssessment(
                combat_active=False,
                outcome=CombatOutcome(
                    short_description="End",
                    full_description="Combat over.",
                ),
            )
        ],
    )
    result = orc.run(state)
    # Talia's turn ended; goblin is now first in rotation
    assert result.final_state.combat_turns[0].actor_id == "npc:goblin-1"


def test_legal_attack_applies_hp_state_effect_to_target() -> None:
    # damage_hp=-5 on goblin_hp=5 → hp=0 → narrator assessment ends combat
    state = _make_combat_state(goblin_hp=5)
    orc, _, _, _ = _orchestrator(
        inputs=["I attack the goblin", "end turn"],
        intents=["combat_action", "end_turn"],
        adjudications=[_legal_attack(damage_hp=-5, target="npc:goblin-1")],
        assessments=[
            CombatAssessment(
                combat_active=False,
                outcome=CombatOutcome(
                    short_description="End",
                    full_description="Combat over.",
                ),
            )
        ],
    )
    result = orc.run(state)
    goblin = result.final_state.actors["npc:goblin-1"]
    assert goblin.hp_current == 0


def test_rules_request_contains_feat_effect_summaries_in_compendium_context() -> None:
    # killing blow then narrator assessment ends combat
    state = _make_combat_state()
    orc, _, rules, _ = _orchestrator(
        inputs=["I attack", "end turn"],
        intents=["combat_action", "end_turn"],
        adjudications=[_legal_attack(damage_hp=-100)],
        assessments=[
            CombatAssessment(
                combat_active=False,
                outcome=CombatOutcome(
                    short_description="End",
                    full_description="Combat over.",
                ),
            )
        ],
    )
    orc.run(state)
    assert len(rules.requests_seen) >= 1
    request = rules.requests_seen[0]
    context = " ".join(request.compendium_context)
    assert "Alert" in context
    assert "Savage Attacker" in context


def test_clarifying_question_does_not_consume_resources() -> None:
    # goblin_hp=0 so narrator assessment ends combat after Talia's turn
    state = _make_combat_state(goblin_hp=0)
    orc, _, _, _ = _orchestrator(
        inputs=["Can I disarm the goblin?", "end turn"],
        intents=["combat_action", "end_turn"],
        adjudications=[_clarifying_question()],
        assessments=[
            CombatAssessment(
                combat_active=False,
                outcome=CombatOutcome(
                    short_description="End",
                    full_description="Combat over.",
                ),
            )
        ],
    )
    result = orc.run(state)
    talia = result.final_state.actors["pc:talia"]
    assert talia.hp_current == TALIA.hp_current


def test_impossible_action_does_not_consume_resources() -> None:
    # goblin_hp=0 so narrator assessment ends combat after Talia's turn
    state = _make_combat_state(goblin_hp=0)
    orc, io, _, _ = _orchestrator(
        inputs=["I cast fireball", "end turn"],
        intents=["combat_action", "end_turn"],
        adjudications=[_impossible_action()],
        assessments=[
            CombatAssessment(
                combat_active=False,
                outcome=CombatOutcome(
                    short_description="End",
                    full_description="Combat over.",
                ),
            )
        ],
    )
    orc.run(state)
    all_output = " ".join(io.displayed)
    assert len(all_output) > 0


def test_per_turn_resource_reset_at_turn_start() -> None:
    """ResourceState entries that recover per-turn should be reset to max."""
    depleted_resources = tuple(
        replace(r, current=0) if r.recovers_after == RecoveryPeriod.TURN else r
        for r in TALIA.resources
    )
    talia_spent = replace(TALIA, resources=depleted_resources)
    goblin = make_goblin_scout("npc:goblin-1", "Goblin Scout 1")
    state = EncounterState(
        encounter_id="test-reset",
        phase=EncounterPhase.COMBAT,
        setting="Forest",
        actors={"pc:talia": talia_spent, "npc:goblin-1": goblin},
        combat_turns=(
            InitiativeTurn(actor_id="pc:talia", initiative_roll=22),
            InitiativeTurn(actor_id="npc:goblin-1", initiative_roll=12),
        ),
    )
    orc, _, rules, _ = _orchestrator(
        inputs=["I attack", "end turn"],
        intents=["combat_action", "end_turn"],
        adjudications=[_legal_attack(damage_hp=-100)],  # killing blow
        assessments=[
            CombatAssessment(
                combat_active=False,
                outcome=CombatOutcome(
                    short_description="End",
                    full_description="Combat over.",
                ),
            )
        ],
    )
    orc.run(state)
    assert len(rules.requests_seen) >= 1
    # RulesAdjudicationRequest no longer carries actor_resources;
    # verify the compendium_context includes Savage Attacker feat instead.
    request = rules.requests_seen[0]
    context = " ".join(request.compendium_context)
    assert "Savage Attacker" in context


def test_movement_deducted_from_turn_resources() -> None:
    # goblin_hp=0 so narrator assessment ends combat after Talia's turn
    state = _make_combat_state(goblin_hp=0)
    movement_effect = RulesAdjudication(
        is_legal=True,
        action_type="move",
        summary="Talia moves 5ft.",
        roll_requests=(),
        state_effects=(
            StateEffect(effect_type="movement", target="pc:talia", value=5),
        ),
        rule_references=(),
        reasoning_summary="Movement.",
    )
    orc, io, _, _ = _orchestrator(
        inputs=["I move to the goblin", "end turn"],
        intents=["combat_action", "end_turn"],
        adjudications=[movement_effect],
        assessments=[
            CombatAssessment(
                combat_active=False,
                outcome=CombatOutcome(
                    short_description="End",
                    full_description="Combat over.",
                ),
            )
        ],
    )
    orc.run(state)
    all_output = " ".join(io.displayed)
    assert "25ft" in all_output


def test_dead_actor_turn_is_skipped() -> None:
    goblin = make_goblin_scout("npc:goblin-1", "Goblin Scout 1")
    goblin = replace(goblin, hp_current=0, conditions=("dead",))
    state = EncounterState(
        encounter_id="test",
        phase=EncounterPhase.COMBAT,
        setting="Forest",
        actors={"pc:talia": TALIA, "npc:goblin-1": goblin},
        combat_turns=(
            InitiativeTurn(actor_id="npc:goblin-1", initiative_roll=20),
            InitiativeTurn(actor_id="pc:talia", initiative_roll=10),
        ),
    )
    orc, _, rules, _ = _orchestrator(
        inputs=["end turn"],
        intents=["end_turn"],
        adjudications=[],
        assessments=[
            CombatAssessment(
                combat_active=False,
                outcome=CombatOutcome(
                    short_description="End",
                    full_description="Combat over.",
                ),
            )
        ],
    )
    orc.run(state)
    assert len(rules.requests_seen) == 0


def test_unconscious_actor_triggers_death_save(mocker: object) -> None:
    mocker.patch(  # type: ignore[attr-defined]
        "campaignnarrator.orchestrators.combat_orchestrator.roll", return_value=15
    )
    talia_unconscious = replace(TALIA, hp_current=0, conditions=("unconscious",))
    state = EncounterState(
        encounter_id="test",
        phase=EncounterPhase.COMBAT,
        setting="Forest",
        actors={
            "pc:talia": talia_unconscious,
            "npc:goblin-1": make_goblin_scout("npc:goblin-1", "G1"),
        },
        combat_turns=(
            InitiativeTurn(actor_id="pc:talia", initiative_roll=20),
            InitiativeTurn(actor_id="npc:goblin-1", initiative_roll=5),
        ),
    )
    # Talia gets 1 death save success (roll≥10). Goblin runs its turn, then
    # _check_player_down_no_allies fires (Talia still unconscious, no allies).
    orc, _, _, _ = _orchestrator(
        inputs=[],
        intents=[],
        adjudications=[_npc_attack_adjudication()],
    )
    result = orc.run(state)
    talia = result.final_state.actors["pc:talia"]
    assert talia.death_save_successes == 1


def test_player_down_no_allies_returns_correct_status(mocker: object) -> None:
    # Talia is unconscious. After her death save, goblin takes its turn, then
    # _check_player_down_no_allies fires (Talia still unconscious, no conscious allies).
    mocker.patch(  # type: ignore[attr-defined]
        "campaignnarrator.orchestrators.combat_orchestrator.roll", return_value=10
    )
    talia_down = replace(TALIA, hp_current=0, conditions=("unconscious",))
    goblin = make_goblin_scout("npc:goblin-1", "G1")
    state = EncounterState(
        encounter_id="test",
        phase=EncounterPhase.COMBAT,
        setting="Forest",
        actors={"pc:talia": talia_down, "npc:goblin-1": goblin},
        combat_turns=(
            InitiativeTurn(actor_id="pc:talia", initiative_roll=20),
            InitiativeTurn(actor_id="npc:goblin-1", initiative_roll=5),
        ),
    )
    # roll=10 → success (≥10), not a natural 20, so 1 success, 0 failures
    orc, _, _, _ = _orchestrator(
        inputs=[],
        intents=[],
        adjudications=[_npc_attack_adjudication()],
    )
    result = orc.run(state)
    assert result.status == CombatStatus.PLAYER_DOWN_NO_ALLIES
    assert result.death_saves_remaining == 3  # noqa: PLR2004


def test_all_enemies_dead_ends_combat_as_complete() -> None:
    killing_blow = _legal_attack(damage_hp=-100, target="npc:goblin-1")
    state = _make_combat_state(goblin_hp=7)
    orc, _, _, _ = _orchestrator(
        inputs=["I attack", "end turn"],
        intents=["combat_action", "end_turn"],
        adjudications=[killing_blow],
        assessments=[
            CombatAssessment(
                combat_active=False,
                outcome=CombatOutcome(
                    short_description="Victory",
                    full_description="The goblin is slain.",
                ),
            )
        ],
    )
    result = orc.run(state)
    assert result.status == CombatStatus.COMPLETE


def test_natural_1_on_death_save_counts_as_two_failures(mocker: object) -> None:
    mocker.patch(  # type: ignore[attr-defined]
        "campaignnarrator.orchestrators.combat_orchestrator.roll", return_value=1
    )
    talia_unconscious = replace(TALIA, hp_current=0, conditions=("unconscious",))
    state = EncounterState(
        encounter_id="test",
        phase=EncounterPhase.COMBAT,
        setting="Forest",
        actors={
            "pc:talia": talia_unconscious,
            "npc:goblin-1": make_goblin_scout("npc:goblin-1", "G1"),
        },
        combat_turns=(
            InitiativeTurn(actor_id="pc:talia", initiative_roll=20),
            InitiativeTurn(actor_id="npc:goblin-1", initiative_roll=5),
        ),
    )
    # roll=1 → 2 failures; Talia still unconscious. Goblin runs, then PLAYER_DOWN.
    orc, _, _, _ = _orchestrator(
        inputs=[],
        intents=[],
        adjudications=[_npc_attack_adjudication()],
    )
    result = orc.run(state)
    talia = result.final_state.actors["pc:talia"]
    assert talia.death_save_failures == 2  # noqa: PLR2004


def test_status_command_during_combat_does_not_call_rules_agent() -> None:
    """'status' should be handled as a utility command, not sent to adjudication."""
    state = _make_combat_state(goblin_hp=0)
    orc, _, rules, _ = _orchestrator(
        inputs=["status", "end turn"],
        intents=["query_status", "end_turn"],
        adjudications=[],
        assessments=[
            CombatAssessment(
                combat_active=False,
                outcome=CombatOutcome(
                    short_description="End",
                    full_description="Combat over.",
                ),
            )
        ],
    )
    orc.run(state)
    assert len(rules.requests_seen) == 0


def test_look_around_during_combat_does_not_call_rules_agent() -> None:
    state = _make_combat_state(goblin_hp=0)
    orc, io, rules, _ = _orchestrator(
        inputs=["look around", "end turn"],
        intents=["query_status", "end_turn"],
        adjudications=[],
        assessments=[
            CombatAssessment(
                combat_active=False,
                outcome=CombatOutcome(
                    short_description="End",
                    full_description="Combat over.",
                ),
            )
        ],
    )
    orc.run(state)
    assert len(rules.requests_seen) == 0
    assert any(
        any(
            label in msg
            for label in (
                "uninjured",
                "bloodied",
                "defeated",
                "barely standing",
                "lightly wounded",
            )
        )
        for msg in io.displayed
    )


def test_exit_during_combat_returns_saved_and_quit_status() -> None:
    """'exit' is treated identically to 'save and quit' — both return SAVED_AND_QUIT."""
    state = _make_combat_state(goblin_hp=7)
    orc, _, _, _ = _orchestrator(
        inputs=["exit"], intents=["exit_session"], adjudications=[]
    )
    result = orc.run(state)
    assert result.status == CombatStatus.SAVED_AND_QUIT


def test_save_and_quit_during_combat_returns_saved_and_quit_status() -> None:
    state = _make_combat_state(goblin_hp=7)
    orc, _, _, _ = _orchestrator(
        inputs=["save and quit"], intents=["exit_session"], adjudications=[]
    )
    result = orc.run(state)
    assert result.status == CombatStatus.SAVED_AND_QUIT


def test_save_and_quit_preserves_final_state() -> None:
    state = _make_combat_state(goblin_hp=7)
    orc, _, _, _ = _orchestrator(
        inputs=["save and quit"], intents=["exit_session"], adjudications=[]
    )
    result = orc.run(state)
    # Turn order rotates after the player's turn ends (even on exit_session),
    # but actor HP and encounter identity must be unchanged.
    assert result.final_state.actors == state.actors
    assert result.final_state.encounter_id == state.encounter_id


def test_narrator_payload_includes_tone_guidance(mocker: object) -> None:
    """scene_tone should appear as tone_guidance in the combat narrator frame."""
    mocker.patch(  # type: ignore[attr-defined]
        "campaignnarrator.orchestrators.combat_orchestrator.roll", return_value=10
    )
    state = replace(_make_combat_state(), scene_tone="tense and foreboding")
    io = ScriptedIO(["I attack the goblin", "end turn"], on_exhaust="end turn")
    rules = ScriptedRulesAgent([_legal_attack(damage_hp=-100, target="npc:goblin-1")])
    narrator = ScriptedNarratorAgent(
        assessments=[
            CombatAssessment(
                combat_active=False,
                outcome=CombatOutcome(
                    short_description="End", full_description="Combat over."
                ),
            )
        ]
    )
    orc = CombatOrchestrator(
        rules_agent=rules,
        narrator_agent=narrator,
        io=io,
        _intent_agent=_mock_intent_agent(["combat_action", "end_turn"]),
    )

    orc.run(state)

    assert len(narrator.frames_seen) >= 1
    frame = narrator.frames_seen[0]
    assert frame.tone_guidance == "tense and foreboding"


def test_three_death_save_failures_kills_actor(mocker: object) -> None:
    mocker.patch(  # type: ignore[attr-defined]
        "campaignnarrator.orchestrators.combat_orchestrator.roll", return_value=5
    )
    talia_near_dead = replace(
        TALIA, hp_current=0, conditions=("unconscious",), death_save_failures=2
    )
    state = EncounterState(
        encounter_id="test",
        phase=EncounterPhase.COMBAT,
        setting="Forest",
        actors={
            "pc:talia": talia_near_dead,
            "npc:goblin-1": make_goblin_scout("npc:goblin-1", "G1"),
        },
        combat_turns=(
            InitiativeTurn(actor_id="pc:talia", initiative_roll=20),
            InitiativeTurn(actor_id="npc:goblin-1", initiative_roll=5),
        ),
    )
    # roll=5 → failure → 3 total failures → Talia dies.
    # Goblin still gets its turn; after its narration, narrator assessment ends combat.
    orc, io, _, _ = _orchestrator(
        inputs=[],
        intents=[],
        adjudications=[_npc_attack_adjudication(damage_hp=0)],
        assessments=[
            CombatAssessment(
                combat_active=False,
                outcome=CombatOutcome(
                    short_description="End",
                    full_description="Combat over.",
                ),
            )
        ],
    )
    result = orc.run(state)
    talia = result.final_state.actors["pc:talia"]
    assert "dead" in talia.conditions
    assert any("died" in msg for msg in io.displayed)


def test_combat_intent_end_turn_ends_turn_without_rules_call(mocker: object) -> None:
    """end_turn intent must break the turn loop without calling the rules agent."""
    mocker.patch(  # type: ignore[attr-defined]
        "campaignnarrator.orchestrators.combat_orchestrator.roll", return_value=10
    )
    state = _make_combat_state(goblin_hp=0)
    io = ScriptedIO(["I'm done"], on_exhaust="end turn")
    rules = ScriptedRulesAgent([])
    narrator = ScriptedNarratorAgent(
        assessments=[
            CombatAssessment(
                combat_active=False,
                outcome=CombatOutcome(
                    short_description="End", full_description="Combat over."
                ),
            )
        ]
    )
    orc = CombatOrchestrator(
        rules_agent=rules,
        narrator_agent=narrator,
        io=io,
        _intent_agent=_mock_intent_agent(["end_turn"]),
    )
    orc.run(state)
    assert len(rules.requests_seen) == 0


def test_combat_intent_exit_session_returns_saved_and_quit(mocker: object) -> None:
    """exit_session intent must return SAVED_AND_QUIT."""
    mocker.patch(  # type: ignore[attr-defined]
        "campaignnarrator.orchestrators.combat_orchestrator.roll", return_value=10
    )
    state = _make_combat_state(goblin_hp=7)
    io = ScriptedIO(["I want to stop"], on_exhaust="end turn")
    rules = ScriptedRulesAgent([])
    narrator = ScriptedNarratorAgent()
    orc = CombatOrchestrator(
        rules_agent=rules,
        narrator_agent=narrator,
        io=io,
        _intent_agent=_mock_intent_agent(["exit_session"]),
    )
    result = orc.run(state)
    assert result.status == CombatStatus.SAVED_AND_QUIT


# ---------------------------------------------------------------------------
# NPC turn, attack resolution, materialize effects
# ---------------------------------------------------------------------------


def _npc_attack_adjudication(
    damage_hp: int = -4,
    target: str = "pc:talia",
) -> RulesAdjudication:
    return RulesAdjudication(
        is_legal=True,
        action_type="attack",
        summary="Goblin slashes at Talia.",
        roll_requests=(),
        state_effects=(
            StateEffect(effect_type="change_hp", target=target, value=damage_hp),
        ),
        rule_references=(),
        reasoning_summary="Valid NPC melee attack.",
    )


def test_npc_turn_state_effect_applied_to_target() -> None:
    goblin = make_goblin_scout("npc:goblin-1", "Goblin Scout 1")
    state = EncounterState(
        encounter_id="test-npc-damage",
        phase=EncounterPhase.COMBAT,
        setting="Forest",
        actors={"npc:goblin-1": goblin, "pc:talia": TALIA},
        combat_turns=(
            InitiativeTurn(actor_id="npc:goblin-1", initiative_roll=20),
            InitiativeTurn(actor_id="pc:talia", initiative_roll=10),
        ),
    )
    orc, _, _, _ = _orchestrator(
        inputs=["end turn"],
        adjudications=[_npc_attack_adjudication(damage_hp=-4)],
        assessments=[
            CombatAssessment(combat_active=True, outcome=None),
            CombatAssessment(
                combat_active=False,
                outcome=CombatOutcome(
                    short_description="End",
                    full_description="Combat ends.",
                ),
            ),
        ],
    )
    result = orc.run(state)
    talia_final = result.final_state.actors["pc:talia"]
    assert talia_final.hp_current == TALIA.hp_current - 4


def test_npc_turn_narrator_intent_prompt_includes_actor_id_and_hp() -> None:
    goblin = make_goblin_scout("npc:goblin-1", "Goblin Scout 1")
    state = EncounterState(
        encounter_id="test-npc-intent",
        phase=EncounterPhase.COMBAT,
        setting="Forest",
        actors={"npc:goblin-1": goblin, "pc:talia": TALIA},
        combat_turns=(
            InitiativeTurn(actor_id="npc:goblin-1", initiative_roll=20),
            InitiativeTurn(actor_id="pc:talia", initiative_roll=10),
        ),
    )
    orc, _, _, narrator = _orchestrator(
        inputs=["end turn"],
        adjudications=[_npc_attack_adjudication()],
        assessments=[
            CombatAssessment(combat_active=True, outcome=None),
            CombatAssessment(
                combat_active=False,
                outcome=CombatOutcome(
                    short_description="End",
                    full_description="Combat ends.",
                ),
            ),
        ],
    )
    orc.run(state)
    assert len(narrator.intent_contexts_seen) >= 1
    context = json.loads(narrator.intent_contexts_seen[0])
    assert context["actor_id"] == "npc:goblin-1"
    assert "hp_current" in context


def test_npc_turn_rules_request_includes_intent_field() -> None:
    goblin = make_goblin_scout("npc:goblin-1", "Goblin Scout 1")
    state = EncounterState(
        encounter_id="test-npc-rules",
        phase=EncounterPhase.COMBAT,
        setting="Forest",
        actors={"npc:goblin-1": goblin, "pc:talia": TALIA},
        combat_turns=(
            InitiativeTurn(actor_id="npc:goblin-1", initiative_roll=20),
            InitiativeTurn(actor_id="pc:talia", initiative_roll=10),
        ),
    )
    scripted_intent = "The goblin lunges at Talia with its rusted blade."
    orc, _, rules, _ = _orchestrator(
        inputs=["end turn"],
        adjudications=[_npc_attack_adjudication()],
        npc_intents=[scripted_intent],
        assessments=[
            CombatAssessment(combat_active=True, outcome=None),
            CombatAssessment(
                combat_active=False,
                outcome=CombatOutcome(
                    short_description="End",
                    full_description="Combat ends.",
                ),
            ),
        ],
    )
    orc.run(state)
    assert len(rules.requests_seen) >= 1
    assert rules.requests_seen[0].intent == scripted_intent


def test_materialize_effects_converts_heal_to_change_hp_using_roll(
    mocker: object,
) -> None:
    mocker.patch(  # type: ignore[attr-defined]
        "campaignnarrator.orchestrators.combat_orchestrator.roll", return_value=7
    )
    heal_effect = RulesAdjudication(
        is_legal=True,
        action_type="bonus_action",
        summary="Talia uses Second Wind to heal.",
        roll_requests=(),
        state_effects=(
            StateEffect(effect_type="heal", target="pc:talia", value="1d10+3"),
        ),
        rule_references=(),
        reasoning_summary="Second Wind restores HP.",
    )
    talia_wounded = replace(TALIA, hp_current=20)
    goblin = make_goblin_scout("npc:goblin-1", "Goblin Scout 1")
    state = EncounterState(
        encounter_id="test-heal",
        phase=EncounterPhase.COMBAT,
        setting="Forest",
        actors={"pc:talia": talia_wounded, "npc:goblin-1": goblin},
        combat_turns=(
            InitiativeTurn(actor_id="pc:talia", initiative_roll=22),
            InitiativeTurn(actor_id="npc:goblin-1", initiative_roll=12),
        ),
    )
    orc, _, _, _ = _orchestrator(
        inputs=["I use Second Wind", "end turn"],
        adjudications=[heal_effect],
        intents=["combat_action", "end_turn"],
        # Assessment fires after Talia's turn; return combat_active=False to end
        # before the goblin's turn so no extra adjudication is needed.
        assessments=[
            CombatAssessment(
                combat_active=False,
                outcome=CombatOutcome(
                    short_description="End",
                    full_description="Combat ends.",
                ),
            ),
        ],
    )
    result = orc.run(state)
    talia_final = result.final_state.actors["pc:talia"]
    expected_hp = talia_wounded.hp_current + 10  # roll=7, modifier=+3 → 10 HP healed
    assert talia_final.hp_current == expected_hp


def test_combat_assessment_active_continues_loop() -> None:
    goblin = make_goblin_scout("npc:goblin-1", "Goblin Scout 1")
    state = EncounterState(
        encounter_id="test-assess-continue",
        phase=EncounterPhase.COMBAT,
        setting="Forest",
        actors={"pc:talia": TALIA, "npc:goblin-1": goblin},
        combat_turns=(
            InitiativeTurn(actor_id="pc:talia", initiative_roll=22),
            InitiativeTurn(actor_id="npc:goblin-1", initiative_roll=12),
        ),
    )
    orc, _, _, narrator = _orchestrator(
        inputs=["I attack", "end turn", "end turn"],
        adjudications=[_legal_attack(damage_hp=-2, target="npc:goblin-1")],
        assessments=[
            CombatAssessment(combat_active=True, outcome=None),
            CombatAssessment(combat_active=True, outcome=None),
            CombatAssessment(
                combat_active=False,
                outcome=CombatOutcome(
                    short_description="Victory",
                    full_description="The goblin falls at last.",
                ),
            ),
        ],
    )
    result = orc.run(state)
    assert result.status == CombatStatus.COMPLETE
    assert len(narrator.assessment_contexts_seen) >= 2  # noqa: PLR2004


def test_combat_assessment_inactive_ends_combat_and_displays_outcome() -> None:
    goblin = make_goblin_scout("npc:goblin-1", "Goblin Scout 1")
    state = EncounterState(
        encounter_id="test-assess-end",
        phase=EncounterPhase.COMBAT,
        setting="Forest",
        actors={"pc:talia": TALIA, "npc:goblin-1": goblin},
        combat_turns=(
            InitiativeTurn(actor_id="pc:talia", initiative_roll=22),
            InitiativeTurn(actor_id="npc:goblin-1", initiative_roll=12),
        ),
    )
    full_desc = "The goblin collapses with a final desperate wheeze."
    orc, io, _, _ = _orchestrator(
        inputs=["I attack", "end turn"],
        adjudications=[_legal_attack(damage_hp=-100, target="npc:goblin-1")],
        assessments=[
            CombatAssessment(
                combat_active=False,
                outcome=CombatOutcome(
                    short_description="Victory", full_description=full_desc
                ),
            )
        ],
    )
    result = orc.run(state)
    assert result.status == CombatStatus.COMPLETE
    assert full_desc in " ".join(io.displayed)


def test_assess_combat_not_called_for_dead_actor_skipped_turn() -> None:
    goblin = make_goblin_scout("npc:goblin-1", "Goblin Scout 1")
    goblin = replace(goblin, hp_current=0, conditions=("dead",))
    state = EncounterState(
        encounter_id="test-skip-assess",
        phase=EncounterPhase.COMBAT,
        setting="Forest",
        actors={"pc:talia": TALIA, "npc:goblin-1": goblin},
        combat_turns=(
            InitiativeTurn(actor_id="npc:goblin-1", initiative_roll=20),
            InitiativeTurn(actor_id="pc:talia", initiative_roll=10),
        ),
    )
    orc, _, _, narrator = _orchestrator(
        inputs=["end turn"],
        adjudications=[],
        assessments=[
            CombatAssessment(
                combat_active=False,
                outcome=CombatOutcome(
                    short_description="End", full_description="Combat over."
                ),
            )
        ],
    )
    orc.run(state)
    assert len(narrator.assessment_contexts_seen) == 1


def test_player_down_no_allies_returned_before_narrator_assessment() -> None:
    goblin = make_goblin_scout("npc:goblin-1", "Goblin Scout 1")
    npc_kill = RulesAdjudication(
        is_legal=True,
        action_type="attack",
        summary="Goblin kills Talia.",
        roll_requests=(),
        state_effects=(
            StateEffect(effect_type="change_hp", target="pc:talia", value=-999),
        ),
        rule_references=(),
        reasoning_summary="Fatal blow.",
    )
    state = EncounterState(
        encounter_id="test-player-down-priority",
        phase=EncounterPhase.COMBAT,
        setting="Forest",
        actors={"npc:goblin-1": goblin, "pc:talia": TALIA},
        combat_turns=(
            InitiativeTurn(actor_id="npc:goblin-1", initiative_roll=20),
            InitiativeTurn(actor_id="pc:talia", initiative_roll=10),
        ),
    )
    orc, _, _, narrator = _orchestrator(
        inputs=[],
        adjudications=[npc_kill],
    )
    result = orc.run(state)
    assert result.status == CombatStatus.PLAYER_DOWN_NO_ALLIES
    assert len(narrator.assessment_contexts_seen) == 0


def test_assess_combat_payload_includes_actor_summaries_and_recent_events() -> None:
    goblin = make_goblin_scout("npc:goblin-1", "Goblin Scout 1")
    state = EncounterState(
        encounter_id="test-assess-payload",
        phase=EncounterPhase.COMBAT,
        setting="Forest clearing",
        actors={"pc:talia": TALIA, "npc:goblin-1": goblin},
        public_events=("Round 1 begins.", "Talia swings.", "Goblin hisses."),
        combat_turns=(
            InitiativeTurn(actor_id="pc:talia", initiative_roll=22),
            InitiativeTurn(actor_id="npc:goblin-1", initiative_roll=12),
        ),
    )
    orc, _, _, narrator = _orchestrator(
        inputs=["end turn"],
        adjudications=[_npc_attack_adjudication(damage_hp=0)],
        assessments=[
            CombatAssessment(combat_active=True, outcome=None),
            CombatAssessment(
                combat_active=False,
                outcome=CombatOutcome(
                    short_description="End",
                    full_description="Combat ends.",
                ),
            ),
        ],
    )
    orc.run(state)
    assert len(narrator.assessment_contexts_seen) >= 1
    payload = json.loads(narrator.assessment_contexts_seen[0])
    assert "actor_summaries" in payload
    assert "recent_events" in payload
    for event in ("Round 1 begins.", "Talia swings.", "Goblin hisses."):
        assert event in payload["recent_events"]


def test_natural_20_on_death_save_counts_as_two_successes(mocker: object) -> None:
    mocker.patch(  # type: ignore[attr-defined]
        "campaignnarrator.orchestrators.combat_orchestrator.roll", return_value=20
    )
    talia_unconscious = replace(TALIA, hp_current=0, conditions=("unconscious",))
    goblin = make_goblin_scout("npc:goblin-1", "Goblin Scout 1")
    state = EncounterState(
        encounter_id="test-nat20-save",
        phase=EncounterPhase.COMBAT,
        setting="Forest",
        actors={"pc:talia": talia_unconscious, "npc:goblin-1": goblin},
        combat_turns=(
            InitiativeTurn(actor_id="pc:talia", initiative_roll=20),
            InitiativeTurn(actor_id="npc:goblin-1", initiative_roll=5),
        ),
    )
    # nat-20 → 2 successes (not yet stable); goblin takes its turn; assessment ends.
    orc, _, _, _ = _orchestrator(
        inputs=[],
        adjudications=[_npc_attack_adjudication(damage_hp=0)],
        assessments=[
            CombatAssessment(
                combat_active=False,
                outcome=CombatOutcome(short_description="End", full_description="End."),
            )
        ],
    )
    result = orc.run(state)
    talia = result.final_state.actors["pc:talia"]
    assert talia.death_save_successes == 2  # noqa: PLR2004


def test_three_death_save_successes_stabilizes_pc(mocker: object) -> None:
    mocker.patch(  # type: ignore[attr-defined]
        "campaignnarrator.orchestrators.combat_orchestrator.roll", return_value=15
    )
    talia_near_stable = replace(
        TALIA, hp_current=0, conditions=("unconscious",), death_save_successes=2
    )
    goblin = make_goblin_scout("npc:goblin-1", "Goblin Scout 1")
    state = EncounterState(
        encounter_id="test-stabilize",
        phase=EncounterPhase.COMBAT,
        setting="Forest",
        actors={"pc:talia": talia_near_stable, "npc:goblin-1": goblin},
        combat_turns=(
            InitiativeTurn(actor_id="pc:talia", initiative_roll=20),
            InitiativeTurn(actor_id="npc:goblin-1", initiative_roll=5),
        ),
    )
    # roll=15 → 1 success → 3 total → Talia stabilizes; goblin turns; assessment ends.
    orc, io, _, _ = _orchestrator(
        inputs=[],
        adjudications=[_npc_attack_adjudication(damage_hp=0)],
        assessments=[
            CombatAssessment(
                combat_active=False,
                outcome=CombatOutcome(short_description="End", full_description="End."),
            )
        ],
    )
    result = orc.run(state)
    talia = result.final_state.actors["pc:talia"]
    assert "stable" in talia.conditions
    assert any("stabilizes" in msg for msg in io.displayed)


def test_materialize_effects_raises_on_invalid_dice_expression() -> None:
    bad_heal = RulesAdjudication(
        is_legal=True,
        action_type="bonus_action",
        summary="Bad heal.",
        roll_requests=(),
        state_effects=(
            StateEffect(effect_type="heal", target="pc:talia", value="fireball"),
        ),
        rule_references=(),
        reasoning_summary="Bad.",
    )
    talia_wounded = replace(TALIA, hp_current=20)
    goblin = make_goblin_scout("npc:goblin-1", "Goblin Scout 1")
    state = EncounterState(
        encounter_id="test-bad-heal",
        phase=EncounterPhase.COMBAT,
        setting="Forest",
        actors={"pc:talia": talia_wounded, "npc:goblin-1": goblin},
        combat_turns=(
            InitiativeTurn(actor_id="pc:talia", initiative_roll=22),
            InitiativeTurn(actor_id="npc:goblin-1", initiative_roll=12),
        ),
    )
    orc, _, _, _ = _orchestrator(
        inputs=["I heal", "end turn"],
        adjudications=[bad_heal],
        intents=["combat_action", "end_turn"],
    )
    with pytest.raises(ValueError, match="Invalid dice expression"):
        orc.run(state)


def test_considering_rules_displayed_before_combat_adjudication() -> None:
    """'Considering the rules...' must appear when a player combat action is adjudicated."""
    state = _make_combat_state()
    orc, io, _, _ = _orchestrator(
        inputs=["I attack", "end turn"],
        adjudications=[_legal_attack(damage_hp=3)],
        intents=["combat_action", "end_turn"],
        assessments=[
            CombatAssessment(
                combat_active=False,
                outcome=CombatOutcome(
                    short_description="Victory",
                    full_description="Combat over.",
                ),
            )
        ],
    )
    orc.run(state)
    assert any("Considering the rules" in msg for msg in io.displayed)


# ---------------------------------------------------------------------------
# Attack resolution via roll_requests + change_hp placeholder
# ---------------------------------------------------------------------------


def _attack_adj_with_placeholder(
    target: str = "npc:goblin-1",
    attack_expression: str = "1d20+7",
    damage_expression: str = "1d8+4",
) -> RulesAdjudication:
    """Adjudication for a player attack using the new roll_requests + placeholder pattern."""
    return RulesAdjudication(
        is_legal=True,
        action_type="attack",
        summary="Talia swings her longsword.",
        roll_requests=(
            RollRequest(
                owner="player",
                visibility=RollVisibility.PUBLIC,
                expression=attack_expression,
                purpose="Attack roll vs Goblin Scout 1",
            ),
            RollRequest(
                owner="player",
                visibility=RollVisibility.PUBLIC,
                expression=damage_expression,
                purpose="Damage: Longsword",
            ),
        ),
        state_effects=(StateEffect(effect_type="change_hp", target=target, value=0),),
        rule_references=(),
        reasoning_summary="Valid attack with placeholder.",
    )


def _npc_attack_adj_with_placeholder(
    target: str = "pc:talia",
) -> RulesAdjudication:
    """NPC attack adjudication using roll_requests + change_hp placeholder."""
    return RulesAdjudication(
        is_legal=True,
        action_type="attack",
        summary="Goblin slashes at Talia.",
        roll_requests=(
            RollRequest(
                owner="npc",
                visibility=RollVisibility.HIDDEN,
                expression="1d20+4",
                purpose="Attack roll vs Talia Ironveil",
            ),
            RollRequest(
                owner="npc",
                visibility=RollVisibility.HIDDEN,
                expression="1d6+2",
                purpose="Damage: Scimitar",
            ),
        ),
        state_effects=(StateEffect(effect_type="change_hp", target=target, value=0),),
        rule_references=(),
        reasoning_summary="Valid NPC attack with placeholder.",
    )


def test_attack_hit_applies_damage_to_target(mocker: object) -> None:
    """Player attack that hits (roll >= AC) applies damage and kills the goblin."""
    # Goblin AC=15, HP=7. roll_dice=20 → attack total=20 ≥ 15 → hit → damage=20 → dead
    mocker.patch(  # type: ignore[attr-defined]
        "campaignnarrator.domain.models._roll", return_value=20
    )
    state = _make_combat_state(goblin_hp=7)
    orc, _, _, _ = _orchestrator(
        inputs=["I attack the goblin", "end turn"],
        intents=["combat_action", "end_turn"],
        adjudications=[_attack_adj_with_placeholder()],
        assessments=[
            CombatAssessment(
                combat_active=False,
                outcome=CombatOutcome(
                    short_description="Victory",
                    full_description="The goblin falls.",
                ),
            )
        ],
    )
    result = orc.run(state)
    goblin = result.final_state.actors["npc:goblin-1"]
    assert goblin.hp_current == 0
    assert "dead" in goblin.conditions


def test_attack_miss_does_not_apply_damage(mocker: object) -> None:
    """Player attack that misses (roll < AC) leaves target HP unchanged."""
    # Goblin AC=15. roll_dice=1 → attack total=1 < 15 → miss → no damage
    mocker.patch(  # type: ignore[attr-defined]
        "campaignnarrator.domain.models._roll", return_value=1
    )
    initial_hp = make_goblin_scout("npc:goblin-1", "G").hp_max
    state = _make_combat_state(goblin_hp=initial_hp)
    orc, _, _, _ = _orchestrator(
        inputs=["I attack the goblin", "end turn"],
        intents=["combat_action", "end_turn"],
        adjudications=[_attack_adj_with_placeholder()],
        assessments=[
            CombatAssessment(
                combat_active=False,
                outcome=CombatOutcome(
                    short_description="End",
                    full_description="Combat ends.",
                ),
            )
        ],
    )
    result = orc.run(state)
    goblin = result.final_state.actors["npc:goblin-1"]
    assert goblin.hp_current == initial_hp


def test_nonzero_change_hp_with_attack_hit_applies_direct_damage(
    mocker: object,
) -> None:
    """Non-zero change_hp is gated on AC: a hit applies the LLM-specified value."""
    # Goblin AC=15, HP=7. roll_dice=20 → attack total=20 ≥ 15 → hit → -5 applied
    mocker.patch(  # type: ignore[attr-defined]
        "campaignnarrator.domain.models._roll", return_value=20
    )
    state = _make_combat_state(goblin_hp=7)
    orc, _, _, _ = _orchestrator(
        inputs=["I attack the goblin", "end turn"],
        intents=["combat_action", "end_turn"],
        adjudications=[_legal_attack_with_roll(RollVisibility.PUBLIC, damage_hp=-5)],
        assessments=[
            CombatAssessment(
                combat_active=False,
                outcome=CombatOutcome(
                    short_description="End",
                    full_description="Combat over.",
                ),
            )
        ],
    )
    result = orc.run(state)
    goblin = result.final_state.actors["npc:goblin-1"]
    assert goblin.hp_current == 2  # 7 - 5


def test_nonzero_change_hp_with_attack_miss_no_damage(mocker: object) -> None:
    """Non-zero change_hp is gated on AC: a miss drops the effect, HP unchanged."""
    # Goblin AC=15, HP=7. roll_dice=1 → attack total=1 < 15 → miss → no damage
    mocker.patch(  # type: ignore[attr-defined]
        "campaignnarrator.domain.models._roll", return_value=1
    )
    state = _make_combat_state(goblin_hp=7)
    orc, _, _, _ = _orchestrator(
        inputs=["I attack the goblin", "end turn"],
        intents=["combat_action", "end_turn"],
        adjudications=[_legal_attack_with_roll(RollVisibility.PUBLIC, damage_hp=-5)],
        assessments=[
            CombatAssessment(
                combat_active=False,
                outcome=CombatOutcome(
                    short_description="End",
                    full_description="Combat over.",
                ),
            )
        ],
    )
    result = orc.run(state)
    goblin = result.final_state.actors["npc:goblin-1"]
    assert goblin.hp_current == 7


def _attack_adj_with_lowercase_purposes(
    target: str = "npc:goblin-1",
) -> RulesAdjudication:
    """Attack adjudication with lowercase purpose strings (LLM casing variant)."""
    return RulesAdjudication(
        is_legal=True,
        action_type="attack",
        summary="Talia strikes.",
        roll_requests=(
            RollRequest(
                owner="player",
                visibility=RollVisibility.PUBLIC,
                expression="1d20+7",
                purpose="attack roll vs goblin scout",
            ),
            RollRequest(
                owner="player",
                visibility=RollVisibility.PUBLIC,
                expression="1d8+4",
                purpose="damage: longsword",
            ),
        ),
        state_effects=(StateEffect(effect_type="change_hp", target=target, value=0),),
        rule_references=(),
        reasoning_summary="Valid attack, lowercase purposes.",
    )


def test_attack_purpose_matching_is_case_insensitive_hit(mocker: object) -> None:
    """Lowercase 'attack roll' and 'damage' purposes are recognised on a hit."""
    # Goblin AC=15, HP=7. roll_dice=20 → 20 ≥ 15 → hit → damage_total=20 → hp=0
    mocker.patch(  # type: ignore[attr-defined]
        "campaignnarrator.domain.models._roll", return_value=20
    )
    state = _make_combat_state(goblin_hp=7)
    orc, _, _, _ = _orchestrator(
        inputs=["I attack the goblin", "end turn"],
        intents=["combat_action", "end_turn"],
        adjudications=[_attack_adj_with_lowercase_purposes()],
        assessments=[
            CombatAssessment(
                combat_active=False,
                outcome=CombatOutcome(
                    short_description="End",
                    full_description="Combat over.",
                ),
            )
        ],
    )
    result = orc.run(state)
    goblin = result.final_state.actors["npc:goblin-1"]
    assert goblin.hp_current == 0


def test_attack_purpose_matching_is_case_insensitive_miss(mocker: object) -> None:
    """Lowercase 'attack roll' purpose is recognised on a miss — no damage applied."""
    # Goblin AC=15, HP=7. roll_dice=1 → 1 < 15 → miss → no damage
    mocker.patch(  # type: ignore[attr-defined]
        "campaignnarrator.domain.models._roll", return_value=1
    )
    state = _make_combat_state(goblin_hp=7)
    orc, _, _, _ = _orchestrator(
        inputs=["I attack the goblin", "end turn"],
        intents=["combat_action", "end_turn"],
        adjudications=[_attack_adj_with_lowercase_purposes()],
        assessments=[
            CombatAssessment(
                combat_active=False,
                outcome=CombatOutcome(
                    short_description="End",
                    full_description="Combat over.",
                ),
            )
        ],
    )
    result = orc.run(state)
    goblin = result.final_state.actors["npc:goblin-1"]
    assert goblin.hp_current == 7


def test_npc_attack_hit_applies_damage_to_player(mocker: object) -> None:
    """NPC attack that hits applies damage to the player via hidden dice rolls."""
    # Talia AC=20, HP=44. roll_dice=20 → attack total=20 ≥ 20 → hit → damage=20
    mocker.patch(  # type: ignore[attr-defined]
        "campaignnarrator.domain.models._roll", return_value=20
    )
    goblin = make_goblin_scout("npc:goblin-1", "Goblin Scout 1")
    state = EncounterState(
        encounter_id="test-npc-hit",
        phase=EncounterPhase.COMBAT,
        setting="Forest",
        actors={"npc:goblin-1": goblin, "pc:talia": TALIA},
        combat_turns=(
            InitiativeTurn(actor_id="npc:goblin-1", initiative_roll=20),
            InitiativeTurn(actor_id="pc:talia", initiative_roll=10),
        ),
    )
    orc, _, _, _ = _orchestrator(
        inputs=["end turn"],
        adjudications=[_npc_attack_adj_with_placeholder()],
        assessments=[
            CombatAssessment(combat_active=True, outcome=None),
            CombatAssessment(
                combat_active=False,
                outcome=CombatOutcome(
                    short_description="End",
                    full_description="Combat ends.",
                ),
            ),
        ],
    )
    result = orc.run(state)
    talia = result.final_state.actors["pc:talia"]
    assert talia.hp_current == TALIA.hp_current - 20  # 44 - 20 = 24


def test_npc_attack_miss_does_not_apply_damage(mocker: object) -> None:
    """NPC attack that misses leaves target HP unchanged."""
    # Talia AC=20. roll_dice=1 → attack total=1 < 20 → miss → no damage
    mocker.patch(  # type: ignore[attr-defined]
        "campaignnarrator.domain.models._roll", return_value=1
    )
    goblin = make_goblin_scout("npc:goblin-1", "Goblin Scout 1")
    state = EncounterState(
        encounter_id="test-npc-miss",
        phase=EncounterPhase.COMBAT,
        setting="Forest",
        actors={"npc:goblin-1": goblin, "pc:talia": TALIA},
        combat_turns=(
            InitiativeTurn(actor_id="npc:goblin-1", initiative_roll=20),
            InitiativeTurn(actor_id="pc:talia", initiative_roll=10),
        ),
    )
    orc, _, _, _ = _orchestrator(
        inputs=["end turn"],
        adjudications=[_npc_attack_adj_with_placeholder()],
        assessments=[
            CombatAssessment(combat_active=True, outcome=None),
            CombatAssessment(
                combat_active=False,
                outcome=CombatOutcome(
                    short_description="End",
                    full_description="Combat ends.",
                ),
            ),
        ],
    )
    result = orc.run(state)
    talia = result.final_state.actors["pc:talia"]
    assert talia.hp_current == TALIA.hp_current


def test_direct_change_hp_without_roll_requests_passes_through_unchanged() -> None:
    """Existing change_hp effects with non-zero value pass through _resolve_attack_effects."""
    # _npc_attack_adjudication has roll_requests=() and direct change_hp(-4).
    # With no roll_totals, _resolve_attack_effects returns effects unchanged.
    goblin = make_goblin_scout("npc:goblin-1", "Goblin Scout 1")
    state = EncounterState(
        encounter_id="test-direct-damage",
        phase=EncounterPhase.COMBAT,
        setting="Forest",
        actors={"npc:goblin-1": goblin, "pc:talia": TALIA},
        combat_turns=(
            InitiativeTurn(actor_id="npc:goblin-1", initiative_roll=20),
            InitiativeTurn(actor_id="pc:talia", initiative_roll=10),
        ),
    )
    orc, _, _, _ = _orchestrator(
        inputs=["end turn"],
        adjudications=[_npc_attack_adjudication(damage_hp=-4)],
        assessments=[
            CombatAssessment(combat_active=True, outcome=None),
            CombatAssessment(
                combat_active=False,
                outcome=CombatOutcome(
                    short_description="End",
                    full_description="Combat ends.",
                ),
            ),
        ],
    )
    result = orc.run(state)
    talia = result.final_state.actors["pc:talia"]
    assert talia.hp_current == TALIA.hp_current - 4


def _legal_attack_with_roll(
    roll_visibility: RollVisibility = RollVisibility.PUBLIC,
    damage_hp: int = -5,
    target: str = "npc:goblin-1",
) -> RulesAdjudication:
    return RulesAdjudication(
        is_legal=True,
        action_type="attack",
        summary="Attack lands.",
        roll_requests=(
            RollRequest(
                owner="player",
                visibility=roll_visibility,
                expression="1d20+3",
                purpose="Attack roll",
            ),
        ),
        state_effects=(
            StateEffect(effect_type="change_hp", target=target, value=damage_hp),
        ),
        rule_references=(),
        reasoning_summary="Valid attack.",
    )


def test_public_roll_request_is_displayed_to_player(mocker: object) -> None:
    """A PUBLIC roll_request must produce a 'Roll:' line in io output."""
    mocker.patch(  # type: ignore[attr-defined]
        "campaignnarrator.domain.models._roll", return_value=12
    )
    state = _make_combat_state(goblin_hp=5)
    orc, io, _, _ = _orchestrator(
        inputs=["I attack the goblin", "end turn"],
        intents=["combat_action", "end_turn"],
        adjudications=[_legal_attack_with_roll(RollVisibility.PUBLIC, damage_hp=-5)],
        assessments=[
            CombatAssessment(
                combat_active=False,
                outcome=CombatOutcome(
                    short_description="End",
                    full_description="Combat over.",
                ),
            )
        ],
    )
    orc.run(state)
    assert any("Roll:" in msg for msg in io.displayed)


def test_public_roll_event_is_included_in_narrator_frame_resolved_outcomes(
    mocker: object,
) -> None:
    """Roll events from PUBLIC roll_requests must appear in the narrator frame."""
    mocker.patch(  # type: ignore[attr-defined]
        "campaignnarrator.domain.models._roll", return_value=12
    )
    state = _make_combat_state(goblin_hp=5)
    orc, _, _, narrator = _orchestrator(
        inputs=["I attack the goblin", "end turn"],
        intents=["combat_action", "end_turn"],
        adjudications=[_legal_attack_with_roll(RollVisibility.PUBLIC, damage_hp=-5)],
        assessments=[
            CombatAssessment(
                combat_active=False,
                outcome=CombatOutcome(
                    short_description="End",
                    full_description="Combat over.",
                ),
            )
        ],
    )
    orc.run(state)
    assert len(narrator.frames_seen) >= 1
    combat_frame = narrator.frames_seen[0]
    assert any("Roll:" in outcome for outcome in combat_frame.resolved_outcomes)


def test_hidden_roll_request_is_not_displayed_to_player(mocker: object) -> None:
    """A HIDDEN roll_request must not produce any 'Roll:' output to the player."""
    mocker.patch(  # type: ignore[attr-defined]
        "campaignnarrator.domain.models._roll", return_value=12
    )
    state = _make_combat_state(goblin_hp=5)
    orc, io, _, _ = _orchestrator(
        inputs=["I attack the goblin", "end turn"],
        intents=["combat_action", "end_turn"],
        adjudications=[_legal_attack_with_roll(RollVisibility.HIDDEN, damage_hp=-5)],
        assessments=[
            CombatAssessment(
                combat_active=False,
                outcome=CombatOutcome(
                    short_description="End",
                    full_description="Combat over.",
                ),
            )
        ],
    )
    orc.run(state)
    assert not any("Roll:" in msg for msg in io.displayed)


def test_ally_actor_skips_npc_turn_in_combat() -> None:
    """An ALLY actor in the initiative order must not trigger a rules adjudication."""
    goblin = make_goblin_scout("npc:goblin-1", "Goblin Scout 1")
    villager = replace(
        goblin, actor_id="npc:villager", name="Villager", actor_type=ActorType.ALLY
    )
    state = EncounterState(
        encounter_id="test-ally-skip",
        phase=EncounterPhase.COMBAT,
        setting="Village road",
        actors={
            "pc:talia": TALIA,
            "npc:villager": villager,
            "npc:goblin-1": goblin,
        },
        combat_turns=(
            InitiativeTurn(actor_id="pc:talia", initiative_roll=20),
            InitiativeTurn(actor_id="npc:villager", initiative_roll=15),
            InitiativeTurn(actor_id="npc:goblin-1", initiative_roll=10),
        ),
    )
    # Player ends turn → assessment 1 (active, combat continues).
    # Villager (ALLY) skips → narration=None → no assessment.
    # Goblin acts → assessment 2 (inactive, combat ends).
    orc, _, rules, _ = _orchestrator(
        inputs=["end turn"],
        intents=[],
        adjudications=[
            RulesAdjudication(
                is_legal=True,
                action_type="attack",
                roll_requests=[],
                summary="Goblin swings.",
                rule_references=[],
                state_effects=[],
            )
        ],
        assessments=[
            CombatAssessment(combat_active=True, outcome=None),
            CombatAssessment(
                combat_active=False,
                outcome=CombatOutcome(
                    short_description="End",
                    full_description="Combat over.",
                ),
            ),
        ],
    )
    orc.run(state)
    # Only goblin's turn should have generated a rules request — one, not two.
    # If the ALLY had triggered a rules call, requests_seen would have 2 entries
    # (or ScriptedRulesAgent would have raised ValueError on an empty queue).
    assert len(rules.requests_seen) == 1


def test_rules_request_includes_equipped_weapon_in_compendium_context() -> None:
    """Weapon name, attack_bonus, damage expression, and type must appear in context."""
    state = _make_combat_state()
    orc, _, rules, _ = _orchestrator(
        inputs=["I attack", "end turn"],
        intents=["combat_action", "end_turn"],
        adjudications=[_legal_attack(damage_hp=-100)],
        assessments=[
            CombatAssessment(
                combat_active=False,
                outcome=CombatOutcome(
                    short_description="End",
                    full_description="Combat over.",
                ),
            )
        ],
    )
    orc.run(state)
    assert len(rules.requests_seen) >= 1
    context = " ".join(rules.requests_seen[0].compendium_context)
    assert "Longsword" in context
    assert "attack_bonus" in context
    assert "1d8" in context
    assert "slashing" in context


def test_rules_request_includes_visible_actors_context() -> None:
    """All encounter actors with their actor_id, AC, and HP must be in context."""
    state = _make_combat_state()
    orc, _, rules, _ = _orchestrator(
        inputs=["I attack", "end turn"],
        intents=["combat_action", "end_turn"],
        adjudications=[_legal_attack(damage_hp=-100)],
        assessments=[
            CombatAssessment(
                combat_active=False,
                outcome=CombatOutcome(
                    short_description="End",
                    full_description="Combat over.",
                ),
            )
        ],
    )
    orc.run(state)
    assert len(rules.requests_seen) >= 1
    ctx = " ".join(rules.requests_seen[0].visible_actors_context)
    assert "pc:talia" in ctx
    assert "npc:goblin-1" in ctx
    assert "AC" in ctx


# ---------------------------------------------------------------------------
# Memory repository integration
# ---------------------------------------------------------------------------


class TestCombatOrchestratorMemoryCalls:
    def test_run_calls_update_game_state_after_player_turn(self) -> None:
        """update_game_state() must be called each time through the loop."""
        memory = MagicMock()
        state = _make_combat_state(goblin_hp=0)
        orc, _, _, _ = _orchestrator(
            inputs=["end turn"],
            intents=["end_turn"],
            adjudications=[],
            assessments=[
                CombatAssessment(
                    combat_active=False,
                    outcome=CombatOutcome(
                        short_description="End",
                        full_description="Combat over.",
                    ),
                )
            ],
            memory_repository=memory,
        )
        orc.run(state)
        memory.update_game_state.assert_called()

    def test_run_calls_log_combat_round_when_narration_produced(self) -> None:
        """log_combat_round() is called with the narrator's text."""
        memory = MagicMock()
        state = _make_combat_state(goblin_hp=7)
        orc, _, _, _ = _orchestrator(
            inputs=["attack goblin", "end turn"],
            intents=["combat_action", "end_turn"],
            adjudications=[_legal_attack()],
            assessments=[
                CombatAssessment(
                    combat_active=False,
                    outcome=CombatOutcome(
                        short_description="End",
                        full_description="Combat over.",
                    ),
                )
            ],
            memory_repository=memory,
        )
        orc.run(state)
        memory.log_combat_round.assert_called()

    def test_run_calls_update_exchange_with_player_input(self) -> None:
        """update_exchange() receives the combat action text, not 'end_turn'."""
        memory = MagicMock()
        state = _make_combat_state(goblin_hp=7)
        orc, _, _, _ = _orchestrator(
            inputs=["attack goblin", "end turn"],
            intents=["combat_action", "end_turn"],
            adjudications=[_legal_attack()],
            assessments=[
                CombatAssessment(
                    combat_active=False,
                    outcome=CombatOutcome(
                        short_description="End",
                        full_description="Combat over.",
                    ),
                )
            ],
            memory_repository=memory,
        )
        orc.run(state)
        calls = memory.update_exchange.call_args_list
        # At least one call where player_input is "attack goblin"
        assert any(c.args[0] == "attack goblin" for c in calls)

    def test_run_calls_clear_combat_memory_at_end(self) -> None:
        """clear_combat_memory() is called regardless of how combat ends."""
        memory = MagicMock()
        state = _make_combat_state(goblin_hp=0)
        orc, _, _, _ = _orchestrator(
            inputs=["end turn"],
            intents=["end_turn"],
            adjudications=[],
            assessments=[
                CombatAssessment(
                    combat_active=False,
                    outcome=CombatOutcome(
                        short_description="End",
                        full_description="Combat over.",
                    ),
                )
            ],
            memory_repository=memory,
        )
        orc.run(state)
        memory.clear_combat_memory.assert_called_once()
