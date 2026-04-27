"""Unit tests for planner domain models."""

from __future__ import annotations

import pytest
from campaignnarrator.domain.models import (
    DivergenceAssessment,
    EncounterPlanList,
    EncounterRecoveryResult,
    EncounterTemplate,
)
from pydantic import ValidationError


def _make_encounter_template(template_id: str = "enc-001") -> EncounterTemplate:
    return EncounterTemplate(
        template_id=template_id,
        order=0,
        setting="x",
        purpose="y",
        npcs=(),
        prerequisites=(),
        expected_outcomes=(),
        downstream_dependencies=(),
    )


def test_divergence_assessment_viable() -> None:
    a = DivergenceAssessment(
        status="viable", reason="prerequisites met", milestone_achieved=False
    )
    assert a.status == "viable"
    assert a.milestone_achieved is False


def test_divergence_assessment_milestone_achieved() -> None:
    a = DivergenceAssessment(
        status="milestone_achieved",
        reason="Player defeated the cult leader.",
        milestone_achieved=True,
    )
    assert a.milestone_achieved is True


def test_divergence_assessment_rejects_invalid_status() -> None:
    with pytest.raises(ValidationError):
        DivergenceAssessment(status="unknown", reason="x", milestone_achieved=False)


def test_encounter_plan_list_stores_encounters() -> None:
    t = _make_encounter_template()
    plan = EncounterPlanList(encounters=(t,))
    assert len(plan.encounters) == 1


def test_encounter_recovery_result_bridge_inserted() -> None:
    t = EncounterTemplate(
        template_id="enc-bridge",
        order=0,
        setting="x",
        purpose="y",
        npcs=(),
        prerequisites=(),
        expected_outcomes=(),
        downstream_dependencies=(),
    )
    result = EncounterRecoveryResult(
        updated_templates=(t,), recovery_type="bridge_inserted"
    )
    assert result.recovery_type == "bridge_inserted"
    assert len(result.updated_templates) == 1
