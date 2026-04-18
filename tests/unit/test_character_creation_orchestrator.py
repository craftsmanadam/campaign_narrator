"""Unit tests for CharacterCreationOrchestrator."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock

from campaignnarrator.orchestrators.character_creation_orchestrator import (
    CharacterCreationOrchestrator,
)

from tests.fixtures.fighter_talia import TALIA


def _make_io(inputs: list[str]) -> MagicMock:
    """Build a mock PlayerIO that returns inputs in sequence."""
    io = MagicMock()
    io.prompt.side_effect = inputs
    return io


def _make_orchestrator(
    inputs: list[str],
    *,
    class_choice: str = "fighter",
    backstory_draft: str = "You served the king.",
) -> tuple[CharacterCreationOrchestrator, MagicMock, MagicMock]:
    io = _make_io(inputs)
    mock_actor_repo = MagicMock()
    mock_template_repo = MagicMock()
    mock_class_agent = MagicMock()
    mock_backstory_agent = MagicMock()

    # Fighter template stub: name="" and no race/description/background
    mock_template_repo.load.return_value = replace(
        TALIA, name="", race=None, description=None, background=None
    )
    mock_class_agent.interpret.return_value = class_choice
    mock_backstory_agent.draft.return_value = backstory_draft

    orch = CharacterCreationOrchestrator(
        io=io,
        actor_repository=mock_actor_repo,
        template_repository=mock_template_repo,
        class_agent=mock_class_agent,
        backstory_agent=mock_backstory_agent,
    )
    return orch, mock_actor_repo, io


def test_run_saves_actor_with_name_race_background() -> None:
    """Happy path: player provides all inputs without requesting backstory help."""
    orch, mock_repo, _ = _make_orchestrator(
        inputs=[
            "I want to be a warrior",  # class choice
            "Aldric",  # name
            "Human",  # race
            "I served the king's guard for six years.",  # backstory (no help request)
            "",  # description (skip)
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
            "fighter",  # class choice
            "Aldric",  # name
            "Human",  # race
            "help me write a backstory",  # triggers backstory agent
            "accept",  # accept the draft
            "",  # description (skip)
        ],
        backstory_draft="You served the king.",
    )
    actor = orch.run()
    assert actor.background == "You served the king."


def test_run_assigns_actor_id_pc_player() -> None:
    orch, _, __ = _make_orchestrator(
        inputs=["fighter", "Aldric", "Human", "A former soldier.", ""]
    )
    actor = orch.run()
    assert actor.actor_id == "pc:player"


def test_run_sets_description_when_provided() -> None:
    orch, _, __ = _make_orchestrator(
        inputs=["fighter", "Aldric", "Human", "A former soldier.", "Tall with a scar."]
    )
    actor = orch.run()
    assert actor.description == "Tall with a scar."


def test_run_backstory_revision_loop() -> None:
    """Rejected backstory draft becomes new fragments for the next revision."""
    orch, _mock_repo, _ = _make_orchestrator(
        inputs=[
            "fighter",  # class choice
            "Aldric",  # name
            "Human",  # race
            "help",  # triggers backstory agent
            "make it more tragic",  # reject draft — becomes new fragments
            "accept",  # accept revised draft
            "",  # description (skip)
        ],
        backstory_draft="You served the king.",
    )
    actor = orch.run()
    assert actor.background == "You served the king."
