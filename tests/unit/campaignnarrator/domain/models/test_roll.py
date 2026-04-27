"""Unit tests for roll domain models."""

from __future__ import annotations

import pytest
from campaignnarrator.domain.models import (
    ActorState,
    ActorType,
    RollRequest,
    RollResult,
    RollVisibility,
)
from pydantic import ValidationError


def _roll_actor(**overrides: object) -> ActorState:
    defaults: dict[str, object] = dict(
        actor_id="pc:test",
        name="Test",
        actor_type=ActorType.PC,
        hp_max=10,
        hp_current=10,
        armor_class=12,
        strength=10,
        dexterity=14,
        constitution=10,
        intelligence=10,
        wisdom=16,
        charisma=8,
        proficiency_bonus=3,
        initiative_bonus=2,
        speed=30,
        attacks_per_action=1,
        action_options=("Attack",),
        ac_breakdown=(),
        level=5,
    )
    defaults.update(overrides)
    return ActorState(**defaults)  # type: ignore[arg-type]


def _make_roll_result(**overrides: object) -> RollResult:
    defaults: dict[str, object] = {
        "owner": "player",
        "visibility": RollVisibility.PUBLIC,
        "resolved_expression": "1d20+3",
        "purpose": None,
        "difficulty_class": None,
        "roll_total": 14,
    }
    defaults.update(overrides)
    return RollResult(**defaults)  # type: ignore[arg-type]


def test_roll_visibility_values_are_public_and_hidden() -> None:
    """Roll visibility enum should expose the expected wire values."""

    assert RollVisibility.PUBLIC.value == "public"
    assert RollVisibility.HIDDEN.value == "hidden"


def test_roll_request_rejects_invalid_dice_expression() -> None:
    with pytest.raises(ValidationError, match="invalid dice expression"):
        RollRequest(owner="player", visibility=RollVisibility.PUBLIC, expression="bad")


def test_roll_request_accepts_valid_dice_expressions() -> None:
    vis = RollVisibility.PUBLIC
    for expr in ("1d20", "2d6+3", "4d6kh3", "1d4-1"):
        req = RollRequest(owner="player", visibility=vis, expression=expr)
        assert req.expression == expr


def test_roll_request_accepts_token_placeholder_expression() -> None:
    """RollRequest must accept expressions with {token} placeholders."""
    req = RollRequest(
        owner="pc:talia",
        visibility=RollVisibility.PUBLIC,
        expression="1d20+{wisdom_mod}+{proficiency_bonus}",
    )
    assert req.expression == "1d20+{wisdom_mod}+{proficiency_bonus}"


def test_roll_request_rejects_symbolic_without_braces() -> None:
    """Bare symbolic names without braces must still be rejected."""
    with pytest.raises(ValidationError):
        RollRequest(
            owner="pc:talia",
            visibility=RollVisibility.PUBLIC,
            expression="d20 + wisdom_modifier",
        )


def test_roll_request_normalizes_spaces_around_operators() -> None:
    """Spaces around + or - (common Ollama output) are stripped and accepted."""
    req = RollRequest(
        owner="pc:talia",
        visibility=RollVisibility.PUBLIC,
        expression="1d20 + {wisdom_mod} + {proficiency_bonus}",
    )
    assert req.expression == "1d20+{wisdom_mod}+{proficiency_bonus}"


def test_roll_request_auto_braces_bare_known_tokens() -> None:
    """Bare known token names (Ollama omits braces) are auto-braced and accepted."""
    req = RollRequest(
        owner="pc:talia",
        visibility=RollVisibility.PUBLIC,
        expression="1d20+charisma_mod+proficiency_bonus",
    )
    assert req.expression == "1d20+{charisma_mod}+{proficiency_bonus}"


def test_roll_request_normalizes_spaces_and_bare_tokens_together() -> None:
    """Combined spaces + missing braces are both fixed in one pass."""
    req = RollRequest(
        owner="pc:talia",
        visibility=RollVisibility.PUBLIC,
        expression="1d20 + wisdom_mod",
    )
    assert req.expression == "1d20+{wisdom_mod}"


def test_roll_request_difficulty_class_defaults_to_none() -> None:
    req = RollRequest(
        owner="player", visibility=RollVisibility.PUBLIC, expression="1d20"
    )
    assert req.difficulty_class is None


def test_roll_request_accepts_difficulty_class() -> None:
    req = RollRequest(
        owner="player",
        visibility=RollVisibility.PUBLIC,
        expression="1d20+3",
        difficulty_class=15,
    )
    assert req.difficulty_class == 15  # noqa: PLR2004


