"""Minimal domain models for the orchestrator steel thread."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class RuleReference:
    """Reference to a rule source or excerpt."""

    path: str
    title: str | None = None
    excerpt: str | None = None


@dataclass(frozen=True, slots=True)
class Action:
    """A narrated action taken by an actor."""

    actor: str
    summary: str
    rule_references: tuple[RuleReference, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class RollRequest:
    """An explicit request for a dice roll."""

    owner: str
    visibility: str
    expression: str
    purpose: str | None = None


@dataclass(frozen=True, slots=True)
class Adjudication:
    """A decision produced from an action and its supporting rules."""

    action: Action
    outcome: str
    roll_request: RollRequest | None = None
    rule_references: tuple[RuleReference, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class PotionOfHealingResolution:
    """The resolved outcome after the potion roll and state update."""

    roll_total: int
    healing_amount: int
    hp_before: int
    hp_after: int


@dataclass(frozen=True, slots=True)
class Narration:
    """The text that should be spoken to the user."""

    text: str
    audience: str | None = None
