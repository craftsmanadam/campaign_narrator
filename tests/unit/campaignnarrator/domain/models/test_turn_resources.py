"""Unit tests for TurnResources.deduct and ResourceUnavailableError."""

from __future__ import annotations

import pytest
from campaignnarrator.domain.models import ResourceUnavailableError, TurnResources

_SPEED_30 = 30
_MOVEMENT_10 = 10
_MOVEMENT_20 = 20
_MOVEMENT_31 = 31


# ---------------------------------------------------------------------------
# Action deduction
# ---------------------------------------------------------------------------


def test_deduct_action_marks_action_unavailable() -> None:
    result = TurnResources().deduct("action")
    assert result.action_available is False


def test_deduct_action_does_not_mutate_original() -> None:
    original = TurnResources()
    original.deduct("action")
    assert original.action_available is True


def test_deduct_action_twice_raises_resource_unavailable() -> None:
    after_first = TurnResources().deduct("action")
    with pytest.raises(ResourceUnavailableError):
        after_first.deduct("action")


def test_deduct_action_error_is_value_error_subclass() -> None:
    assert issubclass(ResourceUnavailableError, ValueError)


# ---------------------------------------------------------------------------
# Bonus action deduction
# ---------------------------------------------------------------------------


def test_deduct_bonus_action_marks_unavailable() -> None:
    result = TurnResources().deduct("bonus_action")
    assert result.bonus_action_available is False


def test_deduct_bonus_action_twice_raises_resource_unavailable() -> None:
    after_first = TurnResources().deduct("bonus_action")
    with pytest.raises(ResourceUnavailableError):
        after_first.deduct("bonus_action")


# ---------------------------------------------------------------------------
# Reaction deduction
# ---------------------------------------------------------------------------


def test_deduct_reaction_marks_unavailable() -> None:
    result = TurnResources().deduct("reaction")
    assert result.reaction_available is False


def test_deduct_reaction_twice_raises_resource_unavailable() -> None:
    after_first = TurnResources().deduct("reaction")
    with pytest.raises(ResourceUnavailableError):
        after_first.deduct("reaction")


# ---------------------------------------------------------------------------
# Movement deduction
# ---------------------------------------------------------------------------


def test_deduct_movement_reduces_remaining() -> None:
    result = TurnResources(movement_remaining=_SPEED_30).deduct(
        "movement", _MOVEMENT_10
    )
    assert result.movement_remaining == _MOVEMENT_20


def test_deduct_movement_full_amount_leaves_zero() -> None:
    result = TurnResources(movement_remaining=_SPEED_30).deduct("movement", _SPEED_30)
    assert result.movement_remaining == 0


def test_deduct_movement_exceeds_remaining_raises_resource_unavailable() -> None:
    with pytest.raises(ResourceUnavailableError):
        TurnResources(movement_remaining=_SPEED_30).deduct("movement", _MOVEMENT_31)


def test_deduct_movement_does_not_affect_other_resources() -> None:
    result = TurnResources(movement_remaining=_SPEED_30).deduct(
        "movement", _MOVEMENT_10
    )
    assert result.action_available is True
    assert result.bonus_action_available is True
    assert result.reaction_available is True


# ---------------------------------------------------------------------------
# Unknown resource type
# ---------------------------------------------------------------------------


def test_deduct_unknown_resource_type_raises_value_error() -> None:
    with pytest.raises(ValueError, match="unknown resource_type"):
        TurnResources().deduct("fly")


# ---------------------------------------------------------------------------
# Independence
# ---------------------------------------------------------------------------


def test_deduct_action_does_not_affect_bonus_action() -> None:
    result = TurnResources().deduct("action")
    assert result.bonus_action_available is True


def test_deduct_bonus_action_does_not_affect_action() -> None:
    result = TurnResources().deduct("bonus_action")
    assert result.action_available is True
