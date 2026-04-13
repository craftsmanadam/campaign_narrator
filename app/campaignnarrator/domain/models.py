"""Domain models for encounter orchestration and narration."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from types import MappingProxyType
from typing import Mapping


class EncounterPhase(str, Enum):
    """High-level phases for encounter progression."""

    SCENE_OPENING = "scene_opening"
    SOCIAL = "social"
    RULES_RESOLUTION = "rules_resolution"
    COMBAT = "combat"
    ENCOUNTER_COMPLETE = "encounter_complete"


class RollVisibility(str, Enum):
    """Controls who can see a roll request."""

    PUBLIC = "public"
    HIDDEN = "hidden"


@dataclass(frozen=True, slots=True)
class PlayerInput:
    """Raw player input with normalized access for routing."""

    raw_text: str

    @property
    def normalized(self) -> str:
        """Return lowercased text with collapsed internal whitespace."""

        return " ".join(self.raw_text.lower().split())


@dataclass(frozen=True, slots=True)
class ActorState:
    """Visible or hidden actor state in an encounter."""

    actor_id: str
    name: str
    kind: str
    hp_current: int
    hp_max: int
    armor_class: int
    inventory: tuple[str, ...] = field(default_factory=tuple)
    is_visible: bool = True
    conditions: tuple[str, ...] = field(default_factory=tuple)
    character_class: str | None = None
    character_background: str | None = None


@dataclass(frozen=True, slots=True)
class EncounterState:
    """Canonical state for an in-progress encounter."""

    encounter_id: str
    phase: EncounterPhase
    setting: str
    actors: Mapping[str, ActorState]
    public_events: tuple[str, ...] = field(default_factory=tuple)
    hidden_facts: Mapping[str, object] = field(default_factory=dict)
    initiative_order: tuple[str, ...] = field(default_factory=tuple)
    outcome: str | None = None

    def __post_init__(self) -> None:
        """Snapshot mutable mappings so encounter state cannot be mutated externally."""

        object.__setattr__(self, "actors", MappingProxyType(dict(self.actors)))
        object.__setattr__(
            self, "hidden_facts", MappingProxyType(dict(self.hidden_facts))
        )

    @property
    def player_actor_id(self) -> str:
        """Return the first player character actor in insertion order."""

        for actor in self.actors.values():
            if actor.kind == "pc":
                return actor.actor_id
        raise ValueError("missing player actor")  # noqa: TRY003

    def visible_actor_names(self) -> tuple[str, ...]:
        """Return visible actor names in encounter insertion order."""

        return tuple(actor.name for actor in self.actors.values() if actor.is_visible)

    def with_phase(self, phase: EncounterPhase) -> "EncounterState":
        """Return a copy of the state with an updated phase."""

        return replace(self, phase=phase)


@dataclass(frozen=True, slots=True)
class OrchestrationDecision:
    """Structured output from the orchestrator."""

    next_step: str
    next_actor: str | None
    requires_rules_resolution: bool
    recommended_check: str | None
    phase_transition: str | None
    player_prompt: str | None
    reason_summary: str


@dataclass(frozen=True, slots=True)
class RollRequest:
    """An explicit request for a dice roll."""

    owner: str
    visibility: RollVisibility
    expression: str
    purpose: str | None = None


@dataclass(frozen=True, slots=True)
class StateEffect:
    """A structured state mutation produced by rules adjudication."""

    effect_type: str
    target: str
    value: object


@dataclass(frozen=True, slots=True)
class RulesAdjudicationRequest:
    """Structured request for adjudicating a generic encounter action."""

    actor_id: str
    intent: str
    phase: EncounterPhase
    allowed_outcomes: tuple[str, ...]
    check_hints: tuple[str, ...] = field(default_factory=tuple)
    compendium_context: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class RulesAdjudication:
    """Structured result from rules resolution."""

    is_legal: bool
    action_type: str
    summary: str
    roll_requests: tuple[RollRequest, ...] = field(default_factory=tuple)
    state_effects: tuple[StateEffect, ...] = field(default_factory=tuple)
    rule_references: tuple[str, ...] = field(default_factory=tuple)
    reasoning_summary: str = ""


@dataclass(frozen=True, slots=True)
class NarrationFrame:
    """Public context that can be narrated to the player."""

    purpose: str
    phase: EncounterPhase
    setting: str
    public_actor_summaries: tuple[str, ...]
    visible_npc_summaries: tuple[str, ...]
    recent_public_events: tuple[str, ...]
    resolved_outcomes: tuple[str, ...]
    allowed_disclosures: tuple[str, ...]
    tone_guidance: str | None = None
    compendium_context: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class Narration:
    """The text that should be spoken to the user."""

    text: str
    audience: str | None = None


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


__all__ = [
    "Action",
    "ActorState",
    "Adjudication",
    "EncounterPhase",
    "EncounterState",
    "Narration",
    "NarrationFrame",
    "OrchestrationDecision",
    "PlayerInput",
    "RollRequest",
    "RollVisibility",
    "RuleReference",
    "RulesAdjudication",
    "RulesAdjudicationRequest",
    "StateEffect",
]
