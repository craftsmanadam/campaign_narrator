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


def _compendium_context(input_text: str) -> list[str]:
    """Parse the JSON input_text and return the compendium_context list."""
    return json.loads(input_text)["compendium_context"]


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


_DATA_COMPENDIUM_ROOT = Path(__file__).resolve().parents[2] / "data" / "compendium"


def _rogue_class_text() -> str:
    return (
        _DATA_COMPENDIUM_ROOT / "DND.SRD.Wiki-0.5.2" / "Classes" / "Rogue.md"
    ).read_text()


def test_social_phase_with_compendium_context_includes_class_text_in_prompt() -> None:
    """compendium_context passed in the request must appear in the LLM input."""

    adapter = CapturingAdapter(_CANNED_ADJUDICATION)
    agent = RulesAgent(
        adapter=adapter,
        rules_repository=RulesRepository(_DATA_RULES_ROOT),
    )
    rogue_text = _rogue_class_text()
    request = RulesAdjudicationRequest(
        actor_id="pc:talia",
        intent="I call out, claiming to be a travelling merchant.",
        phase=EncounterPhase.SOCIAL,
        allowed_outcomes=("success", "failure"),
        check_hints=("Deception",),
        compendium_context=(rogue_text,),
    )

    agent.adjudicate(request)

    compendium_ctx = _compendium_context(adapter.captured_input_texts[0])
    assert any(rogue_text[:100] in entry for entry in compendium_ctx)


def test_stealth_hint_includes_hiding_rules_in_prompt() -> None:
    """check_hints=('Stealth',) must load hiding.md into the rules_context."""

    adapter = CapturingAdapter(_CANNED_ADJUDICATION)
    agent = RulesAgent(
        adapter=adapter,
        rules_repository=RulesRepository(_DATA_RULES_ROOT),
    )
    rogue_text = _rogue_class_text()
    request = RulesAdjudicationRequest(
        actor_id="pc:talia",
        intent="I try to slip through the underbrush past the goblin camp.",
        phase=EncounterPhase.SOCIAL,
        allowed_outcomes=("success", "failure"),
        check_hints=("Stealth",),
        compendium_context=(rogue_text,),
    )

    agent.adjudicate(request)

    input_text = adapter.captured_input_texts[0]
    rules_context = _rules_context(input_text)
    hiding_rules = (
        _DATA_RULES_ROOT / "source" / "adjudication" / "hiding.md"
    ).read_text()
    assert any(hiding_rules in entry for entry in rules_context)
    compendium_ctx = _compendium_context(input_text)
    assert any(rogue_text[:100] in entry for entry in compendium_ctx)


def test_combat_phase_with_compendium_context_includes_sneak_attack_text() -> None:
    """Rogue class text in compendium_context must reach the COMBAT phase prompt."""

    adapter = CapturingAdapter(_CANNED_ADJUDICATION)
    agent = RulesAgent(
        adapter=adapter,
        rules_repository=RulesRepository(_DATA_RULES_ROOT),
    )
    rogue_text = _rogue_class_text()
    request = RulesAdjudicationRequest(
        actor_id="pc:talia",
        intent="I lunge from the shadows at the goblin scout with my dagger.",
        phase=EncounterPhase.COMBAT,
        allowed_outcomes=("hit", "miss", "damage", "defeated"),
        compendium_context=(rogue_text,),
    )

    agent.adjudicate(request)

    input_text = adapter.captured_input_texts[0]
    assert "Sneak Attack" in input_text
    compendium_ctx = _compendium_context(input_text)
    assert any(rogue_text[:100] in entry for entry in compendium_ctx)
