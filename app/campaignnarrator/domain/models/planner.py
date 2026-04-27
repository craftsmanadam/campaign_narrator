"""Encounter planner output models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from .encounter_template import EncounterTemplate


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
