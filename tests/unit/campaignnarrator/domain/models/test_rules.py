"""Unit tests for rules domain models."""

from __future__ import annotations

import pytest
from campaignnarrator.domain.models import (
    EncounterPhase,
    RollRequest,
    RollVisibility,
    RulesAdjudication,
    RulesAdjudicationRequest,
    StateEffect,
)
from pydantic import ValidationError


def test_rules_adjudication_carries_rolls_and_state_effects() -> None:
    """Rules adjudication should include checks, effects, and rule refs."""

    roll_request = RollRequest(
        owner="player",
        visibility=RollVisibility.PUBLIC,
        expression="1d20+2",
        purpose="Persuasion check",
    )
    effect = StateEffect(
        effect_type="set_encounter_outcome",
        target="encounter:goblin-camp",
        value="de-escalated",
    )
    request = RulesAdjudicationRequest(
        actor_id="pc:talia",
        intent="persuade the scout",
        phase=EncounterPhase.SOCIAL,
        allowed_outcomes=("de-escalated", "hostile"),
        check_hints=("social_check",),
        compendium_context=("goblins",),
    )
    adjudication = RulesAdjudication(
        is_legal=True,
        action_type="social_check",
        summary="Talia attempts to talk the scout down.",
        roll_requests=(roll_request,),
        state_effects=(effect,),
        rule_references=("rules/social/persuasion.md",),
        reasoning_summary="A public persuasion roll resolves the scene.",
    )

    assert request.actor_id == "pc:talia"
    assert request.intent == "persuade the scout"
    assert request.phase is EncounterPhase.SOCIAL
    assert request.allowed_outcomes == ("de-escalated", "hostile")
    assert request.check_hints == ("social_check",)
    assert request.compendium_context == ("goblins",)
    assert adjudication.is_legal is True
    assert adjudication.action_type == "social_check"
    assert adjudication.roll_requests == (roll_request,)
    assert adjudication.state_effects == (effect,)
    assert adjudication.rule_references == ("rules/social/persuasion.md",)
    assert adjudication.reasoning_summary == (
        "A public persuasion roll resolves the scene."
    )


def test_state_effect_apply_on_defaults_to_always() -> None:
    effect = StateEffect(effect_type="add_condition", target="pc:talia", value="hidden")
    assert effect.apply_on == "always"


def test_state_effect_apply_on_accepts_success_and_failure() -> None:
    success_effect = StateEffect(
        effect_type="add_condition",
        target="pc:talia",
        value="hidden",
        apply_on="success",
    )
    failure_effect = StateEffect(
        effect_type="add_condition",
        target="pc:talia",
        value="poisoned",
        apply_on="failure",
    )
    assert success_effect.apply_on == "success"
    assert failure_effect.apply_on == "failure"


def test_state_effect_apply_on_rejects_invalid_value() -> None:
    with pytest.raises(ValidationError):
        StateEffect(
            effect_type="add_condition",
            target="pc:talia",
            value="hidden",
            apply_on="maybe",
        )


def test_rules_adjudication_defaults_to_empty_tuples() -> None:
    adj = RulesAdjudication(is_legal=True, action_type="attack", summary="ok")
    assert adj.roll_requests == ()
    assert adj.state_effects == ()
    assert adj.rule_references == ()
    assert adj.reasoning_summary == ""


def test_rules_adjudication_accepts_nested_models() -> None:
    adj = RulesAdjudication(
        is_legal=True,
        action_type="attack",
        summary="ok",
        roll_requests=(
            RollRequest(
                owner="player", visibility=RollVisibility.PUBLIC, expression="1d20"
            ),
        ),
        state_effects=(
            StateEffect(effect_type="damage", target="npc:goblin-1", value=-5),
        ),
        rule_references=("PHB p.192",),
    )
    assert len(adj.roll_requests) == 1
    assert len(adj.state_effects) == 1
