"""Application-level orchestrator: top-level router between workflow orchestrators."""

from __future__ import annotations

from campaignnarrator.orchestrators.encounter_orchestrator import (
    EncounterOrchestrator,
    EncounterRunResult,
)


class ApplicationOrchestrator:
    """Route top-level application flow to the appropriate sub-orchestrator.

    For this slice, all play is routed directly to the EncounterOrchestrator.
    Routing logic for campaign creation, character creation, and session
    management is deferred until those orchestrators exist.
    """

    def __init__(self, *, encounter_orchestrator: EncounterOrchestrator) -> None:
        self._encounter_orchestrator = encounter_orchestrator

    def run_encounter(self, *, encounter_id: str) -> EncounterRunResult:
        """Delegate encounter play to the EncounterOrchestrator."""

        return self._encounter_orchestrator.run_encounter(encounter_id=encounter_id)
