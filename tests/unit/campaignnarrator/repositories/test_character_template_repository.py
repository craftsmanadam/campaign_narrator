"""Unit tests for CharacterTemplateRepository."""

from __future__ import annotations

from pathlib import Path

import pytest
from campaignnarrator.repositories.character_template_repository import (
    CharacterTemplateRepository,
)

TEMPLATE_ROOT = Path(__file__).resolve().parents[4] / "data" / "character_templates"


def test_available_classes_lists_fighter_and_rogue() -> None:
    repo = CharacterTemplateRepository(TEMPLATE_ROOT)
    classes = repo.available_classes()
    assert "fighter" in classes
    assert "rogue" in classes


def test_load_fighter_returns_actor_state_with_correct_stats() -> None:
    repo = CharacterTemplateRepository(TEMPLATE_ROOT)
    actor = repo.load("fighter")
    assert actor.strength == 17  # noqa: PLR2004
    assert actor.dexterity == 14  # noqa: PLR2004
    assert actor.constitution == 14  # noqa: PLR2004
    assert actor.hp_max == 12  # noqa: PLR2004
    assert actor.armor_class == 16  # noqa: PLR2004
    assert actor.proficiency_bonus == 2  # noqa: PLR2004
    assert actor.attacks_per_action == 1


def test_load_rogue_returns_actor_state_with_correct_stats() -> None:
    repo = CharacterTemplateRepository(TEMPLATE_ROOT)
    actor = repo.load("rogue")
    assert actor.dexterity == 17  # noqa: PLR2004
    assert actor.intelligence == 14  # noqa: PLR2004
    assert actor.hp_max == 10  # noqa: PLR2004
    assert actor.armor_class == 14  # noqa: PLR2004


def test_load_template_name_is_empty_string() -> None:
    """Templates leave name as empty string after null replacement."""
    repo = CharacterTemplateRepository(TEMPLATE_ROOT)
    actor = repo.load("fighter")
    assert actor.name == ""


def test_load_unknown_class_raises_file_not_found() -> None:
    repo = CharacterTemplateRepository(TEMPLATE_ROOT)
    with pytest.raises(FileNotFoundError):
        repo.load("wizard")
