"""Domain models for encounter orchestration and narration."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from enum import Enum, StrEnum
from types import MappingProxyType
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, field_validator


class EncounterPhase(StrEnum):
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


class ActorType(str, Enum):
    """Distinguishes player characters, NPCs, and allied NPCs."""

    PC = "pc"
    NPC = "npc"
    ALLY = "ally"


class RecoveryPeriod(str, Enum):
    """When a resource or item charge replenishes."""

    TURN = "turn"  # resets at start of actor's turn
    SHORT_REST = "short_rest"
    LONG_REST = "long_rest"
    DAY = "day"  # items only — "regains charges at dawn"


@dataclass(frozen=True, slots=True)
class Milestone:
    """A campaign story anchor point. Narrator-only — never shown to the player."""

    milestone_id: str
    title: str
    description: str
    completed: bool = False


@dataclass(frozen=True, slots=True)
class CampaignState:
    """Top-level campaign definition.

    Narrator-only fields must never appear in player-facing prompts.
    """

    campaign_id: str
    name: str
    setting: str
    narrator_personality: str
    # --- Narrator-only fields (never send to player-facing prompts) ---
    hidden_goal: str
    bbeg_name: str
    bbeg_description: str
    milestones: tuple[Milestone, ...]
    # --- Progress tracking ---
    current_milestone_index: int
    starting_level: int
    target_level: int
    # --- Player inputs ---
    player_brief: str
    player_actor_id: str
    bbeg_actor_id: str | None = None


@dataclass(frozen=True, slots=True)
class ModuleState:
    """One story arc within a campaign. Generated lazily as play progresses."""

    module_id: str
    campaign_id: str
    title: str
    summary: str
    guiding_milestone_id: str
    encounters: tuple[str, ...]
    current_encounter_index: int
    completed: bool = False


@dataclass(frozen=True, slots=True)
class CampaignEvent:
    """A summarised story event appended to the campaign event log."""

    campaign_id: str
    # encounter_completed | milestone_reached | notable_moment
    # player_downed | npc_death | module_completed
    event_type: str
    summary: str  # narrator-written, 1-3 sentences
    timestamp: str  # ISO 8601
    module_id: str | None = None
    encounter_id: str | None = None


@dataclass(frozen=True, slots=True)
class FeatState:
    """A feat carried by an actor, with LLM-readable effect text."""

    name: str
    effect_summary: str  # Injected verbatim into Rules Agent context
    reference: str | None  # e.g. "DND.SRD.Wiki-0.5.2/Feats.md#Alert"
    per_turn_uses: int | None  # None = passive; int = resource reset each turn


@dataclass(frozen=True, slots=True)
class WeaponState:
    """A weapon with fully pre-computed attack and damage values."""

    name: str
    attack_bonus: int  # proficiency + ability mod (+ magic if any)
    damage_dice: str  # e.g. "1d8", "2d6"
    damage_bonus: int  # ability mod (+ magic if any)
    damage_type: str  # "slashing", "piercing", "bludgeoning", etc.
    properties: tuple[str, ...]  # e.g. ("versatile (1d10)", "finesse")


@dataclass(frozen=True, slots=True)
class InitiativeTurn:
    """One slot in the initiative order: who acts and what they rolled."""

    actor_id: str
    initiative_roll: int


@dataclass(frozen=True, slots=True)
class ResourceState:
    """A character class resource with current/max tracking and recovery metadata."""

    resource: str  # e.g. "second_wind", "action_surge"
    current: int
    max: int
    recovers_after: RecoveryPeriod
    reference: str | None = None  # e.g. "class_features.json#second-wind"


@dataclass(frozen=True, slots=True)
class InventoryItem:
    """A physical item carried by an actor."""

    item_id: str  # unique within actor inventory, e.g. "potion-1", "rope-1"
    item: str  # display name
    count: int
    charges: int | None = None  # current charges (e.g. wand)
    max_charges: int | None = None
    recovers_after: RecoveryPeriod | None = None  # None for consumables/mundane items
    reference: str | None = None  # None for narrative-only items


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
    """Full D&D 2024 character-sheet-equivalent actor state for an encounter."""

    # --- Identity ---
    actor_id: str
    name: str
    actor_type: ActorType

    # --- Core combat stats ---
    hp_max: int
    hp_current: int
    armor_class: int

    # --- Ability scores ---
    strength: int
    dexterity: int
    constitution: int
    intelligence: int
    wisdom: int
    charisma: int

    # --- Derived stats ---
    proficiency_bonus: int
    initiative_bonus: int  # DEX mod + feat bonuses (e.g. Alert); pre-computed
    speed: int  # feet per turn
    attacks_per_action: int

    # --- Action economy options ---
    action_options: tuple[str, ...]

    # --- AC breakdown ---
    ac_breakdown: tuple[str, ...]

    # --- Saving throws: tuple of (ability_name, total_bonus) ---
    saving_throws: tuple[tuple[str, int], ...] = field(default_factory=tuple)

    # --- Temporary HP ---
    hp_temp: int = 0

    # --- Resources: structured per-character ability tracking ---
    resources: tuple[ResourceState, ...] = field(default_factory=tuple)

    # --- Inventory: physical items carried ---
    inventory: tuple[InventoryItem, ...] = field(default_factory=tuple)

    # --- Bonus and reaction action economy ---
    bonus_action_options: tuple[str, ...] = field(default_factory=tuple)
    reaction_options: tuple[str, ...] = field(default_factory=tuple)

    # --- Weapons and feats ---
    equipped_weapons: tuple[WeaponState, ...] = field(default_factory=tuple)
    feats: tuple[FeatState, ...] = field(default_factory=tuple)

    # --- Defenses ---
    damage_resistances: tuple[str, ...] = field(default_factory=tuple)
    damage_vulnerabilities: tuple[str, ...] = field(default_factory=tuple)
    damage_immunities: tuple[str, ...] = field(default_factory=tuple)
    condition_immunities: tuple[str, ...] = field(default_factory=tuple)

    # --- Current conditions ---
    conditions: tuple[str, ...] = field(default_factory=tuple)

    # --- Death saves (dynamic during encounter) ---
    death_save_successes: int = 0
    death_save_failures: int = 0

    # --- Spellcasting (empty for non-casters) ---
    spell_slots: tuple[tuple[str, int], ...] = field(default_factory=tuple)
    spell_slots_max: tuple[tuple[str, int], ...] = field(default_factory=tuple)
    available_spells: tuple[str, ...] = field(default_factory=tuple)
    concentration: str | None = None

    # --- NPC personality (None for PCs) ---
    personality: str | None = None

    # --- Visibility ---
    is_visible: bool = True

    # --- Character creation fields (persisted) ---
    race: str | None = None
    description: str | None = None  # physical appearance
    background: str | None = None  # backstory text

    # --- Compendium references (transient — populated at load time, not persisted) ---
    references: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class EncounterState:
    """Canonical state for an in-progress encounter."""

    encounter_id: str
    phase: EncounterPhase
    setting: str
    actors: Mapping[str, ActorState]
    public_events: tuple[str, ...] = field(default_factory=tuple)
    hidden_facts: Mapping[str, object] = field(default_factory=dict)
    combat_turns: tuple[InitiativeTurn, ...] = field(default_factory=tuple)
    outcome: str | None = None
    scene_tone: str | None = None

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
            if actor.actor_type == ActorType.PC:
                return actor.actor_id
        raise ValueError("missing player actor")  # noqa: TRY003

    def visible_actor_names(self) -> tuple[str, ...]:
        """Return visible actor names in encounter insertion order."""

        return tuple(actor.name for actor in self.actors.values() if actor.is_visible)

    def with_phase(self, phase: EncounterPhase) -> EncounterState:
        """Return a copy of the state with an updated phase."""

        return replace(self, phase=phase)


@dataclass(frozen=True, slots=True)
class GameState:
    """Top-level game state: player + optional campaign/module/encounter."""

    player: ActorState
    campaign: CampaignState | None = None
    module: ModuleState | None = None
    encounter: EncounterState | None = None


class PlayerIO(Protocol):
    """Protocol for all player-facing I/O.

    Lives in models.py so both EncounterOrchestrator and CombatOrchestrator
    can depend on it without circular imports. The terminal implementation is
    created in cli.py and injected downward. Tests inject ScriptedIO.
    """

    def prompt(self, text: str) -> str:
        """Display text and return player input."""
        ...

    def display(self, text: str) -> None:
        """Display text with no expected input."""
        ...


class CombatStatus(StrEnum):
    """Terminal outcome of a combat encounter from CombatOrchestrator's perspective."""

    COMPLETE = "complete"
    PLAYER_DOWN_NO_ALLIES = "player_down_no_allies"
    SAVED_AND_QUIT = "saved_and_quit"


