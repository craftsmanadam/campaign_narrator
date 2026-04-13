"""Integration tests: RulesAgent loads real rule files into the LLM prompt."""

from __future__ import annotations

import json
from pathlib import Path

from campaignnarrator.agents.rules_agent import RulesAgent
from campaignnarrator.domain.models import EncounterPhase, RulesAdjudicationRequest
from campaignnarrator.repositories.rules_repository import RulesRepository

_DATA_RULES_ROOT = Path(__file__).resolve().parents[2] / "data" / "rules"

_CANNED_ADJUDICATION: dict[str, object] = {
    "is_legal": True,
    "action_type": "social_check",
    "summary": "The goblins back away.",
    "roll_requests": [],
    "state_effects": [],
    "rule_references": [],
    "reasoning_summary": "The check succeeds.",
}


class CapturingAdapter:
    """Record generate_structured_json calls and return a canned response."""

    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload
        self.captured_input_texts: list[str] = []

    def generate_structured_json(
        self, *, instructions: str, input_text: str
    ) -> dict[str, object]:
        _ = instructions
        self.captured_input_texts.append(input_text)
        return self._payload


def _rules_context(input_text: str) -> list[str]:
    """Parse the JSON input_text and return the rules_context list."""
    return json.loads(input_text)["rules_context"]


def test_social_phase_adjudication_includes_social_interaction_rules() -> None:
    adapter = CapturingAdapter(_CANNED_ADJUDICATION)
    agent = RulesAgent(
        adapter=adapter,
        rules_repository=RulesRepository(_DATA_RULES_ROOT),
    )
    request = RulesAdjudicationRequest(
        actor_id="pc:talia",
        intent="I raise my hand and ask them to stand down.",
        phase=EncounterPhase.SOCIAL,
        allowed_outcomes=("de-escalated", "combat"),
        check_hints=("Persuasion check",),
    )

    agent.adjudicate(request)

    rules_context = _rules_context(adapter.captured_input_texts[0])
    social_rules = (
        _DATA_RULES_ROOT / "source" / "adjudication" / "social_interaction.md"
    ).read_text()
    assert any(social_rules in entry for entry in rules_context)


def test_social_phase_adjudication_includes_core_resolution_rules() -> None:
    adapter = CapturingAdapter(_CANNED_ADJUDICATION)
    agent = RulesAgent(
        adapter=adapter,
        rules_repository=RulesRepository(_DATA_RULES_ROOT),
    )
    request = RulesAdjudicationRequest(
        actor_id="pc:talia",
        intent="I raise my hand and ask them to stand down.",
        phase=EncounterPhase.SOCIAL,
        allowed_outcomes=("de-escalated", "combat"),
    )

    agent.adjudicate(request)

    rules_context = _rules_context(adapter.captured_input_texts[0])
    core_rules = (
        _DATA_RULES_ROOT / "source" / "adjudication" / "core_resolution.md"
    ).read_text()
    assert any(core_rules in entry for entry in rules_context)


def test_combat_phase_adjudication_includes_combat_rules() -> None:
    adapter = CapturingAdapter(_CANNED_ADJUDICATION)
    agent = RulesAgent(
        adapter=adapter,
        rules_repository=RulesRepository(_DATA_RULES_ROOT),
    )
    request = RulesAdjudicationRequest(
        actor_id="pc:talia",
        intent="I attack the goblin with my longsword.",
        phase=EncounterPhase.COMBAT,
        allowed_outcomes=("hit", "miss", "damage"),
    )

    agent.adjudicate(request)

    rules_context = _rules_context(adapter.captured_input_texts[0])
    combat_rules = (
        _DATA_RULES_ROOT / "source" / "adjudication" / "combat_flow.md"
    ).read_text()
    assert any(combat_rules in entry for entry in rules_context)


def test_combat_phase_adjudication_includes_core_resolution_rules() -> None:
    adapter = CapturingAdapter(_CANNED_ADJUDICATION)
    agent = RulesAgent(
        adapter=adapter,
        rules_repository=RulesRepository(_DATA_RULES_ROOT),
    )
    request = RulesAdjudicationRequest(
        actor_id="pc:talia",
        intent="I attack the goblin with my longsword.",
        phase=EncounterPhase.COMBAT,
        allowed_outcomes=("hit", "miss", "damage"),
    )

    agent.adjudicate(request)

    rules_context = _rules_context(adapter.captured_input_texts[0])
    core_rules = (
        _DATA_RULES_ROOT / "source" / "adjudication" / "core_resolution.md"
    ).read_text()
    assert any(core_rules in entry for entry in rules_context)


def test_check_hint_preserves_orchestrator_recommended_check() -> None:
    adapter = CapturingAdapter(_CANNED_ADJUDICATION)
    agent = RulesAgent(
        adapter=adapter,
        rules_repository=RulesRepository(_DATA_RULES_ROOT),
    )
    request = RulesAdjudicationRequest(
        actor_id="pc:talia",
        intent="I try to persuade them.",
        phase=EncounterPhase.SOCIAL,
        allowed_outcomes=("de-escalated", "combat"),
        check_hints=("Persuasion check",),
    )

    agent.adjudicate(request)

    input_text = adapter.captured_input_texts[0]
    assert "Persuasion check" in input_text
