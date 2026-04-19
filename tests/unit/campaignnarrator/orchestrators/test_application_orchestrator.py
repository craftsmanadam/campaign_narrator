"""Unit tests for the ApplicationOrchestrator."""

from __future__ import annotations

from campaignnarrator.orchestrators.application_orchestrator import (
    ApplicationOrchestrator,
)
from campaignnarrator.orchestrators.encounter_orchestrator import EncounterRunResult


class _FakeEncounterOrchestrator:
    def __init__(self) -> None:
        self.encounter_id: str | None = None
        self._result = EncounterRunResult(
            encounter_id="goblin-camp",
            output_text="The goblin grunts.",
            completed=False,
        )

    def run_encounter(self, *, encounter_id: str) -> EncounterRunResult:
        self.encounter_id = encounter_id
        return self._result


def test_application_orchestrator_delegates_run_encounter() -> None:
    fake = _FakeEncounterOrchestrator()
    orchestrator = ApplicationOrchestrator(encounter_orchestrator=fake)

    result = orchestrator.run_encounter(encounter_id="goblin-camp")

    assert fake.encounter_id == "goblin-camp"
    assert result is fake._result


def test_application_orchestrator_passes_through_completed_result() -> None:
    fake = _FakeEncounterOrchestrator()
    fake._result = EncounterRunResult(
        encounter_id="goblin-camp",
        output_text="The encounter ends.",
        completed=True,
    )
    orchestrator = ApplicationOrchestrator(encounter_orchestrator=fake)

    result = orchestrator.run_encounter(encounter_id="goblin-camp")

    assert result.completed is True
    assert result.output_text == "The encounter ends."