@dataclass(frozen=True, slots=True)
class TurnResources:
    """Action economy remaining for the actor whose turn is currently active."""

    action_available: bool = True
    bonus_action_available: bool = True
    reaction_available: bool = True
    movement_remaining: int = 0  # feet; initialized from ActorState.speed at turn start


@dataclass(frozen=True, slots=True)
class CombatResult:
    """Returned by CombatOrchestrator to EncounterOrchestrator when combat ends."""

    status: CombatStatus
    final_state: EncounterState
    death_saves_remaining: int | None  # None unless status is PLAYER_DOWN_NO_ALLIES


class CombatOutcome(BaseModel):
    """Compact and rich description of how a combat encounter ended."""

    model_config = ConfigDict(frozen=True)
    short_description: str  # compact, for future encounter logs
    full_description: str  # rich prose shown to player


class CombatAssessment(BaseModel):
    """Narrator's assessment of whether combat should continue."""

    model_config = ConfigDict(frozen=True)
    combat_active: bool
    outcome: CombatOutcome | None  # None when combat_active is True


class CritReview(BaseModel):
    """Narrator's decision on an NPC critical hit against a PC."""

    model_config = ConfigDict(frozen=True)
    approved: bool
    reason: str | None = None  # explanation when approved=False


class OrchestrationDecision(BaseModel):
    """Structured output from the orchestrator."""

    model_config = ConfigDict(frozen=True)

    next_step: str
    next_actor: str | None = None
    requires_rules_resolution: bool
    recommended_check: str | None = None
    phase_transition: str | None = None
    player_prompt: str | None = None
    reason_summary: str


