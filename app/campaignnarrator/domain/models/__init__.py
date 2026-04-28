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
from .campaign_state import CampaignEvent, CampaignState, Milestone, ModuleState
from .combat import (
    CombatAssessment,
    CombatIntent,
    CombatOutcome,
    CombatResult,
    CombatStatus,
)
from .encounter_state import (
    EncounterPhase,
    EncounterReady,
    EncounterState,
    GameState,
    InitiativeTurn,
    MilestoneAchieved,
)
from .encounter_template import EncounterNpc, EncounterTemplate
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
    "CampaignEvent",
    "CampaignState",
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
]
