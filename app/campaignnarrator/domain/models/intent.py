"""Player intent, input, and IO protocol models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, model_validator


class IntentCategory(StrEnum):
    """Player intent categories used by PlayerIntentAgent."""

    HOSTILE_ACTION = "hostile_action"
    SKILL_CHECK = "skill_check"
    NPC_DIALOGUE = "npc_dialogue"
    SCENE_OBSERVATION = "scene_observation"
    SAVE_EXIT = "save_exit"
    STATUS = "status"
    RECAP = "recap"
    LOOK_AROUND = "look_around"


class PlayerIntent(BaseModel):
    """Structured output from PlayerIntentAgent."""

    model_config = ConfigDict(frozen=True)

    category: IntentCategory
    check_hint: str | None = None
    reason: str = ""

    @model_validator(mode="before")
    @classmethod
    def _normalise_ollama_drift(cls, data: object) -> object:
        """Remap field names that local LLMs use instead of the schema fields.

        Ollama models sometimes return the input context echoed back with
        ``phase`` instead of ``category``, and embed the skill name inside
        ``skill_check_parameters.skill`` instead of ``check_hint``.
        """
        if not isinstance(data, dict):
            return data
        # Map 'phase' → 'category' when 'category' is absent.
        if "category" not in data and "phase" in data:
            data = {**data, "category": data["phase"]}
        # Extract nested skill name → check_hint when check_hint is absent.
        if "check_hint" not in data:
            params = data.get("skill_check_parameters")
            if isinstance(params, dict) and "skill" in params:
                data = {**data, "check_hint": params["skill"]}
        return data


@dataclass(frozen=True, slots=True)
class PlayerInput:
    """Raw player input with normalized access for routing."""

    raw_text: str

    @property
    def normalized(self) -> str:
        """Return lowercased text with collapsed internal whitespace."""
        return " ".join(self.raw_text.lower().split())


class PlayerIO(Protocol):
    """Protocol for all player-facing I/O.

    Lives in models so both EncounterOrchestrator and CombatOrchestrator
    can depend on it without circular imports. The terminal implementation is
    created in cli.py and injected downward. Tests inject ScriptedIO.
    """

    def prompt(self, text: str) -> str:
        """Display text and return player input; re-prompts silently on blank."""
        ...

    def prompt_optional(self, text: str) -> str:
        """Display text and return player input; returns blank if the player skips."""
        ...

    def prompt_multiline(self, text: str) -> str:
        """Display text and collect lines until a blank line; returns joined text."""
        ...

    def display(self, text: str) -> None:
        """Display text with no expected input."""
        ...
