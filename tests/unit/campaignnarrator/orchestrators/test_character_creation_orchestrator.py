"""Unit tests for CharacterCreationOrchestrator."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock

from campaignnarrator.orchestrators.character_creation_orchestrator import (
    CharacterCreationAgents,
    CharacterCreationOrchestrator,
    CharacterCreationRepositories,
)
from campaignnarrator.repositories.memory_repository import MemoryRepository

from tests.fixtures.fighter_talia import TALIA


def _make_io(inputs: list[str]) -> MagicMock:
    """Build a mock PlayerIO that returns inputs in sequence from a shared iterator.

    prompt(), prompt_multiline(), and prompt_optional() all consume from the
    same sequence so that tests don't need to know which call is required vs optional.
    """
    io = MagicMock()
    it = iter(inputs)
    io.prompt.side_effect = lambda _: next(it)
    io.prompt_multiline.side_effect = lambda _: next(it)
    io.prompt_optional.side_effect = lambda _: next(it)
    return io


def _make_orchestrator(
    inputs: list[str],
    *,
    backstory_draft: str = "You served the king.",
    available_classes: list[str] | None = None,
) -> tuple[CharacterCreationOrchestrator, MagicMock, MagicMock]:
    io = _make_io(inputs)
    mock_actor_repo = MagicMock()
    mock_template_repo = MagicMock()
    mock_memory_repo = MagicMock(spec=MemoryRepository)
    mock_backstory_agent = MagicMock()

    mock_template_repo.load.return_value = replace(
        TALIA, name="", race=None, description=None, background=None
    )
    mock_template_repo.available_classes.return_value = (
        available_classes if available_classes is not None else ["fighter", "rogue"]
    )
    mock_backstory_agent.draft.return_value = backstory_draft

    repos = CharacterCreationRepositories(
        actor=mock_actor_repo,
        template=mock_template_repo,
        memory=mock_memory_repo,
    )
    agents = CharacterCreationAgents(backstory=mock_backstory_agent)
    orch = CharacterCreationOrchestrator(io=io, repositories=repos, agents=agents)
    return orch, mock_actor_repo, mock_memory_repo


def test_run_saves_actor_with_name_race_background() -> None:
    """Happy path: player selects class by number, provides all inputs."""
    orch, mock_repo, _ = _make_orchestrator(
        inputs=[
            "1",  # selects fighter (first in menu)
            "Aldric",  # name
            "Human",  # race
            "I served the king's guard for six years.",  # backstory
            "Tall with brown hair and a soldier's bearing.",  # description
        ]
    )
    actor = orch.run()
    assert actor.name == "Aldric"
    assert actor.race == "Human"
    assert actor.background == "I served the king's guard for six years."
    mock_repo.save.assert_called_once()
    saved = mock_repo.save.call_args[0][0]
    assert saved.name == "Aldric"


def test_run_uses_backstory_agent_when_player_requests_help() -> None:
    """When player says 'help', BackstoryAgent drafts the backstory."""
    orch, _, __ = _make_orchestrator(
        inputs=[
            "1",  # selects fighter
            "Aldric",  # name
            "Human",  # race
            "help me write a backstory",  # triggers backstory agent
            "accept",  # accept the draft
            "Tall with brown hair.",  # description
        ],
        backstory_draft="You served the king.",
    )
    actor = orch.run()
    assert actor.background == "You served the king."


def test_run_assigns_actor_id_pc_player() -> None:
    orch, _, __ = _make_orchestrator(
        inputs=["1", "Aldric", "Human", "A former soldier.", "Tall with a scar."]
    )
    actor = orch.run()
    assert actor.actor_id == "pc:player"


def test_run_sets_description_when_provided() -> None:
    orch, _, __ = _make_orchestrator(
        inputs=["1", "Aldric", "Human", "A former soldier.", "Tall with a scar."]
    )
    actor = orch.run()
    assert actor.description == "Tall with a scar."


def test_run_backstory_revision_loop() -> None:
    """Rejected backstory draft becomes new fragments for the next revision."""
    orch, _mock_repo, _ = _make_orchestrator(
        inputs=[
            "1",  # selects fighter
            "Aldric",  # name
            "Human",  # race
            "help",  # triggers backstory agent
            "make it more tragic",  # reject draft — becomes new fragments
            "accept",  # accept revised draft
            "Gaunt with haunted eyes.",  # description
        ],
        backstory_draft="You served the king.",
    )
    actor = orch.run()
    assert actor.background == "You served the king."


def test_description_reprompts_on_blank_and_accepts_second_attempt() -> None:
    """_choose_description must loop until the player provides a non-blank value."""
    io = MagicMock()
    io.prompt.side_effect = [
        "1",  # class menu selection
        "Aldric",  # name
        "Human",  # race
    ]
    io.prompt_multiline.side_effect = [
        "I served the guard.",  # backstory
        "",  # first description attempt — blank
        "Tall with a scar.",  # second description attempt — accepted
    ]

    mock_actor_repo = MagicMock()
    mock_template_repo = MagicMock()
    mock_memory_repo = MagicMock()
    mock_backstory_agent = MagicMock()

    mock_template_repo.load.return_value = replace(
        TALIA, name="", race=None, description=None, background=None
    )
    mock_template_repo.available_classes.return_value = ["fighter", "rogue"]

    repos = CharacterCreationRepositories(
        actor=mock_actor_repo,
        template=mock_template_repo,
        memory=mock_memory_repo,
    )
    agents = CharacterCreationAgents(backstory=mock_backstory_agent)
    orch = CharacterCreationOrchestrator(io=io, repositories=repos, agents=agents)
    actor = orch.run()

    expected_multiline_calls = 3  # backstory + blank attempt + accepted value
    assert io.prompt_multiline.call_count == expected_multiline_calls
    assert actor.description == "Tall with a scar."


def test_choose_class_by_name_selects_correct_class() -> None:
    """Player can type the class name directly instead of a number."""
    orch, _, __ = _make_orchestrator(
        inputs=["rogue", "Aldric", "Human", "A thief.", "Wiry and quick."],
        available_classes=["fighter", "rogue"],
    )
    actor = orch.run()
    assert actor.actor_id == "pc:player"


def test_choose_class_reprompts_on_invalid_input() -> None:
    """Invalid class input causes reprompt; valid number on retry proceeds."""
    orch, _, __ = _make_orchestrator(
        inputs=[
            "9",  # out of range — reprompt
            "wizard",  # not in available classes — reprompt
            "1",  # valid: selects fighter
            "Aldric",
            "Human",
            "A soldier.",
            "Tall.",
        ],
        available_classes=["fighter", "rogue"],
    )
    actor = orch.run()
    assert actor.actor_id == "pc:player"


def test_grouped_run_saves_actor() -> None:
    orch, mock_actor_repo, _ = _make_orchestrator(
        ["1", "Aldric", "Human", "Soldier background.", "Tall and scarred."]
    )
    orch.run()
    mock_actor_repo.save.assert_called_once()


def test_grouped_run_stores_player_background_in_memory() -> None:
    orch, _, mock_memory_repo = _make_orchestrator(
        ["1", "Aldric", "Human", "Soldier background.", "Tall and scarred."]
    )
    orch.run()
    mock_memory_repo.store_narrative.assert_called_once()
    args = mock_memory_repo.store_narrative.call_args
    assert args[0][1]["event_type"] == "player_background"
