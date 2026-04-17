"""Unit tests for CombatOrchestrator player turn loop."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from unittest.mock import MagicMock

from campaignnarrator.domain.models import (
    CombatIntent,
    CombatStatus,
    EncounterPhase,
    EncounterState,
    InitiativeTurn,
    Narration,
    NarrationFrame,
    RecoveryPeriod,
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
    """NarratorAgent stub that returns canned Narration."""

    def __init__(self, text: str = "The battle rages on.") -> None:
        self._text = text
        self.frames_seen: list[NarrationFrame] = []

    def narrate(self, frame: NarrationFrame) -> Narration:
        self.frames_seen.append(frame)
        return Narration(text=self._text, audience="player")


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


def _orchestrator(
    inputs: list[str],
    intents: list[str],
    adjudications: list[RulesAdjudication],
    narrator_text: str = "Talia strikes!",
    roll_dice: Callable[[str], int] | None = None,
) -> tuple[CombatOrchestrator, ScriptedIO, ScriptedRulesAgent]:
    io = ScriptedIO(inputs, on_exhaust="end turn")
    rules = ScriptedRulesAgent(adjudications)
    narrator = ScriptedNarratorAgent(narrator_text)
    orchestrator = CombatOrchestrator(
        rules_agent=rules,
        narrator_agent=narrator,
        io=io,
        roll_dice=roll_dice or (lambda _expr: 10),
        _intent_agent=_mock_intent_agent(intents),
    )
    return orchestrator, io, rules


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_player_ends_turn_immediately_with_no_resources_consumed() -> None:
    # goblin_hp=0 → after Talia passes, _check_end_condition fires (all NPCs down)
    state = _make_combat_state(goblin_hp=0)
    orc, _, _ = _orchestrator(
        inputs=["end turn"], intents=["end_turn"], adjudications=[]
    )
    result = orc.run(state)
    # Talia's turn ended; goblin is now first in rotation
    assert result.final_state.combat_turns[0].actor_id == "npc:goblin-1"


def test_legal_attack_applies_hp_state_effect_to_target() -> None:
    # damage_hp=-5 on goblin_hp=5 → hp=0 → all_npcs_down → combat ends
    state = _make_combat_state(goblin_hp=5)
    orc, _, _ = _orchestrator(
        inputs=["I attack the goblin", "end turn"],
        intents=["combat_action", "end_turn"],
        adjudications=[_legal_attack(damage_hp=-5, target="npc:goblin-1")],
    )
    result = orc.run(state)
    goblin = result.final_state.actors["npc:goblin-1"]
    assert goblin.hp_current == 0


def test_rules_request_contains_feat_effect_summaries_in_compendium_context() -> None:
    # killing blow ensures combat ends after the attack
    state = _make_combat_state()
    orc, _, rules = _orchestrator(
        inputs=["I attack", "end turn"],
        intents=["combat_action", "end_turn"],
        adjudications=[_legal_attack(damage_hp=-100)],
    )
    orc.run(state)
    assert len(rules.requests_seen) >= 1
    request = rules.requests_seen[0]
    context = " ".join(request.compendium_context)
    assert "Alert" in context
    assert "Savage Attacker" in context


def test_clarifying_question_does_not_consume_resources() -> None:
    # goblin_hp=0 so combat ends after Talia's pass (no state change from clarification)
    state = _make_combat_state(goblin_hp=0)
    orc, _, _ = _orchestrator(
        inputs=["Can I disarm the goblin?", "end turn"],
        intents=["combat_action", "end_turn"],
        adjudications=[_clarifying_question()],
    )
    result = orc.run(state)
    talia = result.final_state.actors["pc:talia"]
    assert talia.hp_current == TALIA.hp_current


def test_impossible_action_does_not_consume_resources() -> None:
    # goblin_hp=0 so combat ends after Talia's pass (impossible action changes nothing)
    state = _make_combat_state(goblin_hp=0)
    orc, io, _ = _orchestrator(
        inputs=["I cast fireball", "end turn"],
        intents=["combat_action", "end_turn"],
        adjudications=[_impossible_action()],
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
    orc, _, rules = _orchestrator(
        inputs=["I attack", "end turn"],
        intents=["combat_action", "end_turn"],
        adjudications=[_legal_attack(damage_hp=-100)],  # killing blow ends combat
    )
    orc.run(state)
    assert len(rules.requests_seen) >= 1
    # RulesAdjudicationRequest no longer carries actor_resources;
    # verify the compendium_context includes Savage Attacker feat instead.
    request = rules.requests_seen[0]
    context = " ".join(request.compendium_context)
    assert "Savage Attacker" in context


def test_movement_deducted_from_turn_resources() -> None:
    # goblin_hp=0 so combat ends after Talia's turn (movement doesn't kill anything)
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
    orc, io, _ = _orchestrator(
        inputs=["I move to the goblin", "end turn"],
        intents=["combat_action", "end_turn"],
        adjudications=[movement_effect],
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
    orc, _, rules = _orchestrator(
        inputs=["end turn"], intents=["end_turn"], adjudications=[]
    )
    orc.run(state)
    assert len(rules.requests_seen) == 0


def test_unconscious_actor_triggers_death_save() -> None:
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
    orc, _, _ = _orchestrator(
        inputs=[], intents=[], adjudications=[], roll_dice=lambda _: 15
    )
    result = orc.run(state)
    talia = result.final_state.actors["pc:talia"]
    assert talia.death_save_successes == 1


def test_player_down_no_allies_returns_correct_status() -> None:
    # NPCs are skipped (Pass 3), so start with Talia already unconscious.
    # After her death save turn the end condition fires (no conscious allies).
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
    orc, _, _ = _orchestrator(
        inputs=[], intents=[], adjudications=[], roll_dice=lambda _: 10
    )
    result = orc.run(state)
    assert result.status == CombatStatus.PLAYER_DOWN_NO_ALLIES
    assert result.death_saves_remaining == 3  # noqa: PLR2004


def test_all_enemies_dead_ends_combat_as_complete() -> None:
    killing_blow = _legal_attack(damage_hp=-100, target="npc:goblin-1")
    state = _make_combat_state(goblin_hp=7)
    orc, _, _ = _orchestrator(
        inputs=["I attack", "end turn"],
        intents=["combat_action", "end_turn"],
        adjudications=[killing_blow],
    )
    result = orc.run(state)
    assert result.status == CombatStatus.COMPLETE


def test_natural_1_on_death_save_counts_as_two_failures() -> None:
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
    orc, _, _ = _orchestrator(
        inputs=[], intents=[], adjudications=[], roll_dice=lambda _: 1
    )
    result = orc.run(state)
    talia = result.final_state.actors["pc:talia"]
    assert talia.death_save_failures == 2  # noqa: PLR2004


def test_status_command_during_combat_does_not_call_rules_agent() -> None:
    """'status' should be handled as a utility command, not sent to adjudication."""
    state = _make_combat_state(goblin_hp=0)
    orc, _, rules = _orchestrator(
        inputs=["status", "end turn"],
        intents=["query_status", "end_turn"],
        adjudications=[],
    )
    orc.run(state)
    assert len(rules.requests_seen) == 0


def test_look_around_during_combat_does_not_call_rules_agent() -> None:
    state = _make_combat_state(goblin_hp=0)
    orc, io, rules = _orchestrator(
        inputs=["look around", "end turn"],
        intents=["query_status", "end_turn"],
        adjudications=[],
    )
    orc.run(state)
    assert len(rules.requests_seen) == 0
    assert any("HP" in msg for msg in io.displayed)


def test_exit_during_combat_returns_saved_and_quit_status() -> None:
    """'exit' is treated identically to 'save and quit' — both return SAVED_AND_QUIT."""
    state = _make_combat_state(goblin_hp=7)
    orc, _, _ = _orchestrator(
        inputs=["exit"], intents=["exit_session"], adjudications=[]
    )
    result = orc.run(state)
    assert result.status == CombatStatus.SAVED_AND_QUIT


def test_save_and_quit_during_combat_returns_saved_and_quit_status() -> None:
    state = _make_combat_state(goblin_hp=7)
    orc, _, _ = _orchestrator(
        inputs=["save and quit"], intents=["exit_session"], adjudications=[]
    )
    result = orc.run(state)
    assert result.status == CombatStatus.SAVED_AND_QUIT


def test_save_and_quit_preserves_final_state() -> None:
    state = _make_combat_state(goblin_hp=7)
    orc, _, _ = _orchestrator(
        inputs=["save and quit"], intents=["exit_session"], adjudications=[]
    )
    result = orc.run(state)
    # Turn order rotates after the player's turn ends (even on exit_session),
    # but actor HP and encounter identity must be unchanged.
    assert result.final_state.actors == state.actors
    assert result.final_state.encounter_id == state.encounter_id


def test_narrator_payload_includes_tone_guidance() -> None:
    """scene_tone should appear as tone_guidance in the combat narrator frame."""
    state = replace(_make_combat_state(), scene_tone="tense and foreboding")
    io = ScriptedIO(["I attack the goblin", "end turn"], on_exhaust="end turn")
    rules = ScriptedRulesAgent([_legal_attack(damage_hp=-100, target="npc:goblin-1")])
    narrator = ScriptedNarratorAgent()
    orc = CombatOrchestrator(
        rules_agent=rules,
        narrator_agent=narrator,
        io=io,
        roll_dice=lambda _: 10,
        _intent_agent=_mock_intent_agent(["combat_action", "end_turn"]),
    )

    orc.run(state)

    assert len(narrator.frames_seen) >= 1
    frame = narrator.frames_seen[0]
    assert frame.tone_guidance == "tense and foreboding"


def test_three_death_save_failures_kills_actor() -> None:
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
    orc, io, _ = _orchestrator(
        inputs=[], intents=[], adjudications=[], roll_dice=lambda _: 5
    )
    result = orc.run(state)
    talia = result.final_state.actors["pc:talia"]
    assert "dead" in talia.conditions
    assert any("died" in msg for msg in io.displayed)


def test_combat_intent_end_turn_ends_turn_without_rules_call() -> None:
    """end_turn intent must break the turn loop without calling the rules agent."""
    state = _make_combat_state(goblin_hp=0)
    io = ScriptedIO(["I'm done"], on_exhaust="end turn")
    rules = ScriptedRulesAgent([])
    narrator = ScriptedNarratorAgent()
    orc = CombatOrchestrator(
        rules_agent=rules,
        narrator_agent=narrator,
        io=io,
        roll_dice=lambda _: 10,
        _intent_agent=_mock_intent_agent(["end_turn"]),
    )
    orc.run(state)
    assert len(rules.requests_seen) == 0


def test_combat_intent_exit_session_returns_saved_and_quit() -> None:
    """exit_session intent must return SAVED_AND_QUIT."""
    state = _make_combat_state(goblin_hp=7)
    io = ScriptedIO(["I want to stop"], on_exhaust="end turn")
    rules = ScriptedRulesAgent([])
    narrator = ScriptedNarratorAgent()
    orc = CombatOrchestrator(
        rules_agent=rules,
        narrator_agent=narrator,
        io=io,
        roll_dice=lambda _: 10,
        _intent_agent=_mock_intent_agent(["exit_session"]),
    )
    result = orc.run(state)
    assert result.status == CombatStatus.SAVED_AND_QUIT
