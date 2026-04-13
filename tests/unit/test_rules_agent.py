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
        check_hints=("social rules",),
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


def test_rules_agent_roll_request_without_purpose_produces_none() -> None:
    payload = {
        "is_legal": True,
        "action_type": "attack",
        "summary": "Talia swings.",
        "roll_requests": [
            {
                "owner": "player",
                "visibility": "public",
                "expression": "1d20+3",
            }
        ],
        "state_effects": [],
        "rule_references": [],
        "reasoning_summary": "Purpose is optional.",
    }
    agent = RulesAgent(adapter=FakeAdapter(payload))
    request = RulesAdjudicationRequest(
        actor_id="player-1",
        intent="attack the goblin",
        phase=EncounterPhase.COMBAT,
        allowed_outcomes=("hit", "miss"),
    )

    adjudication = agent.adjudicate(request)

    assert len(adjudication.roll_requests) == 1
    assert adjudication.roll_requests[0].purpose is None


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


class FakeRulesRepository:
    """Return known rule text for requested topics."""

    def __init__(self, content_by_topic: dict[str, str]) -> None:
        self._content = content_by_topic

    def load_context_for_topics(self, topics: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(
            self._content.get(topic, f"Missing rules context: {topic}")
            for topic in topics
        )


_CANNED_ADJUDICATION: dict[str, object] = {
    "is_legal": True,
    "action_type": "social_check",
    "summary": "The goblins back away.",
    "roll_requests": [],
    "state_effects": [],
    "rule_references": [],
    "reasoning_summary": "The check succeeds.",
}


def test_adjudicate_social_phase_injects_loaded_rule_text() -> None:
    repo = FakeRulesRepository(
        {
            "core_resolution": "CORE RESOLUTION RULES",
            "social_interaction": "SOCIAL INTERACTION RULES",
        }
    )
    adapter = FakeAdapter(_CANNED_ADJUDICATION)
    agent = RulesAgent(adapter=adapter, rules_repository=repo)
    request = RulesAdjudicationRequest(
        actor_id="pc:talia",
        intent="I try to calm them down.",
        phase=EncounterPhase.SOCIAL,
        allowed_outcomes=("de-escalated", "combat"),
        check_hints=("Persuasion check",),
    )

    agent.adjudicate(request)

    input_text = adapter.calls[0]["input_text"]
    assert "CORE RESOLUTION RULES" in input_text
    assert "SOCIAL INTERACTION RULES" in input_text
    assert "Persuasion check" in input_text


def test_adjudicate_combat_phase_injects_loaded_rule_text() -> None:
    repo = FakeRulesRepository(
        {
            "core_resolution": "CORE RESOLUTION RULES",
            "combat": "COMBAT RULES",
        }
    )
    adapter = FakeAdapter(_CANNED_ADJUDICATION)
    agent = RulesAgent(adapter=adapter, rules_repository=repo)
    request = RulesAdjudicationRequest(
        actor_id="pc:talia",
        intent="I attack the goblin with my longsword.",
        phase=EncounterPhase.COMBAT,
        allowed_outcomes=("hit", "miss"),
    )

    agent.adjudicate(request)

    input_text = adapter.calls[0]["input_text"]
    assert "CORE RESOLUTION RULES" in input_text
    assert "COMBAT RULES" in input_text


def test_adjudicate_without_rules_repository_falls_back_to_hint_strings() -> None:
    adapter = FakeAdapter(_CANNED_ADJUDICATION)
    agent = RulesAgent(adapter=adapter, rules_repository=None)
    request = RulesAdjudicationRequest(
        actor_id="pc:talia",
        intent="I try to calm them down.",
        phase=EncounterPhase.SOCIAL,
        allowed_outcomes=("de-escalated", "combat"),
        check_hints=("Persuasion check",),
    )

    agent.adjudicate(request)

    input_text = adapter.calls[0]["input_text"]
    assert "Persuasion check" in input_text


def _canned_adapter() -> object:
    class _Adapter:
        def generate_structured_json(
            self, *, instructions: str, input_text: str
        ) -> dict:
            _ = instructions, input_text
            return {
                "is_legal": True,
                "action_type": "check",
                "summary": "ok",
                "reasoning_summary": "ok",
                "roll_requests": [],
                "state_effects": [],
                "rule_references": [],
            }

    return _Adapter()


def test_stealth_hint_loads_stealth_topic_in_addition_to_social_topics() -> None:
    """Hint 'Stealth' triggers the stealth topic on top of SOCIAL phase topics."""
    captured: list[tuple[str, ...]] = []

    class CapturingRulesRepository:
        def load_context_for_topics(self, topics: tuple[str, ...]) -> tuple[str, ...]:
            captured.append(topics)
            return ()

    adapter = _canned_adapter()
    agent = RulesAgent(adapter=adapter, rules_repository=CapturingRulesRepository())
    request = RulesAdjudicationRequest(
        actor_id="pc:talia",
        intent="I try to sneak past.",
        phase=EncounterPhase.SOCIAL,
        allowed_outcomes=("success", "failure"),
        check_hints=("Stealth",),
    )
    agent.adjudicate(request)

    assert len(captured) == 1
    assert "stealth" in captured[0]
    assert "core_resolution" in captured[0]


def test_hide_hint_also_loads_stealth_topic() -> None:
    """Hint 'hide' is an alias for the stealth topic expansion."""
    captured: list[tuple[str, ...]] = []

    class CapturingRulesRepository:
        def load_context_for_topics(self, topics: tuple[str, ...]) -> tuple[str, ...]:
            captured.append(topics)
            return ()

    adapter = _canned_adapter()
    agent = RulesAgent(adapter=adapter, rules_repository=CapturingRulesRepository())
    request = RulesAdjudicationRequest(
        actor_id="pc:talia",
        intent="I try to hide.",
        phase=EncounterPhase.SOCIAL,
        allowed_outcomes=("success", "failure"),
        check_hints=("hide",),
    )
    agent.adjudicate(request)

    assert len(captured) == 1
    assert "stealth" in captured[0]


def test_unknown_hint_does_not_expand_topics() -> None:
    """Hints with no matching entry in _EXTRA_TOPICS_BY_HINT have no effect."""
    captured: list[tuple[str, ...]] = []

    class CapturingRulesRepository:
        def load_context_for_topics(self, topics: tuple[str, ...]) -> tuple[str, ...]:
            captured.append(topics)
            return ()

    adapter = _canned_adapter()
    agent = RulesAgent(adapter=adapter, rules_repository=CapturingRulesRepository())
    request = RulesAdjudicationRequest(
        actor_id="pc:talia",
        intent="I do something unusual.",
        phase=EncounterPhase.SOCIAL,
        allowed_outcomes=("success", "failure"),
        check_hints=("UnrecognisedHint",),
    )
    agent.adjudicate(request)

    assert len(captured) == 1
    assert "stealth" not in captured[0]
