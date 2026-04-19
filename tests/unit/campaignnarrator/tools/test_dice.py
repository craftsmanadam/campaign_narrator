"""Unit tests for the dice helper."""

from campaignnarrator.tools.dice import roll


def test_dice_wrapper_delegates_to_multi_dice(mocker) -> None:
    """The dice helper should be a thin wrapper over the real dependency."""

    fake_roll = mocker.patch(
        "campaignnarrator.tools.dice.multi_dice.roll",
        return_value=13,
    )

    expected_total = 13

    assert roll("2d6+1") == expected_total
    fake_roll.assert_called_once_with("2d6+1")
