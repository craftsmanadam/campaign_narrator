"""Unit tests for the minimal campaign narrator domain models."""

from campaignnarrator.domain.models import (
    Action,
    Adjudication,
    Narration,
    RollRequest,
    RuleReference,
)


def test_roll_request_tracks_owner_visibility_and_expression() -> None:
    """Roll requests should carry the steel-thread ownership constraint."""

    request = RollRequest(
        owner="orchestrator",
        visibility="private",
        expression="1d20+3",
        purpose="stealth check",
    )

    assert request.owner == "orchestrator"
    assert request.visibility == "private"
    assert request.expression == "1d20+3"
    assert request.purpose == "stealth check"


def test_action_adjudication_and_narration_are_plain_dataclasses() -> None:
    """Core domain objects should compose without extra framework behavior."""

    rule = RuleReference(
        path="adjudication/core_resolution.md",
        title="Core Resolution",
    )
    action = Action(
        actor="talia",
        summary="drink a potion",
        rule_references=(rule,),
    )
    adjudication = Adjudication(
        action=action,
        outcome="success",
        roll_request=RollRequest(
            owner="orchestrator",
            visibility="public",
            expression="2d4+2",
        ),
        rule_references=(rule,),
    )
    narration = Narration(text="Talia drinks the potion and steadies herself.")

    assert adjudication.action == action
    assert adjudication.outcome == "success"
    assert adjudication.roll_request.owner == "orchestrator"
    assert adjudication.roll_request.visibility == "public"
    assert narration.text == "Talia drinks the potion and steadies herself."
