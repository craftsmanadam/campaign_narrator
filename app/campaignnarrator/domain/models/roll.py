"""Dice roll request and result models."""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator

from campaignnarrator.tools.dice import roll as _roll

from .actor_state import ActorState, _ability_modifier


class RollVisibility(StrEnum):
    """Controls who can see a roll request."""

    PUBLIC = "public"
    HIDDEN = "hidden"


class RollRequest(BaseModel):
    """An explicit request for a dice roll."""

    model_config = ConfigDict(frozen=True)

    owner: str
    visibility: RollVisibility
    expression: str
    purpose: str | None = None
    difficulty_class: int | None = None

    @field_validator("expression")
    @classmethod
    def valid_dice(cls, v: str) -> str:
        # Normalize whitespace around operators (Ollama sometimes adds spaces).
        normalized = re.sub(r"\s*([+-])\s*", r"\1", v.strip())
        # Auto-brace bare known token names (Ollama sometimes omits braces).
        for token in (
            "strength_mod",
            "dexterity_mod",
            "constitution_mod",
            "intelligence_mod",
            "wisdom_mod",
            "charisma_mod",
            "proficiency_bonus",
            "level",
        ):
            normalized = re.sub(
                rf"(?<!\{{){re.escape(token)}(?!\}})", f"{{{token}}}", normalized
            )
        if not re.fullmatch(r"\d+d\d+(k[lh]?\d+)?([+-](\d+|\{[a-z_]+\}))*", normalized):
            raise ValueError(f"invalid dice expression: {v!r}")  # noqa: TRY003
        return normalized

    def _resolve_dice_expression(self, actor: ActorState) -> str:
        """Replace {token} placeholders with actor-specific numeric values."""
        token_map = {
            "{strength_mod}": str(_ability_modifier(actor.strength)),
            "{dexterity_mod}": str(_ability_modifier(actor.dexterity)),
            "{constitution_mod}": str(_ability_modifier(actor.constitution)),
            "{intelligence_mod}": str(_ability_modifier(actor.intelligence)),
            "{wisdom_mod}": str(_ability_modifier(actor.wisdom)),
            "{charisma_mod}": str(_ability_modifier(actor.charisma)),
            "{proficiency_bonus}": str(actor.proficiency_bonus),
            "{level}": str(actor.level),
        }
        result = self.expression
        for token, value in token_map.items():
            result = result.replace(token, value)
        return result.replace("+-", "-")

    def roll(self, actor: ActorState) -> RollResult:
        """Resolve expression tokens, roll the dice, and return a RollResult."""
        resolved = self._resolve_dice_expression(actor)
        total = _roll(resolved)
        return RollResult(
            owner=self.owner,
            visibility=self.visibility,
            resolved_expression=resolved,
            purpose=self.purpose,
            difficulty_class=self.difficulty_class,
            roll_total=total,
        )

    def __str__(self) -> str:
        purpose_part = f", purpose={self.purpose!r}" if self.purpose else ""
        dc_part = (
            f", dc={self.difficulty_class}" if self.difficulty_class is not None else ""
        )
        return (
            f"RollRequest(owner={self.owner!r}, expression={self.expression!r}"
            f"{purpose_part}{dc_part})"
        )


class RollResult(BaseModel):
    """The outcome of executing a RollRequest against an ActorState."""

    model_config = ConfigDict(frozen=True)

    owner: str
    visibility: RollVisibility
    resolved_expression: str
    purpose: str | None
    difficulty_class: int | None
    roll_total: int

    def evaluate(self) -> bool:
        """Return True if the roll meets or exceeds the difficulty class.

        Raises ValueError when difficulty_class is not set.
        """
        if self.difficulty_class is None:
            raise ValueError("evaluate() requires difficulty_class to be set")  # noqa: TRY003
        return self.roll_total >= self.difficulty_class

    def __str__(self) -> str:
        label = self.purpose or self.resolved_expression
        base = f"Roll: {label} = {self.roll_total}"
        if self.difficulty_class is not None:
            outcome = (
                "Succeeded" if self.roll_total >= self.difficulty_class else "Failed"
            )
            return f"{base} — {outcome} (DC {self.difficulty_class})"
        return base
