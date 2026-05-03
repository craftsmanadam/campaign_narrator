"""Unit tests for state_updates helpers."""

from __future__ import annotations

import pytest
from campaignnarrator.tools.state_updates import require_int


def test_require_int_returns_int_unchanged() -> None:
    expected = 5
    assert require_int(expected, "hp delta") == expected


def test_require_int_raises_type_error_for_non_int() -> None:
    with pytest.raises(TypeError, match="invalid hp delta"):
        require_int("five", "hp delta")
