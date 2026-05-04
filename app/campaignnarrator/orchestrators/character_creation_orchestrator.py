"""Orchestrator for new character creation."""

from __future__ import annotations

from dataclasses import dataclass

from campaignnarrator.agents.backstory_agent import BackstoryAgent
from campaignnarrator.domain.models import ActorState, PlayerIO
from campaignnarrator.repositories.character_template_repository import (
    CharacterTemplateRepository,
)
from campaignnarrator.repositories.narrative_memory_repository import (
    NarrativeMemoryRepository,
)
from campaignnarrator.repositories.player_repository import PlayerRepository

_HELP_TRIGGERS = {"help", "help me", "assist", "write it for me", "help me write"}
_ACCEPT_TRIGGERS = {"accept", "yes", "ok", "looks good", "perfect", "use it"}


@dataclass(frozen=True)
class CharacterCreationRepositories:
    """All repositories required by CharacterCreationOrchestrator."""

    actor: PlayerRepository
    template: CharacterTemplateRepository
    memory: NarrativeMemoryRepository


@dataclass(frozen=True)
class CharacterCreationAgents:
    """All agents required by CharacterCreationOrchestrator."""

    backstory: BackstoryAgent


class CharacterCreationOrchestrator:
    """Guide the player through character creation and persist the result."""

    def __init__(
        self,
        *,
        io: PlayerIO,
        repositories: CharacterCreationRepositories,
        agents: CharacterCreationAgents,
    ) -> None:
        self._io = io
        self._repos = repositories
        self._agents = agents

    def run(self) -> ActorState:
        """Walk through all creation steps and return the saved ActorState."""
        class_name = self._choose_class()
        template = self._repos.template.load(class_name)
        name = self._choose_name()
        race = self._choose_race()
        background = self._choose_background(
            character_name=name, race=race, class_name=class_name
        )
        description = self._choose_description()

        actor = (
            template.with_actor_id("pc:player")
            .with_name(name)
            .with_race(race)
            .with_background(background)
            .with_description(description or None)
        )
        self._repos.actor.save(actor)

        # Write player background to narrative memory for cross-encounter consistency
        narrative = (
            f"{name} is a {race} {class_name}. "
            f"Background: {background}. "
            f"Appearance: {description or 'undescribed'}."
        )
        self._repos.memory.store_narrative(
            narrative,
            {"event_type": "player_background", "campaign_id": ""},
        )

        return actor

    def _choose_class(self) -> str:
        classes = list(self._repos.template.available_classes())
        menu = "\n".join(f"  {i + 1}. {name}" for i, name in enumerate(classes))
        self._io.display(f"\nPlease choose a class:\n{menu}\n")
        while True:
            raw = self._io.prompt("> ").strip().lower()
            if raw.isdigit():
                idx = int(raw) - 1
                if 0 <= idx < len(classes):
                    return classes[idx]
            elif raw in classes:
                return raw
            self._io.display("Invalid choice, please try again.\n")

    def _choose_name(self) -> str:
        self._io.display("\nWhat are you called?\n")
        return self._io.prompt("> ").strip()

    def _choose_race(self) -> str:
        self._io.display(
            "\nWhat is your heritage? (Human, Elf, Dwarf, Halfling, Half-Elf, "
            "Half-Orc, Gnome, Dragonborn, Tiefling)\n"
        )
        return self._io.prompt("> ").strip()

    def _choose_background(
        self, *, character_name: str, race: str, class_name: str
    ) -> str:
        self._io.display(
            "\nDescribe your past in your own words. "
            "You can paste multiple lines — press Enter twice when done. "
            "If you would like help crafting a backstory, just say 'help'.\n"
        )
        raw = self._io.prompt_multiline("> ").strip()
        raw_lower = raw.lower()
        if raw_lower in _HELP_TRIGGERS or any(t in raw_lower for t in _HELP_TRIGGERS):
            return self._draft_backstory_with_help(
                character_name=character_name, race=race, class_name=class_name
            )
        return raw

    def _draft_backstory_with_help(
        self, *, character_name: str, race: str, class_name: str
    ) -> str:
        fragments = f"{character_name}, a {race} {class_name}"
        draft = ""
        for _ in range(3):
            draft = self._agents.backstory.draft(
                fragments=fragments,
                character_name=character_name,
                race=race,
                class_name=class_name,
            )
            self._io.display(f"\n{draft}\n")
            self._io.display("\nAccept this backstory, or describe changes?\n")
            response = self._io.prompt("> ").strip().lower()
            if response in _ACCEPT_TRIGGERS:
                return draft
            fragments = response
        return draft

    def _choose_description(self) -> str:
        self._io.display(
            "\nDescribe your appearance. "
            "You can write as much as you like — press Enter twice when done.\n"
        )
        while True:
            result = self._io.prompt_multiline("> ").strip()
            if result:
                return result
