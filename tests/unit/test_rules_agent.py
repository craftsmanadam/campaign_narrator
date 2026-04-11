"""Unit tests for the rules agent."""

from __future__ import annotations

import pytest
from campaignnarrator.agents.rules_agent import RulesAgent
from campaignnarrator.domain.models import (
    EncounterPhase,
    RollRequest,
    RollVisibility,
    RulesAdjudication,
    RulesAdjudicationRequest,
    StateEffect,
)


class FakeAdapter:
    """Capture structured-json calls for assertions."""

    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[dict[str, object]] = []

    def generate_structured_json(
        self, *, instructions: str, input_text: str
    ) -> dict[str, object]:
        self.calls.append(
            {
                "instructions": instructions,
                "input_text": input_text,
            }
        )
        return self.payload


class FakeRawAdapter:
    """Return a non-dict payload to exercise adapter-boundary validation."""

    def __init__(self, payload: object) -> None:
        self.payload = payload

    def generate_structured_json(self, *, instructions: str, input_text: str) -> object:
        _ = instructions, input_text
        return self.payload


def test_rules_agent_returns_generic_adjudication() -> None:
    payload = {
        "is_legal": True,
        "action_type": "social_check",
        "summary": "The goblins hesitate and lower their weapons.",
        "roll_requests": [
            {
                "owner": "player",
                "visibility": "public",
                "expression": "1d20+2",
                "purpose": "Persuasion check",
            }
        ],
        "state_effects": [
            {
                "effect_type": "set_encounter_outcome",
                "target": "encounter:goblin-camp",
                "value": "de-escalated",
            }
        ],
        "rule_references": ["source/rules/social.md", "source/rules/outcomes.md"],
        "reasoning_summary": "The intent is peaceful and supported by the scene.",
    }
    adapter = FakeAdapter(payload)
    agent = RulesAgent(adapter=adapter)
    request = RulesAdjudicationRequest(
        actor_id="player-1",
        intent="calm the goblin camp",
        phase=EncounterPhase.SOCIAL,
        allowed_outcomes=("de-escalated", "combat"),
        rules_context=("social rules",),
        compendium_context=("goblin camp lore",),
    )

    adjudication = agent.adjudicate(request)

    assert adjudication == RulesAdjudication(
        is_legal=True,
        action_type="social_check",
        summary="The goblins hesitate and lower their weapons.",
        roll_requests=(
            RollRequest(
                owner="player",
                visibility=RollVisibility.PUBLIC,
                expression="1d20+2",
                purpose="Persuasion check",
            ),
        ),
        state_effects=(
            StateEffect(
                effect_type="set_encounter_outcome",
                target="encounter:goblin-camp",
                value="de-escalated",
            ),
        ),
        rule_references=("source/rules/social.md", "source/rules/outcomes.md"),
        reasoning_summary="The intent is peaceful and supported by the scene.",
    )
    assert len(adapter.calls) == 1
    assert adapter.calls[0]["input_text"].count("intent") == 1


@pytest.mark.parametrize(
    ("payload", "match"),
    [
        (
            {
                "is_legal": True,
                "action_type": "social_check",
                "summary": "A response is required.",
                "roll_requests": [
                    {
                        "owner": "player",
                        "visibility": "everyone",
                        "expression": "1d20+2",
                        "purpose": "Persuasion check",
                    }
                ],
                "state_effects": [],
                "rule_references": [],
                "reasoning_summary": "Visibility must be validated.",
            },
            "invalid roll visibility: everyone",
        ),
        (
            {
                "is_legal": True,
                "action_type": "social_check",
                "summary": "A response is required.",
                "roll_requests": [
                    {
                        "owner": "witness",
                        "visibility": "public",
                        "expression": "1d20+2",
                        "purpose": "Persuasion check",
                    }
                ],
                "state_effects": [],
                "rule_references": [],
                "reasoning_summary": "Owner must be validated.",
            },
            "invalid roll owner: witness",
        ),
    ],
)
def test_rules_agent_rejects_invalid_roll_metadata(
    payload: dict[str, object], match: str
) -> None:
    adapter = FakeAdapter(payload)
    agent = RulesAgent(adapter=adapter)
    request = RulesAdjudicationRequest(
        actor_id="player-1",
        intent="calm the goblin camp",
        phase=EncounterPhase.SOCIAL,
        allowed_outcomes=("de-escalated", "combat"),
    )

    with pytest.raises(ValueError, match=match):
        agent.adjudicate(request)


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("roll_requests", "not-a-list", "invalid roll_requests"),
        ("roll_requests", ["not-a-dict"], "invalid roll request"),
        ("roll_requests", [{"owner": "player"}], "visibility"),
        ("roll_requests", [{"owner": "player", "visibility": "public"}], "expression"),
        (
            "roll_requests",
            [
                {
                    "owner": "player",
                    "visibility": "public",
                    "expression": "1d20",
                    "purpose": 7,
                }
            ],
            "purpose",
        ),
        ("state_effects", "not-a-list", "invalid state_effects"),
        ("state_effects", ["not-a-dict"], "invalid state effect"),
        ("rule_references", "not-a-list", "invalid rule_references"),
        ("rule_references", [""], "invalid rule reference"),
    ],
)
def test_rules_agent_rejects_invalid_optional_collections(
    field: str,
    value: object,
    match: str,
) -> None:
    payload: dict[str, object] = {
        "is_legal": True,
        "action_type": "social_check",
        "summary": "A response is required.",
        "roll_requests": [],
        "state_effects": [],
        "rule_references": [],
        "reasoning_summary": "Optional collections must be validated.",
    }
    payload[field] = value
    agent = RulesAgent(adapter=FakeAdapter(payload))
    request = RulesAdjudicationRequest(
        actor_id="player-1",
        intent="calm the goblin camp",
        phase=EncounterPhase.SOCIAL,
        allowed_outcomes=("de-escalated", "combat"),
    )

    with pytest.raises(ValueError, match=match):
        agent.adjudicate(request)


