"""Generic rules agent for encounter adjudication."""

from __future__ import annotations

import json

from pydantic_ai import Agent

from campaignnarrator.adapters.pydantic_ai_adapter import PydanticAIAdapter
from campaignnarrator.domain.models import (
    EncounterPhase,
    RulesAdjudication,
    RulesAdjudicationRequest,
)

_TOPICS_BY_PHASE: dict[EncounterPhase, tuple[str, ...]] = {
    EncounterPhase.SOCIAL: ("core_resolution", "social_interaction"),
    EncounterPhase.COMBAT: ("core_resolution", "combat"),
}
_FALLBACK_TOPICS: tuple[str, ...] = ("core_resolution",)

_EXTRA_TOPICS_BY_HINT: dict[str, tuple[str, ...]] = {
    "stealth": ("stealth",),
    "hide": ("stealth",),
}

_RULES_INSTRUCTIONS = (
    "You are a rules adjudication engine for a D&D 5e encounter. "
    "Return a structured adjudication. "
    "Set is_legal based on whether the action is legal. "
    "Set action_type to one of the allowed_outcomes. "
    "Populate roll_requests for any dice rolls required. "
    "Populate state_effects for any state changes. "
    "Populate rule_references with relevant source references."
)


class RulesAgent:
    """Adjudicate encounter actions into structured rules output."""

    def __init__(
        self,
        *,
        adapter: object,
        rules_repository: object | None = None,
        compendium_repository: object | None = None,
        _agent: object | None = None,
    ) -> None:
        _ = compendium_repository
        self._rules_repository = rules_repository
        if _agent is not None:
            self._agent = _agent
        else:
            if not isinstance(adapter, PydanticAIAdapter):
                adapter_type = type(adapter).__name__
                msg = f"adapter must be a PydanticAIAdapter, got {adapter_type}"
                raise TypeError(msg)
            self._agent = Agent(
                adapter.model,
                output_type=RulesAdjudication,
                instructions=_RULES_INSTRUCTIONS,
            )

    def adjudicate(self, request: RulesAdjudicationRequest) -> RulesAdjudication:
        """Return a structured adjudication for the supplied request."""
        rule_texts = self._load_rule_texts(request.phase, request.check_hints)
        input_json = json.dumps(
            self._build_input(request, rule_texts), indent=2, sort_keys=True
        )
        return self._agent.run_sync(input_json).output

    def _load_rule_texts(
        self,
        phase: EncounterPhase,
        check_hints: tuple[str, ...] = (),
    ) -> tuple[str, ...]:
        if self._rules_repository is None:
            return ()
        topics = list(_TOPICS_BY_PHASE.get(phase, _FALLBACK_TOPICS))
        for hint in check_hints:
            extra = _EXTRA_TOPICS_BY_HINT.get(hint.lower(), ())
            for topic in extra:
                if topic not in topics:
                    topics.append(topic)
        return self._rules_repository.load_context_for_topics(tuple(topics))

    def _build_input(
        self,
        request: RulesAdjudicationRequest,
        rule_texts: tuple[str, ...],
    ) -> dict[str, object]:
        return {
            "actor_id": request.actor_id,
            "check_hint": list(request.check_hints),
            "compendium_context": list(request.compendium_context),
            "intent": request.intent,
            "phase": request.phase.value,
            "allowed_outcomes": list(request.allowed_outcomes),
            "rules_context": list(rule_texts),
        }
