"""Orchestrator for new character creation."""

from __future__ import annotations

from dataclasses import replace

from campaignnarrator.agents.backstory_agent import BackstoryAgent
from campaignnarrator.agents.character_interpreter_agent import (
    CharacterInterpreterAgent,
)
from campaignnarrator.domain.models import ActorState, PlayerIO
from campaignnarrator.repositories.actor_repository import ActorRepository
from campaignnarrator.repositories.character_template_repository import (
    CharacterTemplateRepository,
)

_HELP_TRIGGERS = {"help", "help me", "assist", "write it for me", "help me write"}
_ACCEPT_TRIGGERS = {"accept", "yes", "ok", "looks good", "perfect", "use it"}


class CharacterCreationOrchestrator:
    """Guide the player through character creation and persist the result."""

    def __init__(
        self,
        *,
        io: PlayerIO,
        actor_repository: ActorRepository,
        template_repository: CharacterTemplateRepository,
        class_agent: CharacterInterpreterAgent,
        backstory_agent: BackstoryAgent,
    ) -> None:
        self._io = io
        self._actor_repo = actor_repository
        self._template_repo = template_repository
        self._class_agent = class_agent
        self._backstory_agent = backstory_agent

    def run(self) -> ActorState:
        """Walk through all creation steps and return the saved ActorState."""
        class_name = self._choose_class()
        template = self._template_repo.load(class_name)
        name = self._choose_name()
        race = self._choose_race()
        background = self._choose_background(
            character_name=name, race=race, class_name=class_name
        )
        description = self._choose_description()

        actor = replace(
            template,
            actor_id="pc:player",
            name=name,
            race=race,
            background=background,
            description=description or None,
        )
        self._actor_repo.save(actor)
        return actor

    def _choose_class(self) -> str:
        self._io.display(
            "\nBefore your story begins, tell me — are you a warrior who meets "
            "challenges head-on, or a shadow who moves unseen?\n"
        )
        raw = self._io.prompt("> ")
        return self._class_agent.interpret(raw)

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
            "If you would like help crafting a backstory, just say 'help'.\n"
        )
        raw = self._io.prompt("> ").strip()

        raw_lower = raw.lower()
        if raw_lower in _HELP_TRIGGERS or any(t in raw_lower for t in _HELP_TRIGGERS):
            return self._draft_backstory_with_help(
                character_name=character_name, race=race, class_name=class_name
            )
        return raw

    def _draft_backstory_with_help(
        self, *, character_name: str, race: str, class_name: str
    ) -> str:
        # Draft immediately from known character context; no extra prompt needed.
        fragments = f"{character_name}, a {race} {class_name}"

        draft = ""
        for _ in range(3):
            draft = self._backstory_agent.draft(
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
            fragments = response  # treat response as revised fragments

        return draft  # use final draft if max iterations reached

    def _choose_description(self) -> str:
        self._io.display("\nDescribe your appearance (or press Enter to skip).\n")
        return self._io.prompt("> ").strip()
