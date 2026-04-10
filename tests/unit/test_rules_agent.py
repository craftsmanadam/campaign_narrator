"""Unit tests for the rules agent."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from campaignnarrator.agents.rules_agent import RulesAgent
from campaignnarrator.domain.models import (
    Action,
    Adjudication,
    RollRequest,
    RuleReference,
)
from campaignnarrator.repositories.compendium_repository import CompendiumRepository
from campaignnarrator.repositories.rules_repository import RulesRepository


class _FakeAdapter:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[dict[str, object]] = []

    def generate_structured_json(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(kwargs)
        return self.payload


def _write_rules_fixture(root: Path) -> RulesRepository:
    (root / "generated").mkdir(parents=True)
    (root / "source" / "adjudication").mkdir(parents=True)
    (root / "generated" / "rule_index.json").write_text(
        json.dumps({"actions": ["actions.md"], "damage_healing": ["damage_healing.md"]})
    )
    (root / "source" / "adjudication" / "actions.md").write_text(
        "# Actions\n\nDrinking a potion is an action."
    )
    (root / "source" / "adjudication" / "damage_healing.md").write_text(
        "# Damage and Healing\n\nA potion of healing restores hit points."
    )
    return RulesRepository(root)


def _write_compendium_fixture(root: Path) -> CompendiumRepository:
    (root / "magic_items").mkdir(parents=True)
    (root / "magic_items" / "common.json").write_text(
        json.dumps(
            {
                "magic_items": [
                    {
                        "item_id": "potion-of-healing",
                        "name": "Potion of Healing",
                        "rarity": "common",
                        "description": (
                            "A restorative potion that replenishes hit points."
                        ),
                    }
                ]
            }
        )
    )
    (root / "magic_items" / "rare.json").write_text(
        json.dumps(
            {
                "magic_items": [
                    {
                        "item_id": "bag-of-beans",
                        "name": "Bag of Beans",
                        "rarity": "rare",
                    }
                ]
            }
        )
    )
    return CompendiumRepository(root)


def test_rules_agent_returns_a_structured_potion_adjudication(
    tmp_path: Path,
) -> None:
    """The rules agent should adjudicate the potion action explicitly."""

    rules = _write_rules_fixture(tmp_path / "rules")
    compendium = _write_compendium_fixture(tmp_path / "compendium")
    adapter = _FakeAdapter(
        {
            "outcome": "roll_requested",
            "roll_request": {
                "owner": "orchestrator",
                "visibility": "public",
                "expression": "2d4+2",
                "purpose": "heal from potion of healing",
            },
        }
    )
    agent = RulesAgent(
        adapter=adapter,
        rules_repository=rules,
        compendium_repository=compendium,
    )

    adjudication = agent.adjudicate_potion_of_healing(actor="Talia")

    assert adjudication == Adjudication(
        action=Action(
            actor="Talia",
            summary="I drink my potion of healing",
            rule_references=(
                RuleReference(
                    path="source/adjudication/actions.md",
                    title="Actions",
                    excerpt="Drinking a potion is an action.",
                ),
                RuleReference(
                    path="source/adjudication/damage_healing.md",
                    title="Damage and Healing",
                    excerpt="A potion of healing restores hit points.",
                ),
            ),
        ),
        outcome="roll_requested",
        roll_request=RollRequest(
            owner="orchestrator",
            visibility="public",
            expression="2d4+2",
            purpose="heal from potion of healing",
        ),
        rule_references=(
            RuleReference(
                path="source/adjudication/actions.md",
                title="Actions",
                excerpt="Drinking a potion is an action.",
            ),
            RuleReference(
                path="source/adjudication/damage_healing.md",
                title="Damage and Healing",
                excerpt="A potion of healing restores hit points.",
            ),
        ),
    )
    assert adapter.calls[0]["schema_name"] == "potion_of_healing_adjudication"
    assert "I drink my potion of healing" in adapter.calls[0]["input_text"]
    assert "Potion of Healing" in adapter.calls[0]["input_text"]


def test_rules_agent_rejects_malformed_adapter_output(
    tmp_path: Path,
) -> None:
    """Malformed structured output should fail closed."""

    rules = _write_rules_fixture(tmp_path / "rules")
    compendium = _write_compendium_fixture(tmp_path / "compendium")
    adapter = _FakeAdapter({"outcome": "roll_requested"})
    agent = RulesAgent(
        adapter=adapter,
        rules_repository=rules,
        compendium_repository=compendium,
    )

    with pytest.raises(TypeError, match="malformed"):
        agent.adjudicate_potion_of_healing(actor="Talia")


@pytest.mark.parametrize(
    ("roll_request", "match"),
    [
        (
            {
                "owner": "orchestrator",
                "visibility": "private",
                "expression": "2d4+2",
                "purpose": "heal from potion of healing",
            },
            "visibility",
        ),
        (
            {
                "owner": "orchestrator",
                "visibility": "public",
                "expression": "1d8+1",
                "purpose": "heal from potion of healing",
            },
            "expression",
        ),
    ],
)
def test_rules_agent_rejects_semantically_invalid_roll_requests(
    tmp_path: Path,
    roll_request: dict[str, str],
    match: str,
) -> None:
    """The potion slice must keep the roll request explicit and exact."""

    rules = _write_rules_fixture(tmp_path / "rules")
    compendium = _write_compendium_fixture(tmp_path / "compendium")
    adapter = _FakeAdapter(
        {
            "outcome": "roll_requested",
            "roll_request": roll_request,
        }
    )
    agent = RulesAgent(
        adapter=adapter,
        rules_repository=rules,
        compendium_repository=compendium,
    )

    with pytest.raises(ValueError, match=match):
        agent.adjudicate_potion_of_healing(actor="Talia")
