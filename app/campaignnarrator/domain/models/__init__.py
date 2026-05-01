"""Domain models package — re-exports all public types.

Import from this package directly:
    from campaignnarrator.domain.models import ActorState, EncounterState, ...
"""

from __future__ import annotations

from .actor_components import (
    FeatState,
    InventoryItem,
    RecoveryPeriod,
    ResourceState,
    WeaponState,
)
from .actor_registry import ActorRegistry, EncounterTransition
from .actor_state import ActorState, ActorType, TurnResources
from .background_entry import BackgroundEntry
from .campaign_state import CampaignEvent, CampaignState, Milestone, ModuleState
from .class_entry import ClassEntry
from .combat import (
    CombatAssessment,
    CombatIntent,
    CombatOutcome,
    CombatResult,
    CombatStatus,
)
from .encounter_state import (
    EncounterPhase,
    EncounterState,
    InitiativeTurn,
    get_player,
    public_actor_summaries,
    visible_actor_names,
)
from .encounter_template import EncounterNpc, EncounterTemplate
from .feat_entry import FeatEntry
from .game_state import EncounterReady, GameState, MilestoneAchieved
from .intent import IntentCategory, PlayerInput, PlayerIntent, PlayerIO
from .narration import (
    Narration,
    NarrationFrame,
    NarrationResponse,
    SceneOpeningResponse,
)
from .npc_presence import NpcPresence, NpcPresenceStatus
from .planner import DivergenceAssessment, EncounterPlanList, EncounterRecoveryResult
from .roll import RollRequest, RollResult, RollVisibility
from .rules import (
    Action,
    Adjudication,
    RuleReference,
    RulesAdjudication,
    RulesAdjudicationRequest,
    StateEffect,
)

__all__ = [
    "Action",
    "ActorRegistry",
    "ActorState",
    "ActorType",
    "Adjudication",
    "BackgroundEntry",
    "CampaignEvent",
    "CampaignState",
    "ClassEntry",
    "CombatAssessment",
    "CombatIntent",
    "CombatOutcome",
    "CombatResult",
    "CombatStatus",
    "DivergenceAssessment",
    "EncounterNpc",
    "EncounterPhase",
    "EncounterPlanList",
    "EncounterReady",
    "EncounterRecoveryResult",
    "EncounterState",
    "EncounterTemplate",
    "EncounterTransition",
    "FeatEntry",
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
    "NarrationResponse",
    "NpcPresence",
    "NpcPresenceStatus",
    "PlayerIO",
    "PlayerInput",
    "PlayerIntent",
    "RecoveryPeriod",
    "ResourceState",
    "RollRequest",
    "RollResult",
    "RollVisibility",
    "RuleReference",
    "RulesAdjudication",
    "RulesAdjudicationRequest",
    "SceneOpeningResponse",
    "StateEffect",
    "TurnResources",
    "WeaponState",
    "get_player",
    "public_actor_summaries",
    "visible_actor_names",
]
