"""Integration tests for CombatOrchestrator multi-round flows.

Mocks rules_agent, narrator_agent, and _intent_agent at the protocol
boundary. Real orchestrator, real domain models, real state mutations.
No Docker, no WireMock, no live LLM calls.
"""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock

import pytest
from campaignnarrator.domain.models import (
    ActorRegistry,
    CombatAssessment,
    CombatIntent,
    CombatOutcome,
    CombatState,
    CombatStatus,
    EncounterPhase,
    EncounterState,
    GameState,
    InitiativeTurn,
    Narration,
    NarrationFrame,
    RulesAdjudication,
    RulesAdjudicationRequest,
    StateEffect,
)
from campaignnarrator.domain.models.combat_state import TurnOrder
from campaignnarrator.orchestrators.combat_orchestrator import CombatOrchestrator

from tests.conftest import ScriptedIO
from tests.fixtures.fighter_talia import TALIA
from tests.fixtures.goblin_scout import make_goblin_scout

# ── Scripted stubs ───────────────────────────────────────────────────────────


class _ScriptedRules:
    """Feeds a pre-defined sequence of adjudications in order."""

    def __init__(self, responses: list[RulesAdjudication]) -> None:
        self._responses = list(responses)

    def adjudicate(self, _request: RulesAdjudicationRequest) -> RulesAdjudication:
        if not self._responses:
            pytest.fail("_ScriptedRules: no more adjudications queued")
        return self._responses.pop(0)


class _ScriptedNarrator:
    """Returns canned narration and scripted combat assessments."""

    def __init__(
        self,
        assessments: list[CombatAssessment],
        npc_intents: list[str] | None = None,
    ) -> None:
        self._assessments = list(assessments)
        self._npc_intents = list(npc_intents or [])

    def narrate(self, _frame: NarrationFrame) -> Narration:
        return Narration(text="The battle rages on.")

    def declare_npc_intent_from_json(self, _context_json: str) -> str:
        if self._npc_intents:
            return self._npc_intents.pop(0)
        return "The goblin attacks."

    def assess_combat_from_json(self, _state_json: str) -> CombatAssessment:
        if self._assessments:
            return self._assessments.pop(0)
        return CombatAssessment(combat_active=False, outcome=_COMBAT_OVER)


_COMBAT_OVER = CombatOutcome(
    short_description="Combat ends.",
    full_description="The last enemy falls. The battle is over.",
)

_COMBAT_ACTIVE = CombatAssessment(combat_active=True, outcome=None)
_COMBAT_COMPLETE = CombatAssessment(combat_active=False, outcome=_COMBAT_OVER)


def _intent_agent(intents: list[str]) -> MagicMock:
    mock = MagicMock()
    queue = list(intents)

    def _run_sync(_input_json: str) -> MagicMock:
        result = MagicMock()
        result.output = CombatIntent(intent=queue.pop(0) if queue else "end_turn")
        return result

    mock.run_sync.side_effect = _run_sync
    return mock


def _hit(target: str, damage: int) -> RulesAdjudication:
    """Adjudication that applies damage directly (no dice roll, bypasses AC check)."""
    return RulesAdjudication(
        is_legal=True,
        action_type="attack",
        summary=f"Attack hits for {damage}.",
        roll_requests=(),
        state_effects=(
            StateEffect(effect_type="change_hp", target=target, value=-damage),
        ),
    )


def _miss() -> RulesAdjudication:
    """Adjudication with no state effects (miss)."""
    return RulesAdjudication(
        is_legal=True,
        action_type="attack",
        summary="Attack misses.",
        roll_requests=(),
        state_effects=(),
    )


