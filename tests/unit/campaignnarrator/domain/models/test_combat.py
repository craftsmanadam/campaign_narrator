"""Unit tests for combat domain models."""

from __future__ import annotations

import pytest
from campaignnarrator.domain.models import (
    CombatAssessment,
    CombatIntent,
    CombatOutcome,
    CombatResult,
    CombatStatus,
    EncounterPhase,
    EncounterState,
)
from pydantic import ValidationError


def test_combat_status_has_expected_values() -> None:
    assert CombatStatus.COMPLETE == "complete"
    assert CombatStatus.PLAYER_DOWN_NO_ALLIES == "player_down_no_allies"


def test_combat_result_carries_final_state_and_status() -> None:
    state = EncounterState(
        encounter_id="test",
        phase=EncounterPhase.COMBAT,
        setting="Forest",
        actor_ids=("pc:talia",),
        player_actor_id="pc:talia",
    )
    result = CombatResult(
        status=CombatStatus.COMPLETE,
        final_state=state,
        death_saves_remaining=None,
    )
    assert result.status == CombatStatus.COMPLETE
    assert result.death_saves_remaining is None


def test_combat_result_player_down_carries_death_saves() -> None:
    state = EncounterState(
        encounter_id="test",
        phase=EncounterPhase.COMBAT,
        setting="Forest",
        actor_ids=("pc:talia",),
        player_actor_id="pc:talia",
    )
    result = CombatResult(
        status=CombatStatus.PLAYER_DOWN_NO_ALLIES,
        final_state=state,
        death_saves_remaining=2,
    )
    assert result.death_saves_remaining == 2  # noqa: PLR2004


def test_combat_intent_accepts_valid_literals() -> None:
    for val in ("end_turn", "query_status", "exit_session", "combat_action"):
        assert CombatIntent(intent=val).intent == val


def test_combat_intent_rejects_invalid_literal() -> None:
    with pytest.raises(ValidationError):
        CombatIntent(intent="fly_away")


def test_combat_outcome_stores_short_and_full_description() -> None:
    outcome = CombatOutcome(
        short_description="Goblins defeated",
        full_description=(
            "With a final blow, Talia drives the last goblin back into the forest."
        ),
    )
    assert outcome.short_description == "Goblins defeated"
    assert outcome.full_description == (
        "With a final blow, Talia drives the last goblin back into the forest."
    )


def test_combat_assessment_active_has_no_outcome() -> None:
    assessment = CombatAssessment(combat_active=True, outcome=None)
    assert assessment.combat_active is True
    assert assessment.outcome is None


def test_combat_assessment_inactive_has_populated_outcome() -> None:
    outcome = CombatOutcome(
        short_description="Victory",
        full_description="The goblins flee in terror.",
    )
    assessment = CombatAssessment(combat_active=False, outcome=outcome)
    assert assessment.combat_active is False
    assert assessment.outcome is not None
    assert assessment.outcome.short_description == "Victory"