class RollRequest(BaseModel):
    """An explicit request for a dice roll."""

    model_config = ConfigDict(frozen=True)

    owner: str
    visibility: RollVisibility
    expression: str
    purpose: str | None = None

    @field_validator("expression")
    @classmethod
    def valid_dice(cls, v: str) -> str:
        if not re.fullmatch(r"\d+d\d+(k[lh]?\d+)?([+-]\d+)?", v):
            raise ValueError(f"invalid dice expression: {v!r}")  # noqa: TRY003
        return v


class StateEffect(BaseModel):
    """A structured state mutation produced by rules adjudication."""

    model_config = ConfigDict(frozen=True)

    effect_type: str
    target: str
    value: object = None


@dataclass(frozen=True, slots=True)
class RulesAdjudicationRequest:
    """Structured request for adjudicating a generic encounter action."""

    actor_id: str
    intent: str
    phase: EncounterPhase
    allowed_outcomes: tuple[str, ...]
    check_hints: tuple[str, ...] = field(default_factory=tuple)
    compendium_context: tuple[str, ...] = field(default_factory=tuple)


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
    scene_tone: str | None = None


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


class SceneOpeningResponse(BaseModel):
    """Structured LLM output for scene opening narration."""

    model_config = ConfigDict(frozen=True)

    text: str
    scene_tone: str


class CombatIntent(BaseModel):
    """Structured LLM output for a player's declared combat intent."""

    model_config = ConfigDict(frozen=True)

    intent: Literal["end_turn", "query_status", "exit_session", "combat_action"]


__all__ = [
    "Action",
    "ActorState",
    "ActorType",
    "Adjudication",
    "CampaignEvent",
    "CampaignState",
    "CombatAssessment",
    "CombatIntent",
    "CombatOutcome",
    "CombatResult",
    "CombatStatus",
    "CritReview",
    "EncounterPhase",
    "EncounterState",
    "FeatState",
    "GameState",
    "InitiativeTurn",
    "InventoryItem",
    "Milestone",
    "ModuleState",
    "Narration",
    "NarrationFrame",
    "OrchestrationDecision",
    "PlayerIO",
    "PlayerInput",
    "RecoveryPeriod",
    "ResourceState",
    "RollRequest",
    "RollVisibility",
    "RuleReference",
    "RulesAdjudication",
    "RulesAdjudicationRequest",
    "SceneOpeningResponse",
    "StateEffect",
    "TurnResources",
    "WeaponState",
]
