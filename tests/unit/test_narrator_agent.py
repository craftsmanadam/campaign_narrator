"""Unit tests for the narrator agent."""

from __future__ import annotations

import pytest
from campaignnarrator.agents.narrator_agent import NarratorAgent
from campaignnarrator.domain.models import (
    Action,
    Adjudication,
    Narration,
    PotionOfHealingResolution,
    RollRequest,
)


class _FakeAdapter:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[dict[str, object]] = []

    def generate_text(self, **kwargs: object) -> str:
        self.calls.append(kwargs)
        return self.text


def test_narrator_agent_turns_adjudication_into_player_facing_text() -> None:
    """Narration should be rendered from the adjudication details."""

    adapter = _FakeAdapter("Talia drinks the potion and waits for the result.")
    agent = NarratorAgent(adapter=adapter)
    adjudication = Adjudication(
        action=Action(actor="Talia", summary="I drink my potion of healing"),
        outcome="roll_requested",
        roll_request=RollRequest(
            owner="orchestrator",
            visibility="public",
            expression="2d4+2",
            purpose="heal from potion of healing",
        ),
    )
    resolution = PotionOfHealingResolution(
        roll_total=7,
        healing_amount=7,
        hp_before=12,
        hp_after=18,
    )

    narration = agent.narrate(adjudication, resolution)

    assert narration == Narration(
        text="Talia drinks the potion and waits for the result.",
        audience="player",
    )
    assert '"outcome"' not in adapter.calls[0]["input_text"]
    assert '"roll_request"' not in adapter.calls[0]["input_text"]
    assert '"rule_references"' not in adapter.calls[0]["input_text"]
    assert '"healing_amount": 7' in adapter.calls[0]["input_text"]


def test_narrator_agent_rejects_blank_text() -> None:
    """Blank text output should fail closed."""

    adapter = _FakeAdapter("")
    agent = NarratorAgent(adapter=adapter)
    adjudication = Adjudication(
        action=Action(actor="Talia", summary="I drink my potion of healing"),
        outcome="roll_requested",
        roll_request=RollRequest(
            owner="orchestrator",
            visibility="public",
            expression="2d4+2",
            purpose="heal from potion of healing",
        ),
    )
    resolution = PotionOfHealingResolution(
        roll_total=7,
        healing_amount=7,
        hp_before=12,
        hp_after=18,
    )

    with pytest.raises(ValueError, match="empty"):
        agent.narrate(adjudication, resolution)