def _make_game_state(goblin_hp: int = 7) -> GameState:
    goblin = make_goblin_scout("npc:goblin-1", "Goblin Scout")
    goblin = replace(goblin, hp_current=goblin_hp)
    registry = ActorRegistry(actors={"pc:talia": TALIA, "npc:goblin-1": goblin})
    encounter = EncounterState(
        encounter_id="test-enc-001",
        phase=EncounterPhase.COMBAT,
        setting="A dark forest clearing.",
        actor_ids=("pc:talia", "npc:goblin-1"),
        player_actor_id="pc:talia",
    )
    combat = CombatState(
        turn_order=TurnOrder(
            turns=(
                InitiativeTurn(actor_id="pc:talia", initiative_roll=22),
                InitiativeTurn(actor_id="npc:goblin-1", initiative_roll=10),
            )
        ),
        current_turn_resources=TALIA.get_turn_resources(),
    )
    return GameState(actor_registry=registry, encounter=encounter, combat_state=combat)


def _orchestrator(
    *,
    io: ScriptedIO,
    rules: _ScriptedRules,
    narrator: _ScriptedNarrator,
    intents: list[str],
) -> CombatOrchestrator:
    return CombatOrchestrator(
        rules_agent=rules,
        narrator_agent=narrator,
        io=io,
        _intent_agent=_intent_agent(intents),
    )


# ── Single-round tests ───────────────────────────────────────────────────────


class TestSingleRoundCombat:
    def test_player_kills_goblin_combat_ends_complete(self) -> None:
        """Player attacks for full goblin HP; assessment says over; status → COMPLETE."""
        game_state = _make_game_state(goblin_hp=7)
        io = ScriptedIO(["I attack the goblin"], on_exhaust="end turn")
        rules = _ScriptedRules([_hit("npc:goblin-1", damage=7)])
        narrator = _ScriptedNarrator(assessments=[_COMBAT_COMPLETE])
        orch = _orchestrator(
            io=io, rules=rules, narrator=narrator, intents=["combat_action", "end_turn"]
        )

        result = orch.run(game_state)

        assert result.combat_state is not None
        assert result.combat_state.status == CombatStatus.COMPLETE
        assert result.actor_registry.actors["npc:goblin-1"].hp_current == 0

    def test_player_attack_misses_goblin_hp_unchanged(self) -> None:
        """Attack adjudication with no state_effects leaves goblin HP at full."""
        game_state = _make_game_state(goblin_hp=7)
        io = ScriptedIO(["I swing wildly"], on_exhaust="end turn")
        rules = _ScriptedRules([_miss()])
        narrator = _ScriptedNarrator(assessments=[_COMBAT_COMPLETE])
        orch = _orchestrator(
            io=io, rules=rules, narrator=narrator, intents=["combat_action", "end_turn"]
        )

        result = orch.run(game_state)

        goblin_hp_start = make_goblin_scout("npc:goblin-1", "Goblin Scout").hp_max
        assert (
            result.actor_registry.actors["npc:goblin-1"].hp_current == goblin_hp_start
        )


# ── Multi-round tests ────────────────────────────────────────────────────────


