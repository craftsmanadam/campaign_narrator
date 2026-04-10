"""Unit tests for the campaign orchestrator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from campaignnarrator.domain.models import (
    Action,
    Adjudication,
    Narration,
    PotionOfHealingResolution,
    RollRequest,
)
from campaignnarrator.orchestrator import CampaignOrchestrator
from campaignnarrator.repositories.memory_repository import MemoryRepository
from campaignnarrator.repositories.state_repository import StateRepository


class _FakeRulesAgent:
    def __init__(self, adjudication: Adjudication) -> None:
        self.adjudication = adjudication
        self.calls: list[str] = []

    def adjudicate_potion_of_healing(self, *, actor: str) -> Adjudication:
        self.calls.append(actor)
        return self.adjudication


class _FakeNarratorAgent:
    def __init__(self, narration: Narration) -> None:
        self.narration = narration
        self.calls: list[tuple[Adjudication, PotionOfHealingResolution]] = []

    def narrate(
        self,
        adjudication: Adjudication,
        resolution: PotionOfHealingResolution,
    ) -> Narration:
        self.calls.append((adjudication, resolution))
        return self.narration


class _FailingNarratorAgent:
    def narrate(
        self,
        adjudication: Adjudication,
        resolution: PotionOfHealingResolution,
    ) -> Narration:
        raise RuntimeError


def _write_state(root: Path) -> StateRepository:
    (root).mkdir(parents=True)
    (root / "player_character.json").write_text(
        json.dumps(
            {
                "character_id": "pc-001",
                "name": "Talia",
                "hp": {"current": 12, "max": 18},
                "inventory": ["potion-of-healing", "rope"],
            }
        )
    )
    return StateRepository(root)


def test_orchestrator_resolves_potion_flow_end_to_end(tmp_path: Path) -> None:
    """The orchestrator should persist state, log the event, and narrate the result."""

    state_repository = _write_state(tmp_path / "state")
    memory_repository = MemoryRepository(tmp_path / "memory")
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
    rules_agent = _FakeRulesAgent(adjudication)
    narration = Narration(
        text="Talia drinks the potion and regains 7 hit points.",
        audience="player",
    )
    narrator_agent = _FakeNarratorAgent(narration)
    roll_calls: list[str] = []

    def _roll(expression: str) -> int:
        roll_calls.append(expression)
        return 7

    orchestrator = CampaignOrchestrator(
        state_repository=state_repository,
        rules_agent=rules_agent,
        memory_repository=memory_repository,
        narrator_agent=narrator_agent,
        roll_dice=_roll,
    )

    output = orchestrator.run("I drink my potion of healing")

    assert output == narration
    assert rules_agent.calls == ["Talia"]
    assert roll_calls == ["2d4+2"]
    assert narrator_agent.calls == [
        (
            adjudication,
            PotionOfHealingResolution(
                roll_total=7,
                healing_amount=7,
                hp_before=12,
                hp_after=18,
            ),
        )
    ]
    assert state_repository.load_player_character() == {
        "character_id": "pc-001",
        "name": "Talia",
        "hp": {"current": 18, "max": 18},
        "inventory": ["rope"],
    }
    assert memory_repository.load_event_log() == [
        {
            "type": "potion_of_healing_resolved",
            "actor": "Talia",
            "input": "I drink my potion of healing",
            "roll_request": {
                "owner": "orchestrator",
                "visibility": "public",
                "expression": "2d4+2",
                "purpose": "heal from potion of healing",
            },
            "roll_total": 7,
            "healing_amount": 7,
            "hp_before": 12,
            "hp_after": 18,
        }
    ]


def test_orchestrator_rejects_unsupported_player_input(tmp_path: Path) -> None:
    """Unsupported inputs should fail closed before any side effects happen."""

    state_repository = _write_state(tmp_path / "state")
    memory_repository = MemoryRepository(tmp_path / "memory")
    rules_agent = _FakeRulesAgent(
        Adjudication(
            action=Action(actor="Talia", summary="I drink my potion of healing"),
            outcome="roll_requested",
            roll_request=RollRequest(
                owner="orchestrator",
                visibility="public",
                expression="2d4+2",
                purpose="heal from potion of healing",
            ),
        )
    )
    narrator_agent = _FakeNarratorAgent(
        Narration(text="unused", audience="player")
    )
    orchestrator = CampaignOrchestrator(
        state_repository=state_repository,
        rules_agent=rules_agent,
        memory_repository=memory_repository,
        narrator_agent=narrator_agent,
        roll_dice=lambda expression: 7,
    )

    with pytest.raises(ValueError, match="unsupported"):
        orchestrator.run("I cast a spell")

    assert rules_agent.calls == []
    assert memory_repository.load_event_log() == []
    assert state_repository.load_player_character()["hp"] == {"current": 12, "max": 18}


def test_orchestrator_rejects_missing_potion_in_inventory(tmp_path: Path) -> None:
    """Missing required inventory state should stop the flow."""

    state_repository = _write_state(tmp_path / "state")
    state_repository.save_player_character(
        {
            "character_id": "pc-001",
            "name": "Talia",
            "hp": {"current": 12, "max": 18},
            "inventory": ["rope"],
        }
    )
    memory_repository = MemoryRepository(tmp_path / "memory")
    rules_agent = _FakeRulesAgent(
        Adjudication(
            action=Action(actor="Talia", summary="I drink my potion of healing"),
            outcome="roll_requested",
            roll_request=RollRequest(
                owner="orchestrator",
                visibility="public",
                expression="2d4+2",
                purpose="heal from potion of healing",
            ),
        )
    )
    narrator_agent = _FakeNarratorAgent(
        Narration(text="unused", audience="player")
    )
    orchestrator = CampaignOrchestrator(
        state_repository=state_repository,
        rules_agent=rules_agent,
        memory_repository=memory_repository,
        narrator_agent=narrator_agent,
        roll_dice=lambda expression: 7,
    )

    with pytest.raises(ValueError, match="potion"):
        orchestrator.run("I drink my potion of healing")

    assert rules_agent.calls == []
    assert memory_repository.load_event_log() == []
    assert state_repository.load_player_character()["inventory"] == ["rope"]


def test_orchestrator_does_not_persist_when_narration_fails(
    tmp_path: Path,
) -> None:
    """Narration failure must leave state and memory unchanged."""

    state_repository = _write_state(tmp_path / "state")
    memory_repository = MemoryRepository(tmp_path / "memory")
    rules_agent = _FakeRulesAgent(
        Adjudication(
            action=Action(actor="Talia", summary="I drink my potion of healing"),
            outcome="roll_requested",
            roll_request=RollRequest(
                owner="orchestrator",
                visibility="public",
                expression="2d4+2",
                purpose="heal from potion of healing",
            ),
        )
    )
    orchestrator = CampaignOrchestrator(
        state_repository=state_repository,
        rules_agent=rules_agent,
        memory_repository=memory_repository,
        narrator_agent=_FailingNarratorAgent(),
        roll_dice=lambda expression: 7,
    )

    with pytest.raises(RuntimeError):
        orchestrator.run("I drink my potion of healing")

    assert state_repository.load_player_character() == {
        "character_id": "pc-001",
        "name": "Talia",
        "hp": {"current": 12, "max": 18},
        "inventory": ["potion-of-healing", "rope"],
    }
    assert memory_repository.load_event_log() == []