def test_rules_agent_rejects_non_object_payload() -> None:
    agent = RulesAgent(adapter=FakeRawAdapter("not-json-object"))
    request = RulesAdjudicationRequest(
        actor_id="player-1",
        intent="calm the goblin camp",
        phase=EncounterPhase.SOCIAL,
        allowed_outcomes=("de-escalated", "combat"),
    )

    with pytest.raises(ValueError, match="invalid payload"):
        agent.adjudicate(request)


@pytest.mark.parametrize(
    ("payload", "match"),
    [
        (
            {
                "action_type": "social_check",
                "summary": "A response is required.",
                "roll_requests": [],
                "state_effects": [],
                "rule_references": [],
                "reasoning_summary": "Missing legality.",
            },
            "is_legal",
        ),
        (
            {
                "is_legal": True,
                "action_type": "",
                "summary": "A response is required.",
                "roll_requests": [],
                "state_effects": [],
                "rule_references": [],
                "reasoning_summary": "Missing action type.",
            },
            "action_type",
        ),
        (
            {
                "is_legal": True,
                "action_type": "social_check",
                "summary": "",
                "roll_requests": [],
                "state_effects": [],
                "rule_references": [],
                "reasoning_summary": "Missing summary.",
            },
            "summary",
        ),
        (
            {
                "is_legal": True,
                "action_type": "social_check",
                "summary": "A response is required.",
                "roll_requests": [],
                "state_effects": [],
                "rule_references": [],
                "reasoning_summary": "",
            },
            "reasoning_summary",
        ),
    ],
)
def test_rules_agent_rejects_missing_required_top_level_values(
    payload: dict[str, object], match: str
) -> None:
    adapter = FakeAdapter(payload)
    agent = RulesAgent(adapter=adapter)
    request = RulesAdjudicationRequest(
        actor_id="player-1",
        intent="calm the goblin camp",
        phase=EncounterPhase.SOCIAL,
        allowed_outcomes=("de-escalated", "combat"),
    )

    with pytest.raises(ValueError, match=match):
        agent.adjudicate(request)


@pytest.mark.parametrize(
    ("payload", "match"),
    [
        (
            {
                "is_legal": True,
                "action_type": "social_check",
                "summary": "A response is required.",
                "roll_requests": [],
                "state_effects": [
                    {
                        "target": "encounter:goblin-camp",
                        "value": "de-escalated",
                    }
                ],
                "rule_references": [],
                "reasoning_summary": "Effect type missing.",
            },
            "effect_type",
        ),
        (
            {
                "is_legal": True,
                "action_type": "social_check",
                "summary": "A response is required.",
                "roll_requests": [],
                "state_effects": [
                    {
                        "effect_type": "set_encounter_outcome",
                        "value": "de-escalated",
                    }
                ],
                "rule_references": [],
                "reasoning_summary": "Target missing.",
            },
            "target",
        ),
    ],
)
def test_rules_agent_rejects_invalid_state_effects(
    payload: dict[str, object], match: str
) -> None:
    adapter = FakeAdapter(payload)
    agent = RulesAgent(adapter=adapter)
    request = RulesAdjudicationRequest(
        actor_id="player-1",
        intent="calm the goblin camp",
        phase=EncounterPhase.SOCIAL,
        allowed_outcomes=("de-escalated", "combat"),
    )

    with pytest.raises(ValueError, match=match):
        agent.adjudicate(request)


@pytest.mark.parametrize(
    ("field", "value"),
    [("action_type", ""), ("summary", " "), ("reasoning_summary", "\t")],
)
def test_rules_agent_rejects_empty_text_fields(field: str, value: str) -> None:
    payload: dict[str, object] = {
        "is_legal": True,
        "action_type": "social_check",
        "summary": "A response is required.",
        "roll_requests": [],
        "state_effects": [],
        "rule_references": [],
        "reasoning_summary": "The goblins are listening.",
    }
    payload[field] = value
    adapter = FakeAdapter(payload)
    agent = RulesAgent(adapter=adapter)
    request = RulesAdjudicationRequest(
        actor_id="player-1",
        intent="calm the goblin camp",
        phase=EncounterPhase.SOCIAL,
        allowed_outcomes=("de-escalated", "combat"),
    )

    with pytest.raises(ValueError, match=field):
        agent.adjudicate(request)