class TestMultiRoundCombat:
    def test_npc_turn_damages_player(self) -> None:
        """Goblin's turn fires after player ends turn; player HP decreases by 3."""
        game_state = _make_game_state(goblin_hp=7)
        # TALIA ends immediately — goblin then gets a turn
        io = ScriptedIO([], on_exhaust="end turn")
        rules = _ScriptedRules([_hit("pc:talia", damage=3)])
        # Assessment after TALIA's empty turn: active; after goblin's turn: over
        narrator = _ScriptedNarrator(assessments=[_COMBAT_ACTIVE, _COMBAT_COMPLETE])
        orch = _orchestrator(
            io=io, rules=rules, narrator=narrator, intents=["end_turn"]
        )

        result = orch.run(game_state)

        assert result.actor_registry.actors["pc:talia"].hp_current == TALIA.hp_max - 3

    def test_player_defeats_goblin_over_two_rounds(self) -> None:
        """Two rounds of 4 damage each reduce goblin HP 7 → 3 → 0.

        IO and intent agent are independent streams.  The IO provides raw text
        (irrelevant content); the intent agent classifies each prompt in order.
        Round 1: prompt→"I attack", intent→"combat_action" → 4 dmg;
                 prompt→"I attack again", intent→"end_turn" → end.
        Goblin round 1: no player prompts, misses.
        Round 2: prompt→"end turn" (exhaust), intent→"combat_action" → 4 dmg;
                 prompt→"end turn" (exhaust), intent→"end_turn" → end.
        """
        game_state = _make_game_state(goblin_hp=7)
        io = ScriptedIO(["I attack", "I attack again"], on_exhaust="end turn")
        rules = _ScriptedRules(
            [
                _hit("npc:goblin-1", damage=4),  # TALIA round 1
                _miss(),  # goblin round 1
                _hit("npc:goblin-1", damage=4),  # TALIA round 2
            ]
        )
        narrator = _ScriptedNarrator(
            assessments=[_COMBAT_ACTIVE, _COMBAT_ACTIVE, _COMBAT_COMPLETE]
        )
        orch = _orchestrator(
            io=io,
            rules=rules,
            narrator=narrator,
            intents=["combat_action", "end_turn", "combat_action", "end_turn"],
        )

        result = orch.run(game_state)

        assert result.combat_state.status == CombatStatus.COMPLETE
        assert result.actor_registry.actors["npc:goblin-1"].hp_current == 0


# ── Player-down tests ────────────────────────────────────────────────────────


class TestPlayerDown:
    def test_player_at_zero_hp_sets_player_down_no_allies(self) -> None:
        """Goblin deals lethal damage; GameState detects no conscious allies."""
        game_state = _make_game_state(goblin_hp=100)
        io = ScriptedIO([], on_exhaust="end turn")
        # Goblin hits TALIA for more than max HP
        rules = _ScriptedRules([_hit("pc:talia", damage=50)])
        narrator = _ScriptedNarrator(assessments=[_COMBAT_ACTIVE])
        orch = _orchestrator(
            io=io, rules=rules, narrator=narrator, intents=["end_turn"]
        )

        result = orch.run(game_state)

        talia_after = result.actor_registry.actors["pc:talia"]
        assert talia_after.hp_current == 0
        assert "unconscious" in talia_after.conditions
        assert result.combat_state.status == CombatStatus.PLAYER_DOWN_NO_ALLIES


# ── Save-and-quit tests ──────────────────────────────────────────────────────


class TestSaveAndQuit:
    def test_exit_session_intent_sets_saved_and_quit(self) -> None:
        """Player typing exit mid-turn sets CombatStatus.SAVED_AND_QUIT."""
        game_state = _make_game_state()
        io = ScriptedIO(["save and quit"])
        rules = _ScriptedRules([])
        narrator = _ScriptedNarrator(assessments=[])
        orch = _orchestrator(
            io=io, rules=rules, narrator=narrator, intents=["exit_session"]
        )

        result = orch.run(game_state)

        assert result.combat_state is not None
        assert result.combat_state.status == CombatStatus.SAVED_AND_QUIT


# ── Rogue class mechanics ────────────────────────────────────────────────────


