"""Integration tests for CharacterCreationOrchestrator class selection flow.

Replaces acceptance/character_creation/class_selection.feature.
Real orchestrator, mocked repos and backstory agent.
No Docker, no WireMock, no live LLM calls.
"""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock

from campaignnarrator.orchestrators.character_creation_orchestrator import (
    CharacterCreationAgents,
    CharacterCreationOrchestrator,
    CharacterCreationRepositories,
)
from campaignnarrator.repositories.narrative_memory_repository import (
    NarrativeMemoryRepository,
)

from tests.fixtures.fighter_talia import TALIA

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_io(inputs: list[str]) -> MagicMock:
    """Build a mock PlayerIO that returns inputs in sequence.

    Both prompt() and prompt_multiline() consume from the same iterator so
    tests do not need to track which call type fires at each step.
    """
    io = MagicMock()
    it = iter(inputs)
    io.prompt.side_effect = lambda _: next(it)
    io.prompt_multiline.side_effect = lambda _: next(it)
    return io


def _make_orchestrator(
    inputs: list[str],
) -> tuple[CharacterCreationOrchestrator, MagicMock]:
    """Build orchestrator with scripted IO and mocked repos."""
    io = _make_io(inputs)
    actor_repo = MagicMock()
    template_repo = MagicMock()
    memory_repo = MagicMock(spec=NarrativeMemoryRepository)
    backstory_agent = MagicMock()

    template_repo.available_classes.return_value = ["fighter", "rogue"]
    template_repo.load.return_value = replace(
        TALIA, name="", race=None, description=None, background=None
    )
    backstory_agent.draft.return_value = "A draft backstory."

    repos = CharacterCreationRepositories(
        actor=actor_repo, template=template_repo, memory=memory_repo
    )
    orch = CharacterCreationOrchestrator(
        io=io,
        repositories=repos,
        agents=CharacterCreationAgents(backstory=backstory_agent),
    )
    return orch, template_repo


# Full input sequence: class, name, race, background, description
_FULL_INPUTS_FIGHTER = [
    "1",
    "Aldric",
    "Human",
    "A former soldier.",
    "Tall with a scar.",
]
_FULL_INPUTS_ROGUE = [
    "rogue",
    "Lyra",
    "Elf",
    "A thief from the docks.",
    "Wiry and quick.",
]


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestClassSelection:
    def test_class_selected_by_number_calls_load_with_fighter(self) -> None:
        """Entering '1' selects the first class (fighter) and loads its template."""
        orch, template_repo = _make_orchestrator(_FULL_INPUTS_FIGHTER)

        actor = orch.run()

        template_repo.load.assert_called_with("fighter")
        assert actor is not None

    def test_class_selected_by_name_calls_load_with_rogue(self) -> None:
        """Typing 'rogue' directly selects the rogue class."""
        orch, template_repo = _make_orchestrator(_FULL_INPUTS_ROGUE)

        orch.run()

        template_repo.load.assert_called_with("rogue")

    def test_invalid_class_reprompts_then_accepts_valid_entry(self) -> None:
        """Out-of-range number and unknown name reprompt; '2' then succeeds."""
        invalid_then_valid = [
            "9",  # out of range
            "wizard",  # not in available classes
            "2",  # valid → rogue
            "Aldric",
            "Human",
            "A soldier.",
            "Wiry.",
        ]
        orch, template_repo = _make_orchestrator(invalid_then_valid)

        actor = orch.run()

        template_repo.load.assert_called_with("rogue")
        assert actor is not None


class TestActorBuilding:
    def test_actor_has_player_chosen_name(self) -> None:
        """The returned ActorState carries the name the player entered."""
        orch, _ = _make_orchestrator(_FULL_INPUTS_FIGHTER)

        actor = orch.run()

        assert actor.name == "Aldric"

    def test_actor_saved_to_repository(self) -> None:
        """actor_repo.save is called once with the final ActorState."""
        io = _make_io(_FULL_INPUTS_FIGHTER)
        actor_repo = MagicMock()
        template_repo = MagicMock()
        memory_repo = MagicMock(spec=NarrativeMemoryRepository)
        backstory_agent = MagicMock()
        template_repo.available_classes.return_value = ["fighter", "rogue"]
        template_repo.load.return_value = replace(
            TALIA, name="", race=None, description=None, background=None
        )

        repos = CharacterCreationRepositories(
            actor=actor_repo, template=template_repo, memory=memory_repo
        )
        orch = CharacterCreationOrchestrator(
            io=io,
            repositories=repos,
            agents=CharacterCreationAgents(backstory=backstory_agent),
        )
        actor = orch.run()

        actor_repo.save.assert_called_once_with(actor)
