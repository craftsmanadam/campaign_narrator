"""Unit tests for PlayerIntentAgent."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from campaignnarrator.agents.player_intent_agent import PlayerIntentAgent
from campaignnarrator.agents.prompts import PLAYER_INTENT_INSTRUCTIONS
from campaignnarrator.domain.models import (
    EncounterPhase,
    IntentCategory,
    NpcPresence,
    NpcPresenceStatus,
    PlayerIntent,
)



def _make_agent(intent: PlayerIntent) -> PlayerIntentAgent:
    mock_agent = MagicMock()
    mock_agent.run_sync.return_value.output = intent
    return PlayerIntentAgent(adapter=MagicMock(), _agent=mock_agent)


def test_classify_returns_player_intent() -> None:
    expected = PlayerIntent(
        category=IntentCategory.SKILL_CHECK,
        check_hint="Stealth",
        reason="Player wants to sneak",
    )
    agent = _make_agent(expected)
    result = agent.classify(
        "I try to sneak past the guards",
        phase=EncounterPhase.SOCIAL,
        setting="A castle courtyard",
        recent_events=(),
        actor_summaries=(),
    )
    assert result.category is IntentCategory.SKILL_CHECK
    assert result.check_hint == "Stealth"


def test_classify_passes_serialized_context_to_agent() -> None:
    mock_agent = MagicMock()
    mock_agent.run_sync.return_value.output = PlayerIntent(
        category=IntentCategory.SCENE_OBSERVATION
    )
    agent = PlayerIntentAgent(adapter=MagicMock(), _agent=mock_agent)
    agent.classify(
        "I look around",
        phase=EncounterPhase.SOCIAL,
        setting="A castle courtyard",
        recent_events=("A goblin appeared",),
        actor_summaries=("Talia (player)",),
    )
    call_args = mock_agent.run_sync.call_args[0][0]
    payload = json.loads(call_args)
    assert payload["player_input"] == "I look around"
    assert payload["setting"] == "A castle courtyard"
    assert "A goblin appeared" in payload["recent_events"]
    assert "Talia (player)" in payload["actor_summaries"]


def test_classify_includes_phase_in_context() -> None:
    mock_agent = MagicMock()
    mock_agent.run_sync.return_value.output = PlayerIntent(
        category=IntentCategory.SCENE_OBSERVATION
    )
    agent = PlayerIntentAgent(adapter=MagicMock(), _agent=mock_agent)
    agent.classify(
        "I move forward",
        phase=EncounterPhase.SOCIAL,
        setting="Roadside camp",
        recent_events=(),
        actor_summaries=(),
    )
    payload = json.loads(mock_agent.run_sync.call_args[0][0])
    assert payload["phase"] == "social"


def test_classify_non_skill_check_has_no_check_hint() -> None:
    expected = PlayerIntent(category=IntentCategory.NPC_DIALOGUE, check_hint=None)
    agent = _make_agent(expected)
    result = agent.classify(
        "I ask the merchant about the map",
        phase=EncounterPhase.SOCIAL,
        setting="Market",
        recent_events=(),
        actor_summaries=(),
    )
    assert result.check_hint is None


# ---------------------------------------------------------------------------
# npc_presences tests
# ---------------------------------------------------------------------------


class _StubResult:
    def __init__(self, intent: PlayerIntent) -> None:
        self.output = intent


def test_classify_includes_npc_presences_in_payload_when_provided() -> None:
    """When npc_presences is non-empty, the JSON payload includes npc_presences."""
    captured: list[str] = []
    stub_output = PlayerIntent(category=IntentCategory.NPC_DIALOGUE)

    class CapturingAgent:
        def run_sync(self, payload_json: str) -> _StubResult:
            captured.append(payload_json)
            return _StubResult(stub_output)

    agent = PlayerIntentAgent(adapter=MagicMock(), _agent=CapturingAgent())
    presences = (
        NpcPresence(
            actor_id="npc:elder",
            display_name="Elder Rovan",
            description="the village elder",
            name_known=True,
            status=NpcPresenceStatus.AVAILABLE,
        ),
    )
    agent.classify(
        "I speak to Elder Rovan",
        phase=EncounterPhase.SOCIAL,
        setting="village square",
        recent_events=(),
        actor_summaries=(),
        npc_presences=presences,
    )
    payload = json.loads(captured[0])
    assert "npc_presences" in payload
    assert payload["npc_presences"][0]["actor_id"] == "npc:elder"
    assert payload["npc_presences"][0]["display_name"] == "Elder Rovan"


def test_classify_omits_npc_presences_from_payload_when_empty() -> None:
    """When npc_presences is empty, the JSON payload has no npc_presences key."""
    captured: list[str] = []
    stub_output = PlayerIntent(category=IntentCategory.SCENE_OBSERVATION)

    class CapturingAgent:
        def run_sync(self, payload_json: str) -> _StubResult:
            captured.append(payload_json)
            return _StubResult(stub_output)

    agent = PlayerIntentAgent(adapter=MagicMock(), _agent=CapturingAgent())
    agent.classify(
        "I look around",
        phase=EncounterPhase.SOCIAL,
        setting="village square",
        recent_events=(),
        actor_summaries=(),
    )
    payload = json.loads(captured[0])
    assert "npc_presences" not in payload


def test_classify_excludes_departed_npcs_from_payload() -> None:
    """DEPARTED NPCs are filtered out of the npc_presences payload."""
    captured: list[str] = []
    stub_output = PlayerIntent(category=IntentCategory.NPC_DIALOGUE)

    class CapturingAgent:
        def run_sync(self, payload_json: str) -> _StubResult:
            captured.append(payload_json)
            return _StubResult(stub_output)

    agent = PlayerIntentAgent(adapter=MagicMock(), _agent=CapturingAgent())
    presences = (
        NpcPresence(
            actor_id="npc:elder",
            display_name="Elder Rovan",
            description="the village elder",
            name_known=True,
            status=NpcPresenceStatus.AVAILABLE,
        ),
        NpcPresence(
            actor_id="npc:guard",
            display_name="Guard",
            description="the guard",
            name_known=False,
            status=NpcPresenceStatus.DEPARTED,
        ),
    )
    agent.classify(
        "I speak to the elder",
        phase=EncounterPhase.SOCIAL,
        setting="village square",
        recent_events=(),
        actor_summaries=(),
        npc_presences=presences,
    )
    payload = json.loads(captured[0])
    ids = [e["actor_id"] for e in payload.get("npc_presences", [])]
    assert "npc:elder" in ids
    assert "npc:guard" not in ids


def test_classify_omits_display_name_for_unknown_npcs() -> None:
    """When name_known=False, display_name is omitted and description is included."""
    captured: list[str] = []
    stub_output = PlayerIntent(category=IntentCategory.NPC_DIALOGUE)

    class CapturingAgent:
        def run_sync(self, payload_json: str) -> _StubResult:
            captured.append(payload_json)
            return _StubResult(stub_output)

    agent = PlayerIntentAgent(adapter=MagicMock(), _agent=CapturingAgent())
    presences = (
        NpcPresence(
            actor_id="npc:stranger",
            display_name="Mira",
            description="the hooded stranger",
            name_known=False,
            status=NpcPresenceStatus.AVAILABLE,
        ),
    )
    agent.classify(
        "I approach the stranger",
        phase=EncounterPhase.SOCIAL,
        setting="village square",
        recent_events=(),
        actor_summaries=(),
        npc_presences=presences,
    )
    payload = json.loads(captured[0])
    entry = payload["npc_presences"][0]
    assert "display_name" not in entry
    assert entry["description"] == "the hooded stranger"


@patch("campaignnarrator.agents.player_intent_agent.Agent")
@patch("campaignnarrator.agents.player_intent_agent.PydanticAIAdapter", MagicMock)
def test_player_intent_agent_passes_intent_instructions_to_agent(
    mock_agent_cls: MagicMock,
) -> None:
    PlayerIntentAgent(adapter=MagicMock())
    _, kwargs = mock_agent_cls.call_args
    assert kwargs["instructions"] == PLAYER_INTENT_INSTRUCTIONS