class TestRogueClassMechanics:
    def test_sneak_attack_applies_extra_damage(self) -> None:
        """Rules agent returns sneak-attack adjudication; full damage applied."""
        rogue_goblin = make_goblin_scout("npc:goblin-1", "Goblin Scout")
        # Use a simple ActorState based on TALIA but rogue flavour is irrelevant here —
        # what matters is that the rules agent returns sneak-attack damage (9 total).
        registry = ActorRegistry(
            actors={"pc:talia": TALIA, "npc:goblin-1": rogue_goblin}
        )
        encounter = EncounterState(
            encounter_id="test-enc-sneak",
            phase=EncounterPhase.COMBAT,
            setting="A shadowed alley.",
            actor_ids=("pc:talia", "npc:goblin-1"),
            player_actor_id="pc:talia",
        )
        combat = CombatState(
            turn_order=TurnOrder(
                turns=(
                    InitiativeTurn(actor_id="pc:talia", initiative_roll=20),
                    InitiativeTurn(actor_id="npc:goblin-1", initiative_roll=8),
                )
            ),
            current_turn_resources=TALIA.get_turn_resources(),
        )
        game_state = GameState(
            actor_registry=registry, encounter=encounter, combat_state=combat
        )

        sneak_adjudication = RulesAdjudication(
            is_legal=True,
            action_type="attack",
            summary="Sneak attack hits for 9.",
            roll_requests=(),
            state_effects=(
                StateEffect(effect_type="change_hp", target="npc:goblin-1", value=-9),
            ),
        )

        io = ScriptedIO(["I lunge from the shadows"], on_exhaust="end turn")
        rules = _ScriptedRules([sneak_adjudication])
        narrator = _ScriptedNarrator(assessments=[_COMBAT_COMPLETE])
        orch = _orchestrator(
            io=io,
            rules=rules,
            narrator=narrator,
            intents=["combat_action", "end_turn"],
        )

        result = orch.run(game_state)

        goblin_after = result.actor_registry.actors["npc:goblin-1"]
        # Goblin started at 7 HP, took 9 damage → capped at 0
        assert goblin_after.hp_current == 0
        assert result.combat_state.status == CombatStatus.COMPLETE


# ── Inventory use ─────────────────────────────────────────────────────────────


class TestInventoryUse:
    def test_player_uses_potion_restores_hp_and_decrements_count(self) -> None:
        """bonus_action potion adjudication: HP increases, potion count drops by 1."""
        wounded_talia = replace(TALIA, hp_current=TALIA.hp_max - 14)
        goblin = make_goblin_scout("npc:goblin-1", "Goblin Scout")
        registry = ActorRegistry(
            actors={"pc:talia": wounded_talia, "npc:goblin-1": goblin}
        )
        encounter = EncounterState(
            encounter_id="test-enc-potion",
            phase=EncounterPhase.COMBAT,
            setting="A dungeon corridor.",
            actor_ids=("pc:talia", "npc:goblin-1"),
            player_actor_id="pc:talia",
        )
        combat = CombatState(
            turn_order=TurnOrder(
                turns=(
                    InitiativeTurn(actor_id="pc:talia", initiative_roll=22),
                    InitiativeTurn(actor_id="npc:goblin-1", initiative_roll=10),
                )
            ),
            current_turn_resources=wounded_talia.get_turn_resources(),
        )
        game_state = GameState(
            actor_registry=registry, encounter=encounter, combat_state=combat
        )

        potion_adjudication = RulesAdjudication(
            is_legal=True,
            action_type="bonus_action",
            summary="Player drinks a Potion of Healing and recovers 8 HP.",
            roll_requests=(),
            state_effects=(
                StateEffect(effect_type="change_hp", target="pc:talia", value=8),
                StateEffect(
                    effect_type="inventory_spent", target="pc:talia", value="potion-1"
                ),
            ),
        )

        io = ScriptedIO(["I drink a healing potion"], on_exhaust="end turn")
        rules = _ScriptedRules([potion_adjudication])
        narrator = _ScriptedNarrator(assessments=[_COMBAT_COMPLETE])
        orch = _orchestrator(
            io=io,
            rules=rules,
            narrator=narrator,
            intents=["combat_action", "end_turn"],
        )

        result = orch.run(game_state)

        talia_after = result.actor_registry.actors["pc:talia"]
        assert talia_after.hp_current == wounded_talia.hp_current + 8
        # TALIA starts with count=2; after use, count should be 1
        potion = next(i for i in talia_after.inventory if i.item_id == "potion-1")
        assert potion.count == 1
