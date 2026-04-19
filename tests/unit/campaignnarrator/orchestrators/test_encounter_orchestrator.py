"""Unit tests for the encounter-loop campaign orchestrator."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from campaignnarrator.domain.models import (
    ActorState,
    ActorType,
    CombatAssessment,
    CombatIntent,
    CombatOutcome,
    CritReview,
    EncounterPhase,
    EncounterState,
    InitiativeTurn,
    Narration,
    NarrationFrame,
    OrchestrationDecision,
    RollRequest,
    RollVisibility,
    RulesAdjudication,
    RulesAdjudicationRequest,
    StateEffect,
)
from campaignnarrator.orchestrators.encounter_orchestrator import (
    EncounterOrchestrator,
    EncounterRunResult,
    OrchestratorAgents,
    OrchestratorRepositories,
    OrchestratorTools,
)
from campaignnarrator.repositories.actor_repository import ActorRepository
from campaignnarrator.repositories.encounter_repository import EncounterRepository
from campaignnarrator.repositories.state_repository import StateRepository

from tests.conftest import ScriptedIO

_DAMAGED_GOBLIN_HP = 2


class FakeMemoryRepository:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def append_event(self, event: Mapping[str, object]) -> None:
        self.events.append(dict(event))


class FakeRulesAgent:
    """Rules agent stub."""

    def __init__(self, adjudications: list[RulesAdjudication] | None = None) -> None:
        self.adjudications = list(adjudications or [])
        self.requests: list[RulesAdjudicationRequest] = []

    def adjudicate(self, request: RulesAdjudicationRequest) -> RulesAdjudication:
        self.requests.append(request)
        return self.adjudications.pop(0)


class FakeNarratorAgent:
    """Narrator stub that returns formatted narration."""

    def __init__(self, scene_tone: str | None = None) -> None:
        self.frames: list[NarrationFrame] = []
        self._scene_tone = scene_tone

    def narrate(self, frame: NarrationFrame) -> Narration:
        self.frames.append(frame)
        outcomes = " ".join(frame.resolved_outcomes)
        tone = self._scene_tone if frame.purpose == "scene_opening" else None
        return Narration(
            text=f"{frame.purpose}: {outcomes}".strip(),
            audience="player",
            scene_tone=tone,
        )

    def declare_npc_intent_from_json(self, context_json: str) -> str:
        return "The enemy advances."

    def assess_combat_from_json(self, state_json: str) -> CombatAssessment:
        return CombatAssessment(
            combat_active=False,
            outcome=CombatOutcome(
                short_description="End",
                full_description="Combat concluded.",
            ),
        )

    def review_crit_from_json(self, context_json: str) -> CritReview:
        return CritReview(approved=True)


class FakeDice:
    def __init__(self, totals: list[int]) -> None:
        self.totals = list(totals)
        self.expressions: list[str] = []

    def __call__(self, expression: str) -> int:
        self.expressions.append(expression)
        return self.totals.pop(0)


def _decision(next_step: str, **overrides: object) -> OrchestrationDecision:
    fields: dict[str, object] = {
        "next_step": next_step,
        "next_actor": None,
        "requires_rules_resolution": False,
        "recommended_check": None,
        "phase_transition": None,
        "player_prompt": None,
        "reason_summary": "test decision",
    }
    fields.update(overrides)
    return OrchestrationDecision(**fields)


def _default_player() -> ActorState:
    return ActorState(
        actor_id="pc:talia",
        name="Talia",
        actor_type=ActorType.PC,
        hp_current=12,
        hp_max=12,
        armor_class=18,
        strength=18,
        dexterity=14,
        constitution=16,
        intelligence=10,
        wisdom=12,
        charisma=8,
        proficiency_bonus=3,
        initiative_bonus=5,
        speed=30,
        attacks_per_action=2,
        action_options=("Attack", "Dodge", "Dash"),
        ac_breakdown=("Chainmail: 16",),
    )


def _default_npc() -> ActorState:
    return ActorState(
        actor_id="npc:goblin-scout",
        name="Goblin Scout",
        actor_type=ActorType.NPC,
        hp_current=7,
        hp_max=7,
        armor_class=15,
        strength=8,
        dexterity=14,
        constitution=10,
        intelligence=10,
        wisdom=8,
        charisma=8,
        proficiency_bonus=2,
        initiative_bonus=2,
        speed=30,
        attacks_per_action=1,
        action_options=("Attack",),
        ac_breakdown=(),
        personality="Cowardly and opportunistic.",
    )


def _scene_opening_repository(tmp_path: Path) -> StateRepository:
    actor_repo = ActorRepository(tmp_path)
    actor_repo.save(_default_player())
    encounter_repo = EncounterRepository(tmp_path)
    encounter_repo.save(
        EncounterState(
            encounter_id="goblin-camp",
            phase=EncounterPhase.SCENE_OPENING,
            setting="A ruined roadside camp.",
            actors={"pc:talia": _default_player(), "npc:goblin-scout": _default_npc()},
            hidden_facts={"goblin_disposition": "neutral"},
        )
    )
    return StateRepository(actor_repo=actor_repo, encounter_repo=encounter_repo)


def _social_repository(tmp_path: Path, goblin_hp: int = 7) -> StateRepository:
    actor_repo = ActorRepository(tmp_path)
    actor_repo.save(_default_player())
    goblin = replace(_default_npc(), hp_current=goblin_hp)
    encounter_repo = EncounterRepository(tmp_path)
    encounter_repo.save(
        EncounterState(
            encounter_id="goblin-camp",
            phase=EncounterPhase.SOCIAL,
            setting="A ruined roadside camp.",
            actors={"pc:talia": _default_player(), "npc:goblin-scout": goblin},
        )
    )
    return StateRepository(actor_repo=actor_repo, encounter_repo=encounter_repo)


def _combat_repository(tmp_path: Path, goblin_hp: int = 0) -> StateRepository:
    """Return a repository in COMBAT phase.

    goblin_hp defaults to 0 so combat ends after Talia passes her first turn,
    allowing ScriptedIO exhaustion ("exit") to terminate cleanly.
    """
    actor_repo = ActorRepository(tmp_path)
    actor_repo.save(_default_player())
    goblin = replace(_default_npc(), hp_current=goblin_hp)
    encounter_repo = EncounterRepository(tmp_path)
    encounter_repo.save(
        EncounterState(
            encounter_id="goblin-camp",
            phase=EncounterPhase.COMBAT,
            setting="A ruined roadside camp.",
            actors={"pc:talia": _default_player(), "npc:goblin-scout": goblin},
            combat_turns=(
                InitiativeTurn(actor_id="pc:talia", initiative_roll=18),
                InitiativeTurn(actor_id="npc:goblin-scout", initiative_roll=12),
            ),
            outcome="combat",
        )
    )
    return StateRepository(actor_repo=actor_repo, encounter_repo=encounter_repo)


def _mock_decision_agent(
    decisions: list[OrchestrationDecision] | None = None,
) -> MagicMock:
    mock_agent = MagicMock()
    decision_queue = list(decisions or [])

    def _run_sync(input_json: str) -> MagicMock:
        result = MagicMock()
        if decision_queue:
            result.output = decision_queue.pop(0)
        else:
            result.output = OrchestrationDecision(
                next_step="narrate_scene",
                requires_rules_resolution=False,
                reason_summary="default",
            )
        return result

    mock_agent.run_sync.side_effect = _run_sync
    return mock_agent


def _mock_combat_intent_agent(
    intents: list[str] | None = None,
) -> MagicMock:
    mock_agent = MagicMock()
    intent_queue = list(intents or [])

    def _run_sync(input_json: str) -> MagicMock:
        result = MagicMock()
        result.output = CombatIntent(
            intent=intent_queue.pop(0) if intent_queue else "end_turn"
        )
        return result

    mock_agent.run_sync.side_effect = _run_sync
    return mock_agent


def _orchestrator(  # noqa: PLR0913
    tmp_path: Path,
    *,
    state_repository: StateRepository | None = None,
    decisions: list[OrchestrationDecision] | None = None,
    rules_agent: FakeRulesAgent | None = None,
    narrator_agent: FakeNarratorAgent | None = None,
    roll_dice: FakeDice | None = None,
    io: ScriptedIO | None = None,
    combat_intents: list[str] | None = None,
) -> EncounterOrchestrator:
    return EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            state=state_repository or _scene_opening_repository(tmp_path),
        ),
        agents=OrchestratorAgents(
            rules=rules_agent or FakeRulesAgent(),
            narrator=narrator_agent or FakeNarratorAgent(),
        ),
        tools=OrchestratorTools(roll_dice=roll_dice or FakeDice([])),
        io=io or ScriptedIO([], on_exhaust="exit"),
        _decision_agent=_mock_decision_agent(decisions),
        _combat_intent_agent=_mock_combat_intent_agent(combat_intents),
    )


def test_run_encounter_returns_peaceful_output_status_and_recap(
    tmp_path: Path,
) -> None:
    # Utility commands (status, what happened) are available both before and after
    # the encounter-ending action.  The loop uses `continue` (not `break`) after
    # phase=ENCOUNTER_COMPLETE, so input ordering is not constrained here.
    rules_agent = FakeRulesAgent()
    narrator_agent = FakeNarratorAgent()
    orchestrator = _orchestrator(
        tmp_path,
        decisions=[
            _decision(
                "complete_encounter",
                reason_summary="The offer of peace works.",
            )
        ],
        rules_agent=rules_agent,
        narrator_agent=narrator_agent,
        io=ScriptedIO(
            ["status", "what happened", "Hello there. I do not want trouble."],
        ),
    )

    result = orchestrator.run_encounter(encounter_id="goblin-camp")

    assert result == EncounterRunResult(
        encounter_id="goblin-camp",
        output_text=result.output_text,
        completed=True,
    )
    assert "complete_encounter: peaceful" in result.output_text
    assert "status_response:" in result.output_text
    assert "recap_response:" in result.output_text
    state = orchestrator.current_state()
    assert state is not None
    assert state.outcome == "peaceful"
    assert rules_agent.requests == []


def test_status_routes_to_status_frame_without_rules_adjudication(
    tmp_path: Path,
) -> None:
    rules_agent = FakeRulesAgent()
    narrator_agent = FakeNarratorAgent()
    orchestrator = _orchestrator(
        tmp_path,
        state_repository=_social_repository(tmp_path),
        rules_agent=rules_agent,
        narrator_agent=narrator_agent,
        io=ScriptedIO(["status", "exit"]),
    )

    result = orchestrator.run_encounter(encounter_id="goblin-camp")

    assert "status_response:" in result.output_text
    assert rules_agent.requests == []
    assert narrator_agent.frames[-1].purpose == "status_response"
    assert any(
        "Talia" in summary and "HP 12/12" in summary
        for summary in narrator_agent.frames[-1].public_actor_summaries
    )


def test_empty_input_is_ignored_and_look_around_routes_to_visible_scene(
    tmp_path: Path,
) -> None:
    rules_agent = FakeRulesAgent()
    narrator_agent = FakeNarratorAgent()
    orchestrator = _orchestrator(
        tmp_path,
        state_repository=_social_repository(tmp_path),
        rules_agent=rules_agent,
        narrator_agent=narrator_agent,
        io=ScriptedIO(["", "   ", "look around", "exit"]),
    )

    result = orchestrator.run_encounter(encounter_id="goblin-camp")

    assert "status_response:" in result.output_text
    assert rules_agent.requests == []
    assert narrator_agent.frames[-1].resolved_outcomes[0] == "A ruined roadside camp."
    assert narrator_agent.frames[-1].allowed_disclosures == (
        "setting",
        "visible actors",
    )


def test_friendly_social_input_can_complete_peacefully_through_decision(
    tmp_path: Path,
) -> None:
    orchestrator = _orchestrator(
        tmp_path,
        state_repository=_social_repository(tmp_path),
        decisions=[
            _decision(
                "complete_encounter",
                reason_summary="The offer of peace works.",
            )
        ],
        io=ScriptedIO(["I lower my weapon and ask to pass peacefully."]),
    )

    result = orchestrator.run_encounter(encounter_id="goblin-camp")

    assert result.completed is True
    assert "peaceful" in result.output_text
    state = orchestrator.current_state()
    assert state is not None
    assert state.outcome == "peaceful"


def test_social_check_uses_rules_agent_and_applies_effects(tmp_path: Path) -> None:
    rules_agent = FakeRulesAgent(
        [
            RulesAdjudication(
                is_legal=True,
                action_type="social_check",
                summary="The goblins accept the offer.",
                roll_requests=(
                    RollRequest(
                        owner="player",
                        visibility=RollVisibility.PUBLIC,
                        expression="1d20+1",
                        purpose="calm goblins",
                    ),
                ),
                state_effects=(
                    StateEffect(
                        effect_type="set_encounter_outcome",
                        target="encounter:goblin-camp",
                        value="de-escalated",
                    ),
                ),
                reasoning_summary="The check succeeds.",
            ),
        ]
    )
    roll_dice = FakeDice([16])
    narrator_agent = FakeNarratorAgent()
    orchestrator = _orchestrator(
        tmp_path,
        state_repository=_social_repository(tmp_path),
        decisions=[
            _decision(
                "adjudicate_action",
                requires_rules_resolution=True,
                recommended_check="Persuasion",
            ),
        ],
        rules_agent=rules_agent,
        narrator_agent=narrator_agent,
        roll_dice=roll_dice,
        io=ScriptedIO(["I try to calm them down.", "exit"]),
    )

    result = orchestrator.run_encounter(encounter_id="goblin-camp")

    request = rules_agent.requests[0]
    state = orchestrator.current_state()
    assert request.allowed_outcomes == (
        "success",
        "failure",
        "complication",
        "peaceful",
    )
    assert request.check_hints == ("Persuasion",)
    assert roll_dice.expressions == ["1d20+1"]
    assert state is not None
    assert state.outcome == "de-escalated"
    assert "Roll: calm goblins = 16." in narrator_agent.frames[-1].resolved_outcomes
    assert "social_resolution:" in result.output_text


def test_social_check_with_outcome_emits_encounter_completed_event(
    tmp_path: Path,
) -> None:
    memory = FakeMemoryRepository()
    rules_agent = FakeRulesAgent(
        [
            RulesAdjudication(
                is_legal=True,
                action_type="social_check",
                summary="The goblins back away.",
                roll_requests=(),
                state_effects=(
                    StateEffect(
                        effect_type="set_encounter_outcome",
                        target="encounter:goblin-camp",
                        value="de-escalated",
                    ),
                ),
                reasoning_summary="The check succeeds.",
            ),
        ]
    )
    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            state=_social_repository(tmp_path),
            memory=memory,
        ),
        agents=OrchestratorAgents(
            rules=rules_agent,
            narrator=FakeNarratorAgent(),
        ),
        tools=OrchestratorTools(roll_dice=FakeDice([])),
        io=ScriptedIO(["I try to calm them down.", "exit"]),
        _decision_agent=_mock_decision_agent(
            [_decision("adjudicate_action", requires_rules_resolution=True)]
        ),
    )

    orchestrator.run_encounter(encounter_id="goblin-camp")

    completed = [e for e in memory.events if e.get("type") == "encounter_completed"]
    assert len(completed) == 1
    assert completed[0]["outcome"] == "de-escalated"


def test_social_check_without_outcome_does_not_emit_encounter_completed_event(
    tmp_path: Path,
) -> None:
    memory = FakeMemoryRepository()
    rules_agent = FakeRulesAgent(
        [
            RulesAdjudication(
                is_legal=True,
                action_type="social_check",
                summary="They look uncertain.",
                roll_requests=(),
                state_effects=(),
                reasoning_summary="Neutral outcome.",
            ),
        ]
    )
    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            state=_social_repository(tmp_path),
            memory=memory,
        ),
        agents=OrchestratorAgents(
            rules=rules_agent,
            narrator=FakeNarratorAgent(),
        ),
        tools=OrchestratorTools(roll_dice=FakeDice([])),
        io=ScriptedIO(["I try to calm them down.", "exit"]),
        _decision_agent=_mock_decision_agent(
            [_decision("adjudicate_action", requires_rules_resolution=True)]
        ),
    )

    orchestrator.run_encounter(encounter_id="goblin-camp")

    completed = [e for e in memory.events if e.get("type") == "encounter_completed"]
    assert completed == []


@pytest.mark.parametrize(
    ("next_step", "purpose"),
    [("npc_dialogue", "npc_dialogue"), ("narrate_scene", "scene_response")],
)
def test_non_combat_narrative_decisions_route_to_narrator(
    tmp_path: Path, next_step: str, purpose: str
) -> None:
    narrator_agent = FakeNarratorAgent()
    orchestrator = _orchestrator(
        tmp_path,
        state_repository=_social_repository(tmp_path),
        decisions=[_decision(next_step, reason_summary="The goblin answers.")],
        narrator_agent=narrator_agent,
        io=ScriptedIO(["I ask what they want.", "exit"]),
    )

    result = orchestrator.run_encounter(encounter_id="goblin-camp")

    assert narrator_agent.frames[-1].purpose == purpose
    assert narrator_agent.frames[-1].resolved_outcomes == ("The goblin answers.",)
    assert f"{purpose}: The goblin answers." in result.output_text


def test_aggressive_input_rolls_initiative_then_enters_combat(
    tmp_path: Path,
) -> None:
    """Entering combat transitions phase and delegates to CombatOrchestrator.

    goblin_hp=0 ensures combat ends as soon as Talia passes (all NPCs down).
    """
    roll_dice = FakeDice([18, 12])
    narrator_agent = FakeNarratorAgent()
    # io provides the social input that triggers combat, then "end turn" for Talia's
    # first (and only) combat turn so the CombatOrchestrator pass-phrase terminates.
    orchestrator = _orchestrator(
        tmp_path,
        state_repository=_social_repository(tmp_path, goblin_hp=0),
        decisions=[_decision("roll_initiative")],
        narrator_agent=narrator_agent,
        roll_dice=roll_dice,
        io=ScriptedIO(["I draw steel and rush the goblin.", "end turn"]),
    )

    result = orchestrator.run_encounter(encounter_id="goblin-camp")

    state = orchestrator.current_state()
    assert result.completed is False
    assert state is not None
    assert state.phase is EncounterPhase.COMBAT
    assert state.outcome == "combat"
    assert roll_dice.expressions == ["1d20+2", "1d20+2"]
    assert narrator_agent.frames[-1].purpose == "combat_start"


def test_enter_combat_emits_encounter_completed_event(tmp_path: Path) -> None:
    # goblin_hp=0 so combat ends after Talia passes, event fires before that.
    memory = FakeMemoryRepository()
    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            state=_social_repository(tmp_path, goblin_hp=0),
            memory=memory,
        ),
        agents=OrchestratorAgents(
            rules=FakeRulesAgent(),
            narrator=FakeNarratorAgent(),
        ),
        tools=OrchestratorTools(roll_dice=FakeDice([18, 12])),
        io=ScriptedIO(["I draw steel and rush the goblin.", "end turn"]),
        _decision_agent=_mock_decision_agent([_decision("roll_initiative")]),
        _combat_intent_agent=_mock_combat_intent_agent(["end_turn"]),
    )

    orchestrator.run_encounter(encounter_id="goblin-camp")

    completed_events = [
        e for e in memory.events if e.get("type") == "encounter_completed"
    ]
    assert len(completed_events) == 1
    assert completed_events[0]["outcome"] == "combat"
    assert completed_events[0]["encounter_id"] == "goblin-camp"


def test_combat_orchestrator_is_invoked_when_phase_is_combat(tmp_path: Path) -> None:
    """CombatOrchestrator takes over when EncounterState is already in COMBAT phase."""
    rules_agent = FakeRulesAgent(
        [
            RulesAdjudication(
                is_legal=True,
                action_type="attack",
                summary="Talia hits the goblin for 7 damage.",
                roll_requests=(),
                state_effects=(
                    StateEffect(
                        effect_type="change_hp",
                        target="npc:goblin-scout",
                        value=-7,
                    ),
                ),
                reasoning_summary="attack resolved",
            ),
        ]
    )
    orchestrator = _orchestrator(
        tmp_path,
        # goblin starts at 7 HP; killing blow ends combat
        state_repository=_combat_repository(tmp_path, goblin_hp=7),
        rules_agent=rules_agent,
        io=ScriptedIO(["I attack the goblin scout.", "end turn"]),
        combat_intents=["combat_action", "end_turn"],
    )

    orchestrator.run_encounter(encounter_id="goblin-camp")

    state = orchestrator.current_state()
    assert state is not None
    assert state.actors["npc:goblin-scout"].hp_current == 0
    assert len(rules_agent.requests) == 1


def test_invalid_orchestration_decision_raises_without_saving_mutated_state(
    tmp_path: Path,
) -> None:
    repository = _social_repository(tmp_path)
    original_state = repository.load().encounter
    orchestrator = _orchestrator(
        tmp_path,
        state_repository=repository,
        decisions=[_decision("summon_dragon")],
        io=ScriptedIO(["I try something confusing."]),
    )

    with pytest.raises(
        ValueError,
        match="invalid orchestration next_step: summon_dragon",
    ):
        orchestrator.run_encounter(encounter_id="goblin-camp")

    assert repository.load().encounter == original_state


def test_invalid_decision_after_scene_opening_leaves_default_state_unchanged(
    tmp_path: Path,
) -> None:
    repository = _scene_opening_repository(tmp_path)
    original_state = repository.load().encounter
    orchestrator = _orchestrator(
        tmp_path,
        state_repository=repository,
        decisions=[_decision("summon_dragon")],
        io=ScriptedIO(["I try something confusing."]),
    )

    with pytest.raises(
        ValueError,
        match="invalid orchestration next_step: summon_dragon",
    ):
        orchestrator.run_encounter(encounter_id="goblin-camp")

    assert repository.load().encounter == original_state


@pytest.mark.parametrize(
    ("decision", "player_input", "expected_outcome"),
    [
        (
            _decision(
                "complete_encounter",
                phase_transition="de-escalated",
            ),
            "I lower my weapon.",
            "de-escalated",
        ),
        (
            _decision(
                "complete_encounter",
                reason_summary="The offer of peace works.",
            ),
            "I negotiate.",
            "peaceful",
        ),
        (
            _decision("complete_encounter"),
            "I leave the ravine.",
            "complete",
        ),
    ],
)
def test_completion_outcome_fallbacks(
    tmp_path: Path,
    decision: OrchestrationDecision,
    player_input: str,
    expected_outcome: str,
) -> None:
    orchestrator = _orchestrator(
        tmp_path,
        state_repository=_social_repository(tmp_path),
        decisions=[decision],
        io=ScriptedIO([player_input]),
    )

    result = orchestrator.run_encounter(encounter_id="goblin-camp")

    assert result.completed is True
    state = orchestrator.current_state()
    assert state is not None
    assert state.outcome == expected_outcome
    assert f"complete_encounter: {expected_outcome}" in result.output_text


def test_save_and_quit_persists_active_encounter_and_records_event(
    tmp_path: Path,
) -> None:
    memory_repository = FakeMemoryRepository()
    repository = _social_repository(tmp_path)
    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            state=repository,
            memory=memory_repository,
        ),
        agents=OrchestratorAgents(
            rules=FakeRulesAgent(),
            narrator=FakeNarratorAgent(),
        ),
        tools=OrchestratorTools(roll_dice=FakeDice([])),
        io=ScriptedIO(["save and quit"]),
        _decision_agent=_mock_decision_agent(),
    )

    result = orchestrator.run_encounter(encounter_id="goblin-camp")

    state = repository.load().encounter
    assert result.completed is False
    assert "saved" in result.output_text.lower()
    assert state is not None
    assert state.phase is EncounterPhase.SOCIAL
    assert memory_repository.events == [
        {
            "type": "encounter_saved",
            "encounter_id": "goblin-camp",
            "phase": "social",
            "outcome": None,
        }
    ]


def test_save_and_quit_without_memory_repository_does_not_raise(
    tmp_path: Path,
) -> None:
    repository = _social_repository(tmp_path)
    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            state=repository,
        ),
        agents=OrchestratorAgents(
            rules=FakeRulesAgent(),
            narrator=FakeNarratorAgent(),
        ),
        tools=OrchestratorTools(roll_dice=FakeDice([])),
        io=ScriptedIO(["save and quit"]),
        _decision_agent=_mock_decision_agent(),
    )

    result = orchestrator.run_encounter(encounter_id="goblin-camp")

    assert result.completed is False
    assert "saved" in result.output_text.lower()


def test_completed_encounter_records_durable_event(tmp_path: Path) -> None:
    memory_repository = FakeMemoryRepository()
    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            state=_social_repository(tmp_path),
            memory=memory_repository,
        ),
        agents=OrchestratorAgents(
            rules=FakeRulesAgent(),
            narrator=FakeNarratorAgent(),
        ),
        tools=OrchestratorTools(roll_dice=FakeDice([])),
        io=ScriptedIO(["I offer peace."]),
        _decision_agent=_mock_decision_agent(
            [
                _decision(
                    "complete_encounter",
                    reason_summary="The offer of peace works.",
                )
            ]
        ),
    )

    orchestrator.run_encounter(encounter_id="goblin-camp")

    assert memory_repository.events == [
        {
            "type": "encounter_completed",
            "encounter_id": "goblin-camp",
            "outcome": "peaceful",
        }
    ]


def test_adjudicate_action_routing_replaces_adjudicate_action(tmp_path: Path) -> None:
    """The renamed next_step 'adjudicate_action' must route to rules adjudication."""
    rules_agent = FakeRulesAgent(
        [
            RulesAdjudication(
                is_legal=True,
                action_type="social_check",
                summary="Success.",
                reasoning_summary="ok",
            ),
        ]
    )
    orchestrator = _orchestrator(
        tmp_path,
        state_repository=_social_repository(tmp_path),
        decisions=[
            _decision(
                "adjudicate_action",
                requires_rules_resolution=True,
                recommended_check="Persuasion",
            ),
        ],
        rules_agent=rules_agent,
        io=ScriptedIO(["I ask them to stand down.", "exit"]),
    )
    orchestrator.run_encounter(encounter_id="goblin-camp")
    assert len(rules_agent.requests) == 1


def test_save_and_quit_during_combat_saves_state_and_records_event(
    tmp_path: Path,
) -> None:
    """save and quit in combat should persist state and record encounter_saved."""
    memory_repository = FakeMemoryRepository()
    repository = _combat_repository(tmp_path, goblin_hp=7)
    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            state=repository,
            memory=memory_repository,
        ),
        agents=OrchestratorAgents(
            rules=FakeRulesAgent(),
            narrator=FakeNarratorAgent(),
        ),
        tools=OrchestratorTools(roll_dice=FakeDice([])),
        io=ScriptedIO(["save and quit"]),
        _decision_agent=_mock_decision_agent(),
        _combat_intent_agent=_mock_combat_intent_agent(["exit_session"]),
    )

    orchestrator.run_encounter(encounter_id="goblin-camp")

    persisted = repository.load().encounter
    assert persisted is not None
    assert persisted.phase is EncounterPhase.COMBAT
    assert memory_repository.events == [
        {
            "type": "encounter_saved",
            "encounter_id": "goblin-camp",
            "phase": "combat",
            "outcome": "combat",
        }
    ]


def test_exit_during_combat_saves_state(tmp_path: Path) -> None:
    """'exit' in combat must persist state — same as 'save and quit'."""
    repository = _combat_repository(tmp_path, goblin_hp=7)
    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            state=repository,
        ),
        agents=OrchestratorAgents(
            rules=FakeRulesAgent(),
            narrator=FakeNarratorAgent(),
        ),
        tools=OrchestratorTools(roll_dice=FakeDice([])),
        io=ScriptedIO(["exit"]),
        _decision_agent=_mock_decision_agent(),
        _combat_intent_agent=_mock_combat_intent_agent(["exit_session"]),
    )

    orchestrator.run_encounter(encounter_id="goblin-camp")

    state_after = repository.load().encounter
    assert state_after is not None
    assert state_after.phase is EncounterPhase.COMBAT


def test_actor_summary_includes_name_hp_and_ac(tmp_path: Path) -> None:
    """The orchestrator decision input shows actor name, HP, and AC in summaries."""
    mock_agent = _mock_decision_agent([_decision("npc_dialogue")])

    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            state=_social_repository(tmp_path),
        ),
        agents=OrchestratorAgents(
            rules=FakeRulesAgent(),
            narrator=FakeNarratorAgent(),
        ),
        tools=OrchestratorTools(roll_dice=FakeDice([])),
        io=ScriptedIO(["Hello.", "exit"]),
        _decision_agent=mock_agent,
    )
    orchestrator.run_encounter(encounter_id="goblin-camp")

    call_args = mock_agent.run_sync.call_args_list[0]
    input_dict = json.loads(call_args[0][0])
    summaries = input_dict.get("public_actor_summaries", [])
    assert any("Talia" in s and "HP" in s and "AC" in s for s in summaries)


def test_scene_tone_persisted_on_state_after_scene_opening(tmp_path: Path) -> None:
    """scene_tone returned from opening narration should be saved on EncounterState."""
    repository = _scene_opening_repository(tmp_path)
    narrator = FakeNarratorAgent(scene_tone="eerie and quiet")
    orchestrator = _orchestrator(
        tmp_path,
        state_repository=repository,
        narrator_agent=narrator,
        io=ScriptedIO(["save and quit"]),
    )

    orchestrator.run_encounter(encounter_id="goblin-camp")

    saved = repository.load().encounter
    assert saved is not None
    assert saved.scene_tone == "eerie and quiet"


def test_tone_guidance_propagated_to_subsequent_narration_frames(
    tmp_path: Path,
) -> None:
    """NarrationFrames built after scene_opening should carry tone_guidance."""
    narrator = FakeNarratorAgent(scene_tone="tense and dark")
    orchestrator = _orchestrator(
        tmp_path,
        state_repository=_scene_opening_repository(tmp_path),
        narrator_agent=narrator,
        io=ScriptedIO(["status", "exit"]),
    )

    orchestrator.run_encounter(encounter_id="goblin-camp")

    # frames[0] is scene_opening; frames[1] is the status frame
    assert narrator.frames[0].purpose == "scene_opening"
    non_opening = [f for f in narrator.frames if f.purpose != "scene_opening"]
    assert len(non_opening) >= 1
    assert all(f.tone_guidance == "tense and dark" for f in non_opening)


def test_exit_during_social_phase_saves_state(tmp_path: Path) -> None:
    """'exit' in social phase must persist state — not silently discard it."""
    state_repo = _social_repository(tmp_path)
    orchestrator = _orchestrator(
        tmp_path,
        state_repository=state_repo,
        io=ScriptedIO(["exit"]),
    )
    orchestrator.run_encounter(encounter_id="goblin-camp")
    # State must have been persisted
    loaded = state_repo.load()
    assert loaded.encounter is not None
    assert loaded.encounter.phase is EncounterPhase.SOCIAL


def test_non_utility_input_after_completion_exits_loop_without_further_agent_calls(
    tmp_path: Path,
) -> None:
    """Non-utility input typed after ENCOUNTER_COMPLETE is a no-op and exits the loop.

    The guard at the top of the non-combat branch breaks immediately when the
    encounter is already complete, so neither the rules agent nor the narrator
    should be called for the trailing junk input.
    """
    rules_agent = FakeRulesAgent()
    narrator_agent = FakeNarratorAgent()
    orchestrator = _orchestrator(
        tmp_path,
        state_repository=_social_repository(tmp_path),
        decisions=[
            _decision(
                "complete_encounter",
                reason_summary="The offer of peace works.",
            )
        ],
        rules_agent=rules_agent,
        narrator_agent=narrator_agent,
        # First input completes the encounter; second is non-utility junk.
        io=ScriptedIO(
            ["I lower my weapon and ask to pass peacefully.", "let us celebrate"]
        ),
    )

    result = orchestrator.run_encounter(encounter_id="goblin-camp")

    assert result.completed is True
    assert result.encounter_id == "goblin-camp"
    # No rules adjudication should ever have been triggered.
    assert rules_agent.requests == []
    # The narrator was called only for the completion narration, not for the
    # trailing junk input.  The last frame purpose must be the completion frame,
    # not any new action frame spawned by "let us celebrate".
    assert narrator_agent.frames[-1].purpose == "complete_encounter"


def test_encounter_orchestrator_raises_if_neither_adapter_nor_decision_agent_provided(
    tmp_path: Path,
) -> None:
    """EncounterOrchestrator without adapter= or _decision_agent= must raise."""
    with pytest.raises(ValueError, match="EncounterOrchestrator requires adapter="):
        EncounterOrchestrator(
            repositories=OrchestratorRepositories(
                state=_scene_opening_repository(tmp_path),
            ),
            agents=OrchestratorAgents(
                rules=FakeRulesAgent(),
                narrator=FakeNarratorAgent(),
            ),
            tools=OrchestratorTools(roll_dice=FakeDice([])),
            io=ScriptedIO([], on_exhaust="exit"),
        )
