"""Rules agent for the potion of healing steel thread."""

from __future__ import annotations

import json
from typing import Any

from campaignnarrator.adapters.openai_adapter import OpenAIAdapter
from campaignnarrator.domain.models import (
    Action,
    Adjudication,
    RollRequest,
    RuleReference,
)
from campaignnarrator.repositories.compendium_repository import CompendiumRepository
from campaignnarrator.repositories.rules_repository import RulesRepository

_SUPPORTED_ACTION = "I drink my potion of healing"
_POTION_ITEM_ID = "potion-of-healing"
_ADJUDICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "outcome": {"type": "string"},
        "roll_request": {
            "type": "object",
            "properties": {
                "owner": {"type": "string"},
                "visibility": {"type": "string"},
                "expression": {"type": "string"},
                "purpose": {"type": "string"},
            },
            "required": ["owner", "visibility", "expression", "purpose"],
            "additionalProperties": False,
        },
    },
    "required": ["outcome", "roll_request"],
    "additionalProperties": False,
}


class RulesAgent:
    """Adjudicate the potion-of-healing action with a narrow rules slice."""

    def __init__(
        self,
        *,
        adapter: OpenAIAdapter,
        rules_repository: RulesRepository,
        compendium_repository: CompendiumRepository,
    ) -> None:
        self._adapter = adapter
        self._rules_repository = rules_repository
        self._compendium_repository = compendium_repository

    def adjudicate_potion_of_healing(self, *, actor: str) -> Adjudication:
        """Return a structured adjudication for drinking a potion of healing."""

        potion = self._compendium_repository.load_magic_item_by_id(_POTION_ITEM_ID)
        rule_index = self._rules_repository.load_rule_index()
        actions_markdown = self._rules_repository.load_topic_markdown(
            "source/adjudication/actions.md"
        )
        healing_markdown = self._rules_repository.load_topic_markdown(
            "source/adjudication/damage_healing.md"
        )
        action_references = (
            RuleReference(
                path="source/adjudication/actions.md",
                title="Actions",
                excerpt=_excerpt(actions_markdown),
            ),
            RuleReference(
                path="source/adjudication/damage_healing.md",
                title="Damage and Healing",
                excerpt=_excerpt(healing_markdown),
            ),
        )
        action = Action(
            actor=actor,
            summary=_SUPPORTED_ACTION,
            rule_references=action_references,
        )
        payload = self._adapter.generate_structured_json(
            instructions=(
                "You adjudicate only one supported action: I drink my "
                "potion of healing. "
                "Return a JSON object that matches the supplied schema. "
                "Keep the roll request explicit and public."
            ),
            input_text=json.dumps(
                {
                    "action": {
                        "actor": actor,
                        "summary": _SUPPORTED_ACTION,
                    },
                    "potion": potion,
                    "rule_index_topics": sorted(rule_index),
                    "rule_context": {
                        "actions": actions_markdown,
                        "damage_healing": healing_markdown,
                    },
                },
                indent=2,
                sort_keys=True,
            ),
            schema_name="potion_of_healing_adjudication",
            json_schema=_ADJUDICATION_SCHEMA,
        )
        return self._parse_adjudication(action, payload, action_references)

    def _parse_adjudication(
        self,
        action: Action,
        payload: dict[str, Any],
        rule_references: tuple[RuleReference, ...],
    ) -> Adjudication:
        outcome = payload.get("outcome")
        roll_request_payload = payload.get("roll_request")
        if not isinstance(outcome, str) or not isinstance(roll_request_payload, dict):
            raise TypeError("malformed payload")  # noqa: TRY003
        if outcome != "roll_requested":
            raise ValueError("invalid outcome")  # noqa: TRY003
        roll_request = self._parse_roll_request(roll_request_payload)
        return Adjudication(
            action=action,
            outcome=outcome,
            roll_request=roll_request,
            rule_references=rule_references,
        )

    def _parse_roll_request(self, payload: dict[str, Any]) -> RollRequest:
        owner = payload.get("owner")
        visibility = payload.get("visibility")
        expression = payload.get("expression")
        purpose = payload.get("purpose")
        if not all(
            isinstance(value, str) and value.strip()
            for value in (owner, visibility, expression, purpose)
        ):
            raise TypeError("malformed payload")  # noqa: TRY003
        if owner != "orchestrator":
            raise ValueError("invalid owner")  # noqa: TRY003
        if visibility != "public":
            raise ValueError("invalid visibility")  # noqa: TRY003
        if expression != "2d4+2":
            raise ValueError("invalid expression")  # noqa: TRY003
        return RollRequest(
            owner=owner,
            visibility=visibility,
            expression=expression,
            purpose=purpose,
        )


def _excerpt(markdown: str) -> str:
    lines = [line.strip() for line in markdown.splitlines() if line.strip()]
    if not lines:
        raise ValueError("empty output")  # noqa: TRY003
    return lines[1] if len(lines) > 1 else lines[0]
