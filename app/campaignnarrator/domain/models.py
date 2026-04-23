"""Domain models for encounter orchestration and narration."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from types import MappingProxyType
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class EncounterPhase(StrEnum):
    """High-level phases for encounter progression."""

    SCENE_OPENING = "scene_opening"
    SOCIAL = "social"
    RULES_RESOLUTION = "rules_resolution"
    COMBAT = "combat"
    ENCOUNTER_COMPLETE = "encounter_complete"


class RollVisibility(StrEnum):
    """Controls who can see a roll request."""

    PUBLIC = "public"
    HIDDEN = "hidden"


class ActorType(StrEnum):
    """Distinguishes player characters, NPCs, and allied NPCs."""

    PC = "pc"
    NPC = "npc"
    ALLY = "ally"


class RecoveryPeriod(StrEnum):
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
    current_module_id: str | None = None


@dataclass(frozen=True, slots=True)
class ModuleState:
    """One story arc within a campaign. Generated lazily as play progresses."""

    module_id: str
    campaign_id: str
    title: str
    summary: str
    guiding_milestone_id: str
    completed_encounter_ids: tuple[str, ...] = ()
    completed_encounter_summaries: tuple[str, ...] = ()
    next_encounter_seed: str | None = None  # deprecated — remove in Plan 4
    completed: bool = False
    planned_encounters: tuple[EncounterTemplate, ...] = ()
    next_encounter_index: int = 0


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
class NpcPresence:
    """Identity anchor for an NPC established in the encounter scene.

    Prevents the narrator from inventing new named characters mid-scene.
    When name_known=False the narrator uses description; when True it uses
    display_name.
    """

    actor_id: str  # FK to EncounterState.actors
    display_name: str  # Canonical name used when name_known=True
    description: str  # Narrative label used when name_known=False ("the innkeeper")
    name_known: bool  # Has the player learned this NPC's name?
    visible: bool  # Is the NPC currently in the scene?


class EncounterNpc(BaseModel):
    """Planning-time NPC definition.

    Single source of truth for ActorState and NpcPresence.
    Supersedes NpcPresenceResult. Assigned by EncounterPlannerAgent at planning time.
    template_npc_id must be unique within a module (not just within an encounter).
    """

    model_config = ConfigDict(frozen=True)

    template_npc_id: str
    display_name: str
    role: str
    description: str
    monster_name: str | None
    stat_source: Literal["monster_compendium", "simple_npc"]
    cr: float
    name_known: bool = False

    @field_validator("cr", mode="before")
    @classmethod
    def _parse_cr(cls, v: object) -> float:
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            if "/" in v:
                num, den = v.split("/")
                return int(num) / int(den)
            return float(v)
        raise ValueError(f"Cannot parse CR: {v!r}")  # noqa: TRY003


class EncounterTemplate(BaseModel):
    """Narrative skeleton for one planned encounter."""

    model_config = ConfigDict(frozen=True)

    template_id: str
    order: int
    setting: str
    purpose: str
    scene_tone: str | None = None
    npcs: tuple[EncounterNpc, ...]
    prerequisites: tuple[str, ...]
    expected_outcomes: tuple[str, ...]
    downstream_dependencies: tuple[str, ...]


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

    # --- Progression ---
    level: int = 1
    class_levels: tuple[tuple[str, int], ...] = field(default_factory=tuple)
    xp: int = 0

    # --- Character creation fields (persisted) ---
    race: str | None = None
    description: str | None = None  # physical appearance
    background: str | None = None  # backstory text

    # --- Compendium references (transient — populated at load time, not persisted) ---
    references: tuple[str, ...] = field(default_factory=tuple)

    # --- Compendium text (transient — populated at load time, not persisted) ---
    compendium_text: str | None = None


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
    npc_presences: tuple[NpcPresence, ...] = field(default_factory=tuple)

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


class NextEncounterPlan(BaseModel):
    """Structured output from NarratorAgent.plan_next_encounter().

    seed: Opening scene description for the next encounter. Used verbatim as
          EncounterState.setting. Ignored when milestone_achieved=True.
    milestone_achieved: True when the module's guiding milestone is narratively
                        complete. ModuleOrchestrator transitions to next module.
    """

    model_config = ConfigDict(frozen=True)

    seed: str
    milestone_achieved: bool


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
class NarrationFrame:
    """Public context that can be narrated to the player."""

    purpose: str
    phase: EncounterPhase
    setting: str
    public_actor_summaries: tuple[str, ...]
    recent_public_events: tuple[str, ...]
    resolved_outcomes: tuple[str, ...]
    allowed_disclosures: tuple[str, ...]
    tone_guidance: str | None = None
    player_action: str | None = None
    prior_narrative_context: str = ""
    compendium_context: tuple[str, ...] = field(default_factory=tuple)
    npc_presences: tuple[NpcPresence, ...] = field(default_factory=tuple)


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


class NpcPresenceResult(BaseModel):
    """Structured NPC declaration from the scene opening LLM response.

    stat_source controls how ActorState is populated at encounter creation:
    - 'monster_compendium': look up monster_name in the monster index and parse
      combat stats from the SRD markdown via MonsterLoader.
    - 'simple_npc': create a minimal ActorState with placeholder combat stats
      (HP=1, AC=10, no attacks). Use for social NPCs not expected to fight.
    """

    model_config = ConfigDict(frozen=True)

    display_name: str
    description: str
    name_known: bool
    stat_source: Literal["monster_compendium", "simple_npc"]
    monster_name: str | None = None


class DivergenceAssessment(BaseModel):
    """Output of EncounterPlannerAgent._assess_agent."""

    model_config = ConfigDict(frozen=True)

    status: Literal[
        "viable",
        "needs_bridge",
        "needs_rebuild",
        "needs_full_replan",
        "milestone_achieved",
    ]
    reason: str
    milestone_achieved: bool


class EncounterPlanList(BaseModel):
    """Output of EncounterPlannerAgent._plan_agent."""

    model_config = ConfigDict(frozen=True)

    encounters: tuple[EncounterTemplate, ...]


class EncounterRecoveryResult(BaseModel):
    """Output of EncounterPlannerAgent._recovery_agent."""

    model_config = ConfigDict(frozen=True)

    updated_templates: tuple[EncounterTemplate, ...]
    recovery_type: Literal["bridge_inserted", "template_replaced", "full_replan"]


@dataclass(frozen=True)
class EncounterReady:
    """Returned by EncounterPlannerOrchestrator.prepare() on success.

    module may differ from the input module if recovery occurred.
    Callers must use EncounterReady.module, not their local reference.
    """

    encounter_state: EncounterState
    module: ModuleState


@dataclass(frozen=True)
class MilestoneAchieved:
    """Returned by EncounterPlannerOrchestrator.prepare() when milestone is complete.

    Signals ModuleOrchestrator to advance to the next module.
    """


class SceneOpeningResponse(BaseModel):
    """Structured LLM output for scene opening narration."""

    model_config = ConfigDict(frozen=True)

    text: str
    scene_tone: str
    introduced_npcs: list[NpcPresenceResult] = []


class CombatIntent(BaseModel):
    """Structured LLM output for a player's declared combat intent."""

    model_config = ConfigDict(frozen=True)

    intent: Literal["end_turn", "query_status", "exit_session", "combat_action"]


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
    "DivergenceAssessment",
    "EncounterNpc",
    "EncounterPhase",
    "EncounterPlanList",
    "EncounterReady",
    "EncounterRecoveryResult",
    "EncounterState",
    "EncounterTemplate",
    "FeatState",
    "GameState",
    "InitiativeTurn",
    "IntentCategory",
    "InventoryItem",
    "Milestone",
    "MilestoneAchieved",
    "ModuleState",
    "Narration",
    "NarrationFrame",
    "NextEncounterPlan",
    "NpcPresence",
    "NpcPresenceResult",
    "PlayerIO",
    "PlayerInput",
    "PlayerIntent",
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