def test_roll_request_roll_resolves_tokens_and_returns_result(
    mocker: object,
) -> None:
    """roll() substitutes actor tokens, calls _roll, and returns a RollResult."""
    mocker.patch("campaignnarrator.domain.models.roll._roll", return_value=14)
    actor = _roll_actor(wisdom=16, proficiency_bonus=3)
    req = RollRequest(
        owner="player",
        visibility=RollVisibility.PUBLIC,
        expression="1d20+{wisdom_mod}+{proficiency_bonus}",
        purpose="Insight check",
    )
    result = req.roll(actor)
    assert result.roll_total == 14  # noqa: PLR2004
    assert result.resolved_expression == "1d20+3+3"
    assert result.purpose == "Insight check"
    assert result.owner == "player"
    assert result.visibility is RollVisibility.PUBLIC
    assert result.difficulty_class is None


def test_roll_request_roll_negative_modifier_collapses_sign(
    mocker: object,
) -> None:
    """Negative modifier produces 1d20-2 not 1d20+-2."""
    mocker.patch("campaignnarrator.domain.models.roll._roll", return_value=5)
    actor = _roll_actor(charisma=6)
    req = RollRequest(
        owner="player",
        visibility=RollVisibility.PUBLIC,
        expression="1d20+{charisma_mod}",
    )
    result = req.roll(actor)
    assert result.resolved_expression == "1d20-2"


def test_roll_request_roll_carries_difficulty_class(
    mocker: object,
) -> None:
    """RollResult carries difficulty_class from the request."""
    mocker.patch("campaignnarrator.domain.models.roll._roll", return_value=7)
    actor = _roll_actor()
    req = RollRequest(
        owner="player",
        visibility=RollVisibility.PUBLIC,
        expression="1d20",
        difficulty_class=15,
    )
    result = req.roll(actor)
    assert result.difficulty_class == 15  # noqa: PLR2004
    assert result.roll_total == 7  # noqa: PLR2004


def test_roll_request_roll_calls_roll_with_resolved_expression(
    mocker: object,
) -> None:
    """roll() passes the resolved (token-substituted) expression to _roll."""
    mock_roll = mocker.patch("campaignnarrator.domain.models.roll._roll", return_value=10)
    actor = _roll_actor(wisdom=16, proficiency_bonus=3)
    req = RollRequest(
        owner="player",
        visibility=RollVisibility.PUBLIC,
        expression="1d20+{wisdom_mod}+{proficiency_bonus}",
    )
    req.roll(actor)
    mock_roll.assert_called_once_with("1d20+3+3")


def test_roll_result_str_no_purpose_uses_resolved_expression() -> None:
    result = _make_roll_result(resolved_expression="1d20+3", roll_total=7)
    assert str(result) == "Roll: 1d20+3 = 7"


def test_roll_result_str_uses_purpose_over_resolved_expression() -> None:
    result = _make_roll_result(
        resolved_expression="1d20+3", purpose="Insight check", roll_total=14
    )
    assert str(result) == "Roll: Insight check = 14"


def test_roll_result_str_success_with_dc() -> None:
    result = _make_roll_result(
        purpose="Investigation check", roll_total=17, difficulty_class=15
    )
    assert str(result) == "Roll: Investigation check = 17 — Succeeded (DC 15)"


def test_roll_result_str_failure_with_dc() -> None:
    result = _make_roll_result(
        purpose="Investigation check", roll_total=3, difficulty_class=15
    )
    assert str(result) == "Roll: Investigation check = 3 — Failed (DC 15)"


def test_roll_result_str_exactly_dc_is_success() -> None:
    """Exactly meeting the DC is a success (>=)."""
    result = _make_roll_result(roll_total=15, difficulty_class=15)
    assert "Succeeded" in str(result)


def test_roll_result_str_no_dc_has_no_outcome_label() -> None:
    result = _make_roll_result(roll_total=12, difficulty_class=None)
    assert "DC" not in str(result)
    assert "Succeeded" not in str(result)
    assert "Failed" not in str(result)


def test_roll_result_evaluate_success() -> None:
    result = _make_roll_result(roll_total=17, difficulty_class=15)
    assert result.evaluate() is True


def test_roll_result_evaluate_failure() -> None:
    result = _make_roll_result(roll_total=3, difficulty_class=15)
    assert result.evaluate() is False


def test_roll_result_evaluate_exactly_dc_succeeds() -> None:
    result = _make_roll_result(roll_total=15, difficulty_class=15)
    assert result.evaluate() is True


def test_roll_result_evaluate_raises_when_no_dc() -> None:
    result = _make_roll_result(difficulty_class=None)
    with pytest.raises(ValueError, match="difficulty_class"):
        result.evaluate()


def test_roll_result_is_frozen() -> None:
    result = _make_roll_result()
    with pytest.raises(ValidationError):
        result.roll_total = 99  # type: ignore[misc]
