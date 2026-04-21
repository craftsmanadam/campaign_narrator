"""Acceptance tests for CharacterCreationOrchestrator class selection menu.

These tests inject fakes directly — no Docker, no WireMock, no live LLM.
"""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock

import pytest
from campaignnarrator.orchestrators.character_creation_orchestrator import (
    CharacterCreationAgents,
    CharacterCreationOrchestrator,
    CharacterCreationRepositories,
)
from campaignnarrator.repositories.memory_repository import MemoryRepository
from pytest_bdd import given, parsers, scenario, then, when

from tests.fixtures.fighter_talia import TALIA

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_io(inputs: list[str]) -> MagicMock:
    """Build a mock PlayerIO that returns inputs in sequence from a shared iterator.

    Both prompt() and prompt_multiline() consume from the same sequence so tests
    do not need to know which call is issued at each step.
    """
    io = MagicMock()
    it = iter(inputs)
    io.prompt.side_effect = lambda _: next(it)
    io.prompt_multiline.side_effect = lambda _: next(it)
    io.prompt_optional.side_effect = lambda _: next(it)
    return io


def _make_orchestrator(
    inputs: list[str],
) -> tuple[CharacterCreationOrchestrator, MagicMock]:
    """Build a CharacterCreationOrchestrator wired with mock repos and the given inputs."""
    io = _make_io(inputs)
    mock_actor_repo = MagicMock()
    mock_template_repo = MagicMock()
    mock_memory_repo = MagicMock(spec=MemoryRepository)
    mock_backstory_agent = MagicMock()

    mock_template_repo.load.return_value = replace(
        TALIA, name="", race=None, description=None, background=None
    )
    mock_template_repo.available_classes.return_value = ["fighter", "rogue"]
    mock_backstory_agent.draft.return_value = "A draft backstory."

    repos = CharacterCreationRepositories(
        actor=mock_actor_repo,
        template=mock_template_repo,
        memory=mock_memory_repo,
    )
    agents = CharacterCreationAgents(backstory=mock_backstory_agent)
    orch = CharacterCreationOrchestrator(io=io, repositories=repos, agents=agents)
    return orch, mock_template_repo


# ---------------------------------------------------------------------------
# Shared context fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def context() -> dict:
    return {}


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


@scenario(
    "class_selection.feature",
    "Class selection presents a numbered menu and accepts number input",
)
def test_class_selection_by_number() -> None:
    """Player enters '1' and fighter is selected."""


@scenario(
    "class_selection.feature",
    "Class selection accepts class name typed directly",
)
def test_class_selection_by_name() -> None:
    """Player types 'rogue' directly and rogue is selected."""


@scenario(
    "class_selection.feature",
    "Class selection reprompts on invalid input then accepts valid input",
)
def test_class_selection_reprompts_then_accepts() -> None:
    """Player enters invalid inputs twice then a valid choice on third attempt."""


# ---------------------------------------------------------------------------
# Given steps
# ---------------------------------------------------------------------------


@given("available character classes fighter and rogue", target_fixture="class_setup")
def available_classes_fighter_and_rogue(context: dict) -> dict:
    context["available_classes"] = ["fighter", "rogue"]
    return context


# ---------------------------------------------------------------------------
# When steps
# ---------------------------------------------------------------------------


@when(parsers.parse('the player reaches class selection and enters "{entry}"'))
def player_enters_class_selection(
    entry: str,
    class_setup: dict,
    context: dict,
) -> None:
    # Full inputs: class selection + name + race + backstory + description
    inputs = [entry, "Aldric", "Human", "A former soldier.", "Tall with a scar."]
    orch, mock_template_repo = _make_orchestrator(inputs)
    actor = orch.run()
    context["actor"] = actor
    context["template_repo"] = mock_template_repo


@when(parsers.parse('the player enters "9" then "wizard" then "2"'))
def player_enters_invalid_then_valid(
    class_setup: dict,
    context: dict,
) -> None:
    # "9" = out of range; "wizard" = not in available classes; "2" = valid (rogue)
    inputs = [
        "9",
        "wizard",
        "2",
        "Aldric",
        "Human",
        "A soldier who walked away.",
        "Wiry and quick.",
    ]
    orch, mock_template_repo = _make_orchestrator(inputs)
    actor = orch.run()
    context["actor"] = actor
    context["template_repo"] = mock_template_repo


# ---------------------------------------------------------------------------
# Then steps
# ---------------------------------------------------------------------------


@then(parsers.parse("{class_name} is selected as the class"))
def class_is_selected(class_name: str, context: dict) -> None:
    mock_template_repo: MagicMock = context["template_repo"]
    mock_template_repo.load.assert_called_with(class_name)
