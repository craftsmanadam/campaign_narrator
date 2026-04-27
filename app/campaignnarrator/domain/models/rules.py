"""Rules adjudication models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict

from .encounter_state import EncounterPhase
from .roll import RollRequest


class StateEffect(BaseModel):
    """A structured state mutation produced by rules adjudication."""

    model_config = ConfigDict(frozen=True)

    effect_type: str
    target: str
    value: object = None
    apply_on: Literal["always", "success", "failure"] = "always"


@dataclass(frozen=True, slots=True)
class RulesAdjudicationRequest:
    """Structured request for adjudicating a generic encounter action."""

    actor_id: str
    intent: str
    phase: EncounterPhase
    allowed_outcomes: tuple[str, ...]
    encounter_id: str = ""
    check_hints: tuple[str, ...] = field(default_factory=tuple)
    compendium_context: tuple[str, ...] = field(default_factory=tuple)
    actor_modifiers: Mapping[str, int] = field(default_factory=dict)
    visible_actors_context: tuple[str, ...] = field(default_factory=tuple)


class RulesAdjudication(BaseModel):
    """Structured result from rules resolution."""

    model_config = ConfigDict(frozen=True)

    is_legal: bool
    action_type: str
    summary: str
    reasoning_summary: str = ""
    roll_requests: tuple[RollRequest, ...] = ()
    state_effects: tuple[StateEffect, ...] = ()
    rule_references: tuple[str, ...] = ()


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
class Adjudication:
    """A decision produced from an action and its supporting rules."""

    action: Action
    outcome: str
    roll_request: RollRequest | None = None
    rule_references: tuple[RuleReference, ...] = field(default_factory=tuple)
