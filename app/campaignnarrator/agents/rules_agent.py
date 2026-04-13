"""Generic rules agent for encounter adjudication."""

from __future__ import annotations

import json
from typing import Any

from campaignnarrator.domain.models import (
    EncounterPhase,
    RollRequest,
    RollVisibility,
    RulesAdjudication,
    RulesAdjudicationRequest,
    StateEffect,
)

_VALID_ROLL_OWNERS = {"player", "narrator", "system"}

# Maps each encounter phase to the rule topics loaded from disk before adjudication.
# Topic strings must match keys in data/rules/generated/rule_index.json.
_TOPICS_BY_PHASE: dict[EncounterPhase, tuple[str, ...]] = {
    EncounterPhase.SOCIAL: ("core_resolution", "social_interaction"),
    EncounterPhase.COMBAT: ("core_resolution", "combat"),
}
# Defensive default for phases not yet in _TOPICS_BY_PHASE (e.g. future enum values).
_FALLBACK_TOPICS: tuple[str, ...] = ("core_resolution",)


class RulesAgent:
    """Adjudicate encounter actions into structured rules output."""

    def __init__(
        self,
        *,
        adapter: object,
        rules_repository: object | None = None,
        compendium_repository: object | None = None,
    ) -> None:
        _ = compendium_repository  # reserved for spellcasting/compendium slice
        self._adapter = adapter
        self._rules_repository = rules_repository

    def adjudicate(self, request: RulesAdjudicationRequest) -> RulesAdjudication:
        """Return a structured adjudication for the supplied request."""

        rule_texts = self._load_rule_texts(request.phase)
        payload = self._adapter.generate_structured_json(
            instructions=(
                "You are a rules adjudication engine. Return only a single "
                "machine-readable JSON object. Do not include prose, markdown, "
                "or code fences. The object must contain is_legal, action_type, "
                "summary, reasoning_summary, and optional roll_requests, "
                "state_effects, and rule_references."
            ),
            input_text=json.dumps(
                self._build_input(request, rule_texts), indent=2, sort_keys=True
            ),
        )
        return self._parse_adjudication(payload)

    def _load_rule_texts(self, phase: EncounterPhase) -> tuple[str, ...]:
        if self._rules_repository is None:
            return ()
        topics = _TOPICS_BY_PHASE.get(phase, _FALLBACK_TOPICS)
        return self._rules_repository.load_context_for_topics(topics)

    def _build_input(
        self,
        request: RulesAdjudicationRequest,
        rule_texts: tuple[str, ...],
    ) -> dict[str, object]:
        rules_context = list(rule_texts) if rule_texts else []
        return {
            "actor_id": request.actor_id,
            "check_hint": list(request.check_hints),
            "compendium_context": list(request.compendium_context),
            "intent": request.intent,
            "phase": request.phase.value,
            "allowed_outcomes": list(request.allowed_outcomes),
            "rules_context": rules_context,
        }

    def _parse_adjudication(self, payload: object) -> RulesAdjudication:
        if not isinstance(payload, dict):
            raise ValueError("invalid payload")  # noqa: TRY003, TRY004

        is_legal = self._require_bool(payload, "is_legal")
        action_type = self._require_text(payload, "action_type")
        summary = self._require_text(payload, "summary")
        reasoning_summary = self._require_text(payload, "reasoning_summary")
        roll_requests = self._parse_roll_requests(payload.get("roll_requests"))
        state_effects = self._parse_state_effects(payload.get("state_effects"))
        rule_references = self._parse_rule_references(payload.get("rule_references"))

        return RulesAdjudication(
            is_legal=is_legal,
            action_type=action_type,
            summary=summary,
            roll_requests=roll_requests,
            state_effects=state_effects,
            rule_references=rule_references,
            reasoning_summary=reasoning_summary,
        )

    def _parse_roll_requests(self, payload: object) -> tuple[RollRequest, ...]:
        if payload is None:
            return ()
        if not isinstance(payload, list):
            raise ValueError("invalid roll_requests")  # noqa: TRY003, TRY004
        return tuple(self._parse_roll_request(entry) for entry in payload)

    def _parse_roll_request(self, payload: object) -> RollRequest:
        if not isinstance(payload, dict):
            raise ValueError("invalid roll request")  # noqa: TRY003, TRY004

        owner = self._require_text(payload, "owner")
        if owner not in _VALID_ROLL_OWNERS:
            raise ValueError(  # noqa: TRY003
                f"invalid roll owner: {owner}"
            )

        visibility_value = self._require_text(payload, "visibility")
        try:
            visibility = RollVisibility(visibility_value)
        except ValueError as exc:
            message = f"invalid roll visibility: {visibility_value}"
            raise ValueError(message) from exc

        expression = self._require_text(payload, "expression")
        purpose_value = payload.get("purpose")
        purpose: str | None
        if purpose_value is None:
            purpose = None
        else:
            purpose = self._require_text(payload, "purpose")

        return RollRequest(
            owner=owner,
            visibility=visibility,
            expression=expression,
            purpose=purpose,
        )

    def _parse_state_effects(self, payload: object) -> tuple[StateEffect, ...]:
        if payload is None:
            return ()
        if not isinstance(payload, list):
            raise ValueError("invalid state_effects")  # noqa: TRY003, TRY004
        return tuple(self._parse_state_effect(entry) for entry in payload)

    def _parse_state_effect(self, payload: object) -> StateEffect:
        if not isinstance(payload, dict):
            raise ValueError("invalid state effect")  # noqa: TRY003, TRY004

        effect_type = self._require_text(payload, "effect_type")
        target = self._require_text(payload, "target")
        value = payload.get("value")
        return StateEffect(effect_type=effect_type, target=target, value=value)

    def _parse_rule_references(self, payload: object) -> tuple[str, ...]:
        if payload is None:
            return ()
        if not isinstance(payload, list):
            raise ValueError("invalid rule_references")  # noqa: TRY003, TRY004
        references: list[str] = []
        for entry in payload:
            if not isinstance(entry, str) or not entry.strip():
                raise ValueError("invalid rule reference")  # noqa: TRY003
            references.append(entry)
        return tuple(references)

    def _require_bool(self, payload: dict[str, Any], field: str) -> bool:
        value = payload.get(field)
        if not isinstance(value, bool):
            raise ValueError(f"invalid {field}")  # noqa: TRY003, TRY004
        return value

    def _require_text(self, payload: dict[str, Any], field: str) -> str:
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"invalid {field}")  # noqa: TRY003
        return value
