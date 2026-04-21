"""Generic rules agent for encounter adjudication."""

from __future__ import annotations

import json
import logging

from pydantic_ai import Agent

from campaignnarrator.adapters.pydantic_ai_adapter import PydanticAIAdapter
from campaignnarrator.agents.prompts import RULES_INSTRUCTIONS
from campaignnarrator.domain.models import (
    EncounterPhase,
    RulesAdjudication,
    RulesAdjudicationRequest,
)

_log = logging.getLogger(__name__)

_SKILL_CHECK_TOPICS: frozenset[str] = frozenset(
    {
        "Acrobatics",
        "Animal Handling",
        "Arcana",
        "Athletics",
        "Deception",
        "History",
        "Insight",
        "Intimidation",
        "Investigation",
        "Medicine",
        "Nature",
        "Perception",
        "Performance",
        "Persuasion",
        "Religion",
        "Sleight of Hand",
        "Stealth",
        "Survival",
    }
)

_EXTRA_TOPICS_BY_HINT: dict[str, tuple[str, ...]] = {
    "stealth": ("stealth",),
    "hide": ("stealth",),
}

_MAX_EXPECTED_RULES_CONTEXT: int = 3500

_RULES_INSTRUCTIONS = RULES_INSTRUCTIONS


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
        check_hint = request.check_hints[0] if request.check_hints else None
        rule_texts = self._load_rule_texts(check_hint, phase=request.phase)
        total_chars = sum(len(t) for t in rule_texts)
        if total_chars > _MAX_EXPECTED_RULES_CONTEXT:
            _log.error(
                "Rules context size %d exceeds threshold %d — "
                "topic selection needs review (check_hint=%r)",
                total_chars,
                _MAX_EXPECTED_RULES_CONTEXT,
                request.check_hints,
            )
        input_json = json.dumps(
            self._build_input(request, rule_texts), indent=2, sort_keys=True
        )
        _log.info("Adjudication request: %s", input_json)
        result = self._agent.run_sync(input_json).output
        _log.info(
            "Adjudication result: action_type=%s summary=%r roll_requests=%s "
            "state_effects=%s",
            result.action_type,
            result.summary,
            [
                {"expression": r.expression, "visibility": r.visibility.value}
                for r in result.roll_requests
            ],
            [
                {"effect_type": e.effect_type, "target": e.target, "value": e.value}
                for e in result.state_effects
            ],
        )
        return result

    def _load_rule_texts(
        self,
        check_hint: str | None = None,
        phase: EncounterPhase | None = None,
    ) -> tuple[str, ...]:
        if self._rules_repository is None:
            return ()

        hint_lower = (check_hint or "").lower()

        if check_hint and check_hint in _SKILL_CHECK_TOPICS:
            base_topics: list[str] = ["skill_check"]
        elif phase is EncounterPhase.COMBAT:
            base_topics = ["attack_resolution"]
        else:
            base_topics = ["social_interaction"]

        for hint_key, extra in _EXTRA_TOPICS_BY_HINT.items():
            if hint_key in hint_lower:
                for topic in extra:
                    if topic not in base_topics:
                        base_topics.append(topic)

        return self._rules_repository.load_context_for_topics(tuple(base_topics))

    def _build_input(
        self,
        request: RulesAdjudicationRequest,
        rule_texts: tuple[str, ...],
    ) -> dict[str, object]:
        data: dict[str, object] = {
            "actor_id": request.actor_id,
            "check_hint": list(request.check_hints),
            "compendium_context": list(request.compendium_context),
            "intent": request.intent,
            "phase": request.phase.value,
            "allowed_outcomes": list(request.allowed_outcomes),
            "rules_context": list(rule_texts),
        }
        if request.actor_modifiers:
            data["actor_modifiers"] = dict(request.actor_modifiers)
        return data
