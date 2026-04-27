"""Unit tests for the models package exports."""

from __future__ import annotations

from campaignnarrator.domain import models


def test_legacy_potion_resolution_models_are_not_exported() -> None:
    """Legacy potion-specific models should not be exported anymore."""

    assert all("potion" not in name.lower() for name in models.__all__)
