"""Unit tests for TurnOrder and CombatState domain models."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from campaignnarrator.domain.models import (
    CombatState,
    CombatStatus,
    InitiativeTurn,
    TurnOrder,
    TurnResources,
)

_ROLL_14 = 14
_ROLL_8 = 8

_TURN_ALICE = InitiativeTurn(actor_id="alice", initiative_roll=_ROLL_14)
_TURN_BOB = InitiativeTurn(actor_id="bob", initiative_roll=_ROLL_8)


# ---------------------------------------------------------------------------
# TurnOrder tests
# ---------------------------------------------------------------------------


def test_turn_order_defaults_to_empty_turns():
    assert TurnOrder().turns == ()


def test_turn_order_current_actor_id_returns_first_actor():
    order = TurnOrder(turns=(_TURN_ALICE, _TURN_BOB))
    assert order.current_actor_id == "alice"


def test_turn_order_current_actor_id_empty_string_when_no_turns():
    assert TurnOrder().current_actor_id == ""


def test_turn_order_end_turn_rotates_to_next_actor():
    order = TurnOrder(turns=(_TURN_ALICE, _TURN_BOB))
    rotated = order.end_turn()
    assert rotated.current_actor_id == "bob"


def test_turn_order_end_turn_wraps_around():
    order = TurnOrder(turns=(_TURN_ALICE,))
    rotated = order.end_turn()
    assert rotated.current_actor_id == "alice"


def test_turn_order_end_turn_no_op_when_empty():
    order = TurnOrder()
    result = order.end_turn()
    assert result is order


def test_turn_order_is_frozen():
    order = TurnOrder(turns=(_TURN_ALICE,))
    with pytest.raises(FrozenInstanceError):
        order.turns = ()  # type: ignore[misc]


def test_turn_order_round_trips_to_dict():
    order = TurnOrder(turns=(_TURN_ALICE, _TURN_BOB))
    restored = TurnOrder.from_dict(order.to_dict())
    assert restored == order


def test_turn_order_from_dict_empty_list_returns_empty():
    result = TurnOrder.from_dict([])
    assert result.turns == ()


def test_turn_order_from_dict_invalid_input_returns_empty():
    result = TurnOrder.from_dict("not-a-list")
    assert result.turns == ()


# ---------------------------------------------------------------------------
# CombatState tests
# ---------------------------------------------------------------------------


def test_combat_state_defaults_to_active_status():
    assert CombatState().status == CombatStatus.ACTIVE


def test_combat_state_defaults_to_empty_turn_order():
    assert CombatState().turn_order.turns == ()


def test_combat_state_defaults_to_full_turn_resources():
    assert CombatState().current_turn_resources.action_available is True


def test_combat_state_defaults_death_saves_to_none():
    assert CombatState().death_saves_remaining is None


def test_combat_state_is_frozen():
    state = CombatState()
    with pytest.raises(FrozenInstanceError):
        state.status = CombatStatus.COMPLETE  # type: ignore[misc]


def test_combat_state_round_trips_to_dict():
    state = CombatState(
        turn_order=TurnOrder(turns=(_TURN_ALICE, _TURN_BOB)),
        status=CombatStatus.ACTIVE,
        current_turn_resources=TurnResources(
            action_available=False,
            bonus_action_available=True,
            reaction_available=True,
            movement_remaining=30,
        ),
        death_saves_remaining=2,
    )
    restored = CombatState.from_dict(state.to_dict())
    assert restored == state


def test_combat_state_from_dict_preserves_status():
    state = CombatState.from_dict({"status": "complete"})
    assert state.status == CombatStatus.COMPLETE


def test_combat_state_from_dict_unknown_status_falls_back_to_active():
    state = CombatState.from_dict({"status": 999})
    assert state.status == CombatStatus.ACTIVE


def test_combat_state_from_dict_preserves_death_saves():
    state = CombatState.from_dict({"death_saves_remaining": 3})
    assert state.death_saves_remaining == 3  # noqa: PLR2004


def test_combat_state_from_dict_death_saves_none_when_absent():
    state = CombatState.from_dict({})
    assert state.death_saves_remaining is None
