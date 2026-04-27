"""Unit tests for combat domain models."""

from __future__ import annotations

import pytest
from campaignnarrator.domain.models import (
    ActorState,
    ActorType,
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
    actor = ActorState(
        actor_id="pc:talia",
        name="Talia",
        actor_type=ActorType.PC,
        hp_max=44,
        hp_current=44,
        armor_class=20,
        strength=16,
        dexterity=14,
        constitution=16,
        intelligence=10,
        wisdom=12,
        charisma=8,
        proficiency_bonus=3,
        initiative_bonus=5,
        speed=30,
        attacks_per_action=2,
        action_options=(),
        ac_breakdown=(),
    )
    state = EncounterState(
        encounter_id="test",
        phase=EncounterPhase.COMBAT,
        setting="Forest",
        actors={"pc:talia": actor},
    )
    result = CombatResult(
        status=CombatStatus.COMPLETE,
        final_state=state,
        death_saves_remaining=None,
    )
    assert result.status == CombatStatus.COMPLETE
    assert result.death_saves_remaining is None


def test_combat_result_player_down_carries_death_saves() -> None:
    actor = ActorState(
        actor_id="pc:talia",
        name="Talia",
        actor_type=ActorType.PC,
        hp_max=44,
        hp_current=0,
        armor_class=20,
        strength=16,
        dexterity=14,
        constitution=16,
        intelligence=10,
        wisdom=12,
        charisma=8,
        proficiency_bonus=3,
        initiative_bonus=5,
        speed=30,
        attacks_per_action=2,
        action_options=(),
        ac_breakdown=(),
    )
    state = EncounterState(
        encounter_id="test",
        phase=EncounterPhase.COMBAT,
        setting="Forest",
        actors={"pc:talia": actor},
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
