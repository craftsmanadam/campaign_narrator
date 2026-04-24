"""Unit tests for the encounter-loop campaign orchestrator."""

from __future__ import annotations

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
    EncounterPhase,
    EncounterState,
    InitiativeTurn,
    IntentCategory,
    Narration,
    NarrationFrame,
    PlayerIntent,
    RollRequest,
    RollVisibility,
    RulesAdjudication,
    RulesAdjudicationRequest,
    StateEffect,
)
from campaignnarrator.orchestrators.actor_summaries import (
    actor_narrative_summary as _actor_narrative_summary,
)
from campaignnarrator.orchestrators.encounter_orchestrator import (
    EncounterOrchestrator,
    OrchestratorAgents,
    OrchestratorRepositories,
)
from campaignnarrator.repositories.actor_repository import ActorRepository
from campaignnarrator.repositories.encounter_repository import EncounterRepository
from campaignnarrator.repositories.state_repository import StateRepository

from tests.conftest import ScriptedIO

_DAMAGED_GOBLIN_HP = 2


class FakeMemoryRepository:
    def __init__(
        self,
        prior_context: list[str] | None = None,
        *,
        game_state: object | None = None,
        exchange_buffer: tuple[str, ...] = (),
    ) -> None:
        self.events: list[dict[str, object]] = []
        self.narratives: list[tuple[str, dict[str, str]]] = []
        self._prior_context: list[str] = prior_context or []
        self.retrieve_queries: list[str] = []
        self.staged_game_state: object | None = None
        self._initial_game_state: object | None = game_state
        self.exchange_updates: list[tuple[str, str]] = []
        self.staged_narrations: list[tuple[str, dict]] = []
        self.combat_round_logs: list[str] = []
        self.encounter_memory_cleared: bool = False
        self._exchange_buffer: tuple[str, ...] = exchange_buffer

    def append_event(self, event: Mapping[str, object]) -> None:
        self.events.append(dict(event))

    def store_narrative(self, text: str, metadata: dict[str, str]) -> None:
        self.narratives.append((text, metadata))

    def retrieve_relevant(self, query: str, *, limit: int = 5) -> list[str]:
        self.retrieve_queries.append(query)
        return self._prior_context[:limit]

    def update_game_state(self, game_state: object) -> None:
        self.staged_game_state = game_state

    def load_game_state(self) -> object:
        """Return most recently staged state, or initial state passed at construction."""
        if self.staged_game_state is not None:
            return self.staged_game_state
        if self._initial_game_state is not None:
            return self._initial_game_state
        msg = (
            "FakeMemoryRepository has no game state — pass game_state= at construction"
            " or call update_game_state() first"
        )
        raise RuntimeError(msg)

    def update_exchange(self, player_input: str, narrator_output: str) -> None:
        self.exchange_updates.append((player_input, narrator_output))

    def get_exchange_buffer(self) -> tuple[str, ...]:
        return self._exchange_buffer

    def stage_narration(self, text: str, metadata: dict) -> None:
        self.staged_narrations.append((text, metadata))

    def log_combat_round(self, entry: str) -> None:
        self.combat_round_logs.append(entry)

    def clear_combat_memory(self) -> None:
        self.combat_round_logs.clear()

    def clear_encounter_memory(self) -> None:
        self.encounter_memory_cleared = True

    def persist(self) -> None:
        pass


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

    def summarize_encounter_partial(self, encounter: object) -> str:
        return "Partial summary of the interrupted encounter."

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


class FakePlayerIntentAgent:
    """PlayerIntentAgent stub that returns scripted intents in sequence."""

    def __init__(self, intents: list[PlayerIntent] | None = None) -> None:
        self._intents = list(intents or [])
        self.calls: list[str] = []

    def classify(
        self,
        raw_text: str,
        *,
        phase: EncounterPhase,
        setting: str,
        recent_events: tuple[str, ...],
        actor_summaries: tuple[str, ...],
    ) -> PlayerIntent:
        self.calls.append(raw_text)
        if self._intents:
            return self._intents.pop(0)
        return PlayerIntent(category=IntentCategory.SAVE_EXIT, reason="exhausted")


def _intent(category: IntentCategory, **kwargs: object) -> PlayerIntent:
    fields: dict[str, object] = {"category": category}
    fields.update(kwargs)
    return PlayerIntent(**fields)


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


def _social_repository(
    tmp_path: Path,
    goblin_hp: int = 7,
    public_events: tuple[str, ...] = (),
) -> StateRepository:
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
            public_events=public_events,
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


def _orchestrator(
    tmp_path: Path,
    *,
    state_repository: StateRepository | None = None,
    intents: list[PlayerIntent] | None = None,
    rules_agent: FakeRulesAgent | None = None,
    narrator_agent: FakeNarratorAgent | None = None,
    io: ScriptedIO | None = None,
    combat_intents: list[str] | None = None,
) -> EncounterOrchestrator:
    repo = state_repository or _scene_opening_repository(tmp_path)
    initial_game_state = repo.load()
    fake_memory = FakeMemoryRepository(game_state=initial_game_state)
    return EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=fake_memory,
        ),
        agents=OrchestratorAgents(
            rules=rules_agent or FakeRulesAgent(),
            narrator=narrator_agent or FakeNarratorAgent(),
        ),
        io=io or ScriptedIO([], on_exhaust="exit"),
        _player_intent_agent=FakePlayerIntentAgent(intents),
        _combat_intent_agent=_mock_combat_intent_agent(combat_intents),
    )


def test_run_encounter_returns_peaceful_output_status_and_recap(
    tmp_path: Path,
) -> None:
    rules_agent = FakeRulesAgent(
        [
            RulesAdjudication(
                is_legal=True,
                action_type="social_check",
                summary="The offer of peace works.",
                roll_requests=(),
                state_effects=(
                    StateEffect(
                        effect_type="set_encounter_outcome",
                        target="encounter:goblin-camp",
                        value="peaceful",
                    ),
                ),
                reasoning_summary="The check succeeds.",
            )
        ]
    )
    narrator_agent = FakeNarratorAgent()
    orchestrator = _orchestrator(
        tmp_path,
        state_repository=_social_repository(tmp_path),
        intents=[
            _intent(IntentCategory.STATUS),
            _intent(IntentCategory.RECAP),
            _intent(IntentCategory.SKILL_CHECK, check_hint="Persuasion"),
        ],
        rules_agent=rules_agent,
        narrator_agent=narrator_agent,
        io=ScriptedIO(["status", "what happened", "Hello, I do not want trouble."]),
    )

    result = orchestrator.run_encounter(encounter_id="goblin-camp")

    assert "social_resolution:" in result.output_text
    assert "status_response:" in result.output_text
    assert "recap_response:" in result.output_text
    state = orchestrator.current_state()
    assert state is not None
    assert state.outcome == "peaceful"


def test_status_routes_to_status_frame_without_rules_adjudication(
    tmp_path: Path,
) -> None:
    rules_agent = FakeRulesAgent()
    narrator_agent = FakeNarratorAgent()
    orchestrator = _orchestrator(
        tmp_path,
        state_repository=_social_repository(tmp_path),
        intents=[_intent(IntentCategory.STATUS)],
        rules_agent=rules_agent,
        narrator_agent=narrator_agent,
        io=ScriptedIO(["status", "exit"]),
    )

    result = orchestrator.run_encounter(encounter_id="goblin-camp")

    assert "status_response:" in result.output_text
    assert rules_agent.requests == []
    assert narrator_agent.frames[-1].purpose == "status_response"
    assert any(
        "Talia" in summary and "uninjured" in summary
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
        intents=[_intent(IntentCategory.LOOK_AROUND)],
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


def test_social_check_uses_rules_agent_and_applies_effects(
    tmp_path: Path, mocker: object
) -> None:
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
    mock_roll = mocker.patch(  # type: ignore[attr-defined]
        "campaignnarrator.domain.models._roll", side_effect=[16]
    )
    narrator_agent = FakeNarratorAgent()
    orchestrator = _orchestrator(
        tmp_path,
        state_repository=_social_repository(tmp_path),
        intents=[
            _intent(IntentCategory.SKILL_CHECK, check_hint="Persuasion"),
        ],
        rules_agent=rules_agent,
        narrator_agent=narrator_agent,
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
    assert [c.args[0] for c in mock_roll.call_args_list] == ["1d20+1"]
    assert state is not None
    assert state.outcome == "de-escalated"
    assert "Roll: calm goblins = 16" in narrator_agent.frames[-1].resolved_outcomes
    assert narrator_agent.frames[-1].player_action == "I try to calm them down."
    assert "social_resolution:" in result.output_text


def test_social_check_with_outcome_emits_encounter_completed_event(
    tmp_path: Path,
) -> None:
    initial_state = _social_repository(tmp_path).load()
    memory = FakeMemoryRepository(game_state=initial_state)
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
            memory=memory,
        ),
        agents=OrchestratorAgents(
            rules=rules_agent,
            narrator=FakeNarratorAgent(),
        ),
        io=ScriptedIO(["I try to calm them down.", "exit"]),
        _player_intent_agent=FakePlayerIntentAgent(
            [_intent(IntentCategory.SKILL_CHECK, check_hint="Persuasion")]
        ),
    )

    orchestrator.run_encounter(encounter_id="goblin-camp")

    completed = [e for e in memory.events if e.get("type") == "encounter_completed"]
    assert len(completed) == 1
    assert completed[0]["outcome"] == "de-escalated"


def test_social_check_without_outcome_does_not_emit_encounter_completed_event(
    tmp_path: Path,
) -> None:
    initial_state = _social_repository(tmp_path).load()
    memory = FakeMemoryRepository(game_state=initial_state)
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
            memory=memory,
        ),
        agents=OrchestratorAgents(
            rules=rules_agent,
            narrator=FakeNarratorAgent(),
        ),
        io=ScriptedIO(["I try to calm them down.", "exit"]),
        _player_intent_agent=FakePlayerIntentAgent(
            [_intent(IntentCategory.SKILL_CHECK, check_hint="Persuasion")]
        ),
    )

    orchestrator.run_encounter(encounter_id="goblin-camp")

    completed = [e for e in memory.events if e.get("type") == "encounter_completed"]
    assert completed == []


@pytest.mark.parametrize(
    ("category", "purpose"),
    [
        (IntentCategory.NPC_DIALOGUE, "npc_dialogue"),
        (IntentCategory.SCENE_OBSERVATION, "scene_response"),
    ],
)
def test_non_combat_narrative_decisions_route_to_narrator(
    tmp_path: Path, category: IntentCategory, purpose: str
) -> None:
    narrator_agent = FakeNarratorAgent()
    orchestrator = _orchestrator(
        tmp_path,
        state_repository=_social_repository(tmp_path),
        intents=[_intent(category)],
        narrator_agent=narrator_agent,
        io=ScriptedIO(["I ask what they want.", "exit"]),
    )

    result = orchestrator.run_encounter(encounter_id="goblin-camp")

    assert narrator_agent.frames[-1].purpose == purpose
    assert narrator_agent.frames[-1].player_action == "I ask what they want."
    assert purpose in result.output_text


def test_aggressive_input_rolls_initiative_then_enters_combat(
    tmp_path: Path, mocker: object
) -> None:
    """Entering combat transitions phase and delegates to CombatOrchestrator.

    goblin_hp=0 ensures combat ends as soon as Talia passes (all NPCs down).
    """
    # Actors are rolled in sorted(actor_id) order: "npc:goblin-scout" before "pc:talia".
    # Give goblin a lower roll (12) so Talia (18) wins initiative and goes first.
    mock_roll = mocker.patch(  # type: ignore[attr-defined]
        "campaignnarrator.orchestrators.encounter_orchestrator.roll",
        side_effect=[12, 18],
    )
    narrator_agent = FakeNarratorAgent()
    # io provides the social input that triggers combat, then "end turn" for Talia's
    # first (and only) combat turn so the CombatOrchestrator pass-phrase terminates.
    orchestrator = _orchestrator(
        tmp_path,
        state_repository=_social_repository(tmp_path, goblin_hp=0),
        intents=[_intent(IntentCategory.HOSTILE_ACTION)],
        narrator_agent=narrator_agent,
        io=ScriptedIO(["I draw steel and rush the goblin.", "end turn"]),
    )

    result = orchestrator.run_encounter(encounter_id="goblin-camp")

    state = orchestrator.current_state()
    assert result.completed is False
    assert state is not None
    assert state.phase is EncounterPhase.COMBAT
    assert state.outcome == "combat"
    assert [c.args[0] for c in mock_roll.call_args_list] == ["1d20+2", "1d20+5"]
    assert narrator_agent.frames[-1].purpose == "combat_start"


def test_enter_combat_emits_encounter_completed_event(
    tmp_path: Path, mocker: object
) -> None:
    # goblin_hp=0 so combat ends after Talia passes, event fires before that.
    initial_state = _social_repository(tmp_path, goblin_hp=0).load()
    memory = FakeMemoryRepository(game_state=initial_state)
    # Actors rolled in sorted(actor_id) order: goblin first, Talia second.
    # Goblin gets 12, Talia gets 18 → Talia wins initiative and goes first.
    mocker.patch(  # type: ignore[attr-defined]
        "campaignnarrator.orchestrators.encounter_orchestrator.roll",
        side_effect=[12, 18],
    )
    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=memory,
        ),
        agents=OrchestratorAgents(
            rules=FakeRulesAgent(),
            narrator=FakeNarratorAgent(),
        ),
        io=ScriptedIO(["I draw steel and rush the goblin.", "end turn"]),
        _player_intent_agent=FakePlayerIntentAgent(
            [_intent(IntentCategory.HOSTILE_ACTION)]
        ),
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


def test_save_and_quit_persists_active_encounter_and_records_event(
    tmp_path: Path,
) -> None:
    repository = _social_repository(tmp_path)
    initial_state = repository.load()
    memory_repository = FakeMemoryRepository(game_state=initial_state)
    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=memory_repository,
        ),
        agents=OrchestratorAgents(
            rules=FakeRulesAgent(),
            narrator=FakeNarratorAgent(),
        ),
        io=ScriptedIO(["save and quit"]),
        _player_intent_agent=FakePlayerIntentAgent(),
    )

    result = orchestrator.run_encounter(encounter_id="goblin-camp")

    assert result.completed is False
    assert "saved" in result.output_text.lower()
    assert memory_repository.events == [
        {
            "type": "encounter_saved",
            "encounter_id": "goblin-camp",
            "phase": "social",
            "outcome": None,
        }
    ]


def test_save_and_quit_completes_without_raising(
    tmp_path: Path,
) -> None:
    initial_state = _social_repository(tmp_path).load()
    memory_repository = FakeMemoryRepository(game_state=initial_state)
    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=memory_repository,
        ),
        agents=OrchestratorAgents(
            rules=FakeRulesAgent(),
            narrator=FakeNarratorAgent(),
        ),
        io=ScriptedIO(["save and quit"]),
        _player_intent_agent=FakePlayerIntentAgent(),
    )

    result = orchestrator.run_encounter(encounter_id="goblin-camp")

    assert result.completed is False
    assert "saved" in result.output_text.lower()


def test_completed_encounter_records_durable_event(tmp_path: Path) -> None:
    initial_state = _social_repository(tmp_path).load()
    memory_repository = FakeMemoryRepository(game_state=initial_state)
    rules_agent = FakeRulesAgent(
        [
            RulesAdjudication(
                is_legal=True,
                action_type="social_check",
                summary="The offer of peace works.",
                roll_requests=(),
                state_effects=(
                    StateEffect(
                        effect_type="set_encounter_outcome",
                        target="encounter:goblin-camp",
                        value="peaceful",
                    ),
                    StateEffect(
                        effect_type="set_phase",
                        target="encounter:goblin-camp",
                        value="encounter_complete",
                    ),
                ),
                reasoning_summary="The check succeeds.",
            ),
        ]
    )
    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=memory_repository,
        ),
        agents=OrchestratorAgents(
            rules=rules_agent,
            narrator=FakeNarratorAgent(),
        ),
        io=ScriptedIO(["I offer peace."]),
        _player_intent_agent=FakePlayerIntentAgent(
            [
                _intent(IntentCategory.SKILL_CHECK, check_hint="Persuasion"),
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
    """SKILL_CHECK intent must route to rules adjudication."""
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
        intents=[
            _intent(IntentCategory.SKILL_CHECK, check_hint="Persuasion"),
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
    repository = _combat_repository(tmp_path, goblin_hp=7)
    initial_state = repository.load()
    memory_repository = FakeMemoryRepository(game_state=initial_state)
    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=memory_repository,
        ),
        agents=OrchestratorAgents(
            rules=FakeRulesAgent(),
            narrator=FakeNarratorAgent(),
        ),
        io=ScriptedIO(["save and quit"]),
        _player_intent_agent=FakePlayerIntentAgent(),
        _combat_intent_agent=_mock_combat_intent_agent(["exit_session"]),
    )

    orchestrator.run_encounter(encounter_id="goblin-camp")

    assert memory_repository.events == [
        {
            "type": "encounter_saved",
            "encounter_id": "goblin-camp",
            "phase": "combat",
            "outcome": "combat",
        }
    ]


def test_exit_during_combat_saves_state(tmp_path: Path) -> None:
    """'exit' in combat must persist state via memory repository."""
    initial_state = _combat_repository(tmp_path, goblin_hp=7).load()
    memory_repository = FakeMemoryRepository(game_state=initial_state)
    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=memory_repository,
        ),
        agents=OrchestratorAgents(
            rules=FakeRulesAgent(),
            narrator=FakeNarratorAgent(),
        ),
        io=ScriptedIO(["exit"]),
        _player_intent_agent=FakePlayerIntentAgent(),
        _combat_intent_agent=_mock_combat_intent_agent(["exit_session"]),
    )

    orchestrator.run_encounter(encounter_id="goblin-camp")

    state_after = memory_repository.load_game_state().encounter
    assert state_after is not None
    assert state_after.phase is EncounterPhase.COMBAT


def _make_actor(
    name: str,
    hp_current: int,
    hp_max: int,
    actor_type: ActorType = ActorType.PC,
    **kwargs: object,
) -> ActorState:
    """Helper to build a minimal ActorState for summary tests."""
    return ActorState(
        actor_id=f"pc:{name.lower()}",
        name=name,
        actor_type=actor_type,
        hp_max=hp_max,
        hp_current=hp_current,
        armor_class=16,
        strength=16,
        dexterity=12,
        constitution=14,
        intelligence=10,
        wisdom=10,
        charisma=10,
        proficiency_bonus=2,
        initiative_bonus=1,
        speed=30,
        attacks_per_action=1,
        action_options=("Attack",),
        ac_breakdown=("chain mail",),
        **kwargs,
    )


def test_narrative_summary_uninjured() -> None:
    actor = _make_actor("Talia", hp_current=20, hp_max=20)
    result = _actor_narrative_summary(actor)
    assert "20" not in result
    assert "16" not in result  # no AC
    assert "uninjured" in result
    assert "Talia" in result


def test_narrative_summary_lightly_wounded() -> None:
    actor = _make_actor("Talia", hp_current=14, hp_max=20)  # 70% = lightly wounded
    result = _actor_narrative_summary(actor)
    assert "lightly wounded" in result


def test_narrative_summary_bloodied() -> None:
    actor = _make_actor("Talia", hp_current=9, hp_max=20)  # 45% = bloodied
    result = _actor_narrative_summary(actor)
    assert "bloodied" in result
    assert "9" not in result


def test_narrative_summary_barely_standing() -> None:
    actor = _make_actor("Goblin", hp_current=1, hp_max=7)  # ~14% = barely standing
    result = _actor_narrative_summary(actor)
    assert "barely standing" in result


def test_narrative_summary_defeated() -> None:
    actor = _make_actor("Goblin", hp_current=0, hp_max=7)
    result = _actor_narrative_summary(actor)
    assert "defeated" in result


def test_narrative_summary_includes_conditions() -> None:
    actor = _make_actor("Talia", hp_current=15, hp_max=20, conditions=("poisoned",))
    result = _actor_narrative_summary(actor)
    assert "poisoned" in result


def test_narrative_summary_no_hp_numbers() -> None:
    actor = _make_actor("Talia", hp_current=15, hp_max=20)
    result = _actor_narrative_summary(actor)
    assert "15/20" not in result
    assert "AC" not in result


def test_narrative_summary_pc_includes_player_tag() -> None:
    actor = _make_actor("Gareth", hp_current=20, hp_max=20, actor_type=ActorType.PC)
    result = _actor_narrative_summary(actor)
    assert "player" in result
    assert "Gareth" in result
    assert "uninjured" in result


def test_narrative_summary_npc_excludes_player_tag() -> None:
    actor = _make_actor("Goblin", hp_current=7, hp_max=7, actor_type=ActorType.NPC)
    result = _actor_narrative_summary(actor)
    assert "player" not in result
    assert "uninjured" in result


def test_actor_summary_includes_name_and_injury_status(tmp_path: Path) -> None:
    """The orchestrator passes actor name and injury status to the intent classifier."""
    captured_summaries: list[tuple[str, ...]] = []

    class CapturingIntentAgent(FakePlayerIntentAgent):
        def classify(
            self,
            raw_text: str,
            *,
            phase: EncounterPhase,
            setting: str,
            recent_events: tuple[str, ...],
            actor_summaries: tuple[str, ...],
        ) -> PlayerIntent:
            captured_summaries.append(actor_summaries)
            return super().classify(
                raw_text,
                phase=phase,
                setting=setting,
                recent_events=recent_events,
                actor_summaries=actor_summaries,
            )

    initial_state = _social_repository(tmp_path).load()
    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=FakeMemoryRepository(game_state=initial_state),
        ),
        agents=OrchestratorAgents(
            rules=FakeRulesAgent(),
            narrator=FakeNarratorAgent(),
        ),
        io=ScriptedIO(["Hello.", "exit"]),
        _player_intent_agent=CapturingIntentAgent(
            [_intent(IntentCategory.NPC_DIALOGUE)]
        ),
    )
    orchestrator.run_encounter(encounter_id="goblin-camp")

    assert captured_summaries, "classify was not called with actor summaries"
    summaries = captured_summaries[0]
    assert any("Talia" in s and "uninjured" in s for s in summaries)
    assert not any("HP" in s or "AC" in s for s in summaries)


def test_scene_tone_persisted_on_state_after_scene_opening(tmp_path: Path) -> None:
    """scene_tone returned from opening narration should be saved on EncounterState."""
    narrator = FakeNarratorAgent(scene_tone="eerie and quiet")
    orchestrator = _orchestrator(
        tmp_path,
        state_repository=_scene_opening_repository(tmp_path),
        narrator_agent=narrator,
        io=ScriptedIO(["save and quit"]),
    )

    orchestrator.run_encounter(encounter_id="goblin-camp")

    saved = orchestrator.current_state()
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
        intents=[_intent(IntentCategory.STATUS)],
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

    The guard at the top of the loop breaks immediately when the encounter is
    already complete, so the trailing "let us celebrate" input is never read
    and neither rules adjudication nor narration should fire for it.
    """
    rules_agent = FakeRulesAgent(
        [
            RulesAdjudication(
                is_legal=True,
                action_type="social_check",
                summary="They stand aside and let you pass.",
                roll_requests=(),
                state_effects=(
                    StateEffect(
                        effect_type="set_encounter_outcome",
                        target="encounter:goblin-camp",
                        value="peaceful",
                    ),
                    StateEffect(
                        effect_type="set_phase",
                        target="encounter:goblin-camp",
                        value="encounter_complete",
                    ),
                ),
                reasoning_summary="Persuasion succeeds.",
            )
        ]
    )
    narrator_agent = FakeNarratorAgent()
    orchestrator = _orchestrator(
        tmp_path,
        state_repository=_social_repository(tmp_path),
        intents=[
            _intent(IntentCategory.SKILL_CHECK, check_hint="Persuasion"),
        ],
        rules_agent=rules_agent,
        narrator_agent=narrator_agent,
        # First input completes the encounter; second is non-utility junk that
        # must never be consumed because the loop exits after completion.
        io=ScriptedIO(
            ["I lower my weapon and ask to pass peacefully.", "let us celebrate"]
        ),
    )

    result = orchestrator.run_encounter(encounter_id="goblin-camp")

    assert result.completed is True
    assert result.encounter_id == "goblin-camp"
    # Rules were called exactly once for the completing action.
    assert len(rules_agent.requests) == 1
    # The narrator was called only for the completion narration; the last frame
    # must be social_resolution, not any frame spawned by "let us celebrate".
    assert narrator_agent.frames[-1].purpose == "social_resolution"


def test_encounter_orchestrator_raises_if_neither_adapter_nor_player_intent_agent_provided(
    tmp_path: Path,
) -> None:
    """EncounterOrchestrator without adapter= or _player_intent_agent= must raise."""
    initial_state = _scene_opening_repository(tmp_path).load()
    with pytest.raises(ValueError, match="EncounterOrchestrator requires adapter="):
        EncounterOrchestrator(
            repositories=OrchestratorRepositories(
                memory=FakeMemoryRepository(game_state=initial_state),
            ),
            agents=OrchestratorAgents(
                rules=FakeRulesAgent(),
                narrator=FakeNarratorAgent(),
            ),
            io=ScriptedIO([], on_exhaust="exit"),
        )


def test_thinking_indicator_displayed_before_action_processing(
    tmp_path: Path,
) -> None:
    """'...' must appear in output immediately after player submits an action."""
    io = ScriptedIO(["I look around.", "exit"])
    orchestrator = _orchestrator(
        tmp_path,
        intents=[_intent(IntentCategory.SCENE_OBSERVATION)],
        io=io,
    )
    orchestrator.run_encounter(encounter_id="goblin-camp")
    assert any("..." in msg for msg in io.displayed)


def test_considering_rules_displayed_before_adjudication(
    tmp_path: Path,
) -> None:
    """'Considering the rules...' must appear when action routes to adjudication."""
    io = ScriptedIO(["I try to pick the lock.", "exit"])
    orchestrator = _orchestrator(
        tmp_path,
        intents=[
            _intent(IntentCategory.SKILL_CHECK, check_hint="Dexterity"),
        ],
        io=io,
    )
    orchestrator.run_encounter(encounter_id="goblin-camp")
    assert any("Considering the rules" in msg for msg in io.displayed)


def test_resume_encounter_displays_recap_before_prompt(tmp_path: Path) -> None:
    """When resuming an encounter with prior events, a recap must appear before the prompt."""
    io = ScriptedIO(["exit"])
    orchestrator = _orchestrator(
        tmp_path,
        state_repository=_social_repository(
            tmp_path,
            public_events=("The goblin scout eyed you warily.",),
        ),
        io=io,
    )
    result = orchestrator.run_encounter(encounter_id="goblin-camp")
    assert "recap_response" in result.output_text


def test_fresh_encounter_does_not_show_recap(tmp_path: Path) -> None:
    """A brand-new SCENE_OPENING encounter must show the scene narration, not a recap."""
    io = ScriptedIO(["exit"])
    orchestrator = _orchestrator(
        tmp_path,
        state_repository=_scene_opening_repository(tmp_path),
        io=io,
    )
    result = orchestrator.run_encounter(encounter_id="goblin-camp")
    assert "scene_opening" in result.output_text
    assert "recap_response" not in result.output_text


def test_save_exit_intent_saves_state_and_breaks_loop(tmp_path: Path) -> None:
    initial_state = _social_repository(tmp_path).load()
    memory = FakeMemoryRepository(game_state=initial_state)
    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=memory,
        ),
        agents=OrchestratorAgents(
            rules=FakeRulesAgent(),
            narrator=FakeNarratorAgent(),
        ),
        io=ScriptedIO(["save and exit the game"]),
        _player_intent_agent=FakePlayerIntentAgent([_intent(IntentCategory.SAVE_EXIT)]),
    )

    result = orchestrator.run_encounter(encounter_id="goblin-camp")

    assert result.completed is False
    saved = [e for e in memory.events if e.get("type") == "encounter_saved"]
    assert len(saved) == 1
    assert saved[0]["encounter_id"] == "goblin-camp"


def test_narration_stored_to_memory_during_encounter(tmp_path: Path) -> None:
    """Every narrate() call must store a record in the memory repository."""
    initial_state = _scene_opening_repository(tmp_path).load()
    memory = FakeMemoryRepository(game_state=initial_state)
    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=memory,
        ),
        agents=OrchestratorAgents(
            rules=FakeRulesAgent(),
            narrator=FakeNarratorAgent(),
        ),
        io=ScriptedIO(["Hello there.", "exit"]),
        _player_intent_agent=FakePlayerIntentAgent(
            [_intent(IntentCategory.NPC_DIALOGUE)]
        ),
    )

    orchestrator.run_encounter(encounter_id="goblin-camp")

    narration_entries = [
        m for _, m in memory.narratives if m.get("event_type") == "narration"
    ]
    # At minimum: scene_opening + npc_dialogue
    min_expected = 2
    assert len(narration_entries) >= min_expected
    assert all(m["encounter_id"] == "goblin-camp" for m in narration_entries)


def test_save_exit_stores_partial_summary_in_memory(tmp_path: Path) -> None:
    """save-and-quit must generate and store a partial encounter summary."""
    initial_state = _scene_opening_repository(tmp_path).load()
    memory = FakeMemoryRepository(game_state=initial_state)
    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=memory,
        ),
        agents=OrchestratorAgents(
            rules=FakeRulesAgent(),
            narrator=FakeNarratorAgent(),
        ),
        io=ScriptedIO(["save and quit"]),
        _player_intent_agent=FakePlayerIntentAgent([_intent(IntentCategory.SAVE_EXIT)]),
    )

    orchestrator.run_encounter(encounter_id="goblin-camp")

    partial = [
        m
        for _, m in memory.staged_narrations
        if m.get("event_type") == "encounter_partial_summary"
    ]
    assert len(partial) == 1
    assert partial[0]["encounter_id"] == "goblin-camp"


def test_public_roll_event_is_displayed_to_player_in_social_path(
    tmp_path: Path, mocker: object
) -> None:
    """A PUBLIC roll_request from rules adjudication must be displayed to the player."""
    rules_agent = FakeRulesAgent(
        [
            RulesAdjudication(
                is_legal=True,
                action_type="social_check",
                summary="The goblins are convinced.",
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
                reasoning_summary="Persuasion succeeds.",
            ),
        ]
    )
    mocker.patch(  # type: ignore[attr-defined]
        "campaignnarrator.orchestrators.encounter_orchestrator.roll", return_value=15
    )
    io = ScriptedIO(["I appeal to their sense of reason.", "exit"])
    orchestrator = _orchestrator(
        tmp_path,
        state_repository=_social_repository(tmp_path),
        intents=[_intent(IntentCategory.SKILL_CHECK, check_hint="Persuasion")],
        rules_agent=rules_agent,
        io=io,
    )

    orchestrator.run_encounter(encounter_id="goblin-camp")

    assert any("Roll:" in msg for msg in io.displayed)


def test_resume_recap_populates_prior_narrative_context_from_memory(
    tmp_path: Path,
) -> None:
    """On resume, prior session context is retrieved from memory and passed to narrator."""
    prior_summary = "You searched the woods and found a mysterious mirror."
    narrator_agent = FakeNarratorAgent()

    encounter_repo = EncounterRepository(tmp_path)
    actor_repo = ActorRepository(tmp_path)
    actor_repo.save(_default_player())
    encounter_repo.save(
        EncounterState(
            encounter_id="goblin-camp",
            phase=EncounterPhase.SOCIAL,
            setting="A ruined roadside camp.",
            actors={"pc:talia": _default_player()},
            public_events=("Roll: Investigation = 15.",),  # triggers recap path
        )
    )
    state_repo = StateRepository(actor_repo=actor_repo, encounter_repo=encounter_repo)
    memory_repository = FakeMemoryRepository(
        prior_context=[prior_summary],
        game_state=state_repo.load(),
    )
    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=memory_repository,
        ),
        agents=OrchestratorAgents(
            rules=FakeRulesAgent(),
            narrator=narrator_agent,
        ),
        io=ScriptedIO(["exit"]),
        _player_intent_agent=FakePlayerIntentAgent(),
    )

    orchestrator.run_encounter(encounter_id="goblin-camp")

    # The recap frame must have prior_narrative_context populated from memory
    recap_frames = [f for f in narrator_agent.frames if f.purpose == "recap_response"]
    assert recap_frames, "Expected at least one recap_response frame"
    assert prior_summary in recap_frames[0].prior_narrative_context


def test_resume_recap_includes_exchange_buffer_in_prior_context(
    tmp_path: Path,
) -> None:
    """On resume, exchange buffer entries appear in the prior_narrative_context."""
    narrator_agent = FakeNarratorAgent()

    encounter_repo = EncounterRepository(tmp_path)
    actor_repo = ActorRepository(tmp_path)
    actor_repo.save(_default_player())
    encounter_repo.save(
        EncounterState(
            encounter_id="goblin-camp",
            phase=EncounterPhase.SOCIAL,
            setting="A ruined roadside camp.",
            actors={"pc:talia": _default_player()},
            public_events=("Roll: Investigation = 15.",),
        )
    )
    state_repo = StateRepository(actor_repo=actor_repo, encounter_repo=encounter_repo)
    memory_repository = FakeMemoryRepository(
        game_state=state_repo.load(),
        exchange_buffer=("I search the camp.", "You find charred goblin bones."),
    )
    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(memory=memory_repository),
        agents=OrchestratorAgents(rules=FakeRulesAgent(), narrator=narrator_agent),
        io=ScriptedIO(["exit"]),
        _player_intent_agent=FakePlayerIntentAgent(),
    )

    orchestrator.run_encounter(encounter_id="goblin-camp")

    recap_frames = [f for f in narrator_agent.frames if f.purpose == "recap_response"]
    assert recap_frames, "Expected at least one recap_response frame"
    assert "I search the camp." in recap_frames[0].prior_narrative_context
    assert "You find charred goblin bones." in recap_frames[0].prior_narrative_context


class TestSaveExitPath:
    def test_save_exit_stages_partial_summary(self, tmp_path: Path) -> None:
        """SAVE_EXIT must call stage_narration() — not store_narrative() directly."""
        state_repo = _social_repository(tmp_path)
        initial_state = state_repo.load()
        fake_memory = FakeMemoryRepository(game_state=initial_state)
        orchestrator = EncounterOrchestrator(
            repositories=OrchestratorRepositories(memory=fake_memory),
            agents=OrchestratorAgents(
                rules=FakeRulesAgent(),
                narrator=FakeNarratorAgent(),
            ),
            io=ScriptedIO(["save and quit"]),
            _player_intent_agent=FakePlayerIntentAgent(
                [_intent(IntentCategory.SAVE_EXIT)]
            ),
        )
        orchestrator.run_encounter(encounter_id="goblin-camp")
        assert any(
            m[1].get("event_type") == "encounter_partial_summary"
            for m in fake_memory.staged_narrations
        )

    def test_save_exit_updates_game_state(self, tmp_path: Path) -> None:
        """SAVE_EXIT must call update_game_state() so SIGTERM has current state."""
        state_repo = _social_repository(tmp_path)
        initial_state = state_repo.load()
        fake_memory = FakeMemoryRepository(game_state=initial_state)
        orchestrator = EncounterOrchestrator(
            repositories=OrchestratorRepositories(memory=fake_memory),
            agents=OrchestratorAgents(
                rules=FakeRulesAgent(),
                narrator=FakeNarratorAgent(),
            ),
            io=ScriptedIO(["save and quit"]),
            _player_intent_agent=FakePlayerIntentAgent(
                [_intent(IntentCategory.SAVE_EXIT)]
            ),
        )
        orchestrator.run_encounter(encounter_id="goblin-camp")
        assert fake_memory.staged_game_state is not None


class TestApplyAction:
    def test_apply_action_updates_exchange_buffer(self, tmp_path: Path) -> None:
        """After a non-combat action, update_exchange() is called with input + narration."""
        state_repo = _social_repository(tmp_path)
        initial_state = state_repo.load()
        fake_memory = FakeMemoryRepository(game_state=initial_state)
        orchestrator = EncounterOrchestrator(
            repositories=OrchestratorRepositories(memory=fake_memory),
            agents=OrchestratorAgents(
                rules=FakeRulesAgent(),
                narrator=FakeNarratorAgent(),
            ),
            io=ScriptedIO(["I ask what they want.", "exit"]),
            _player_intent_agent=FakePlayerIntentAgent(
                [_intent(IntentCategory.NPC_DIALOGUE)]
            ),
        )
        orchestrator.run_encounter(encounter_id="goblin-camp")
        assert len(fake_memory.exchange_updates) >= 1
        assert any(
            pair[0] == "I ask what they want." for pair in fake_memory.exchange_updates
        )

    def test_scene_opening_updates_exchange_buffer(self, tmp_path: Path) -> None:
        """Scene opening narration is appended with empty player input."""
        state_repo = _scene_opening_repository(tmp_path)
        initial_state = state_repo.load()
        fake_memory = FakeMemoryRepository(game_state=initial_state)
        orchestrator = EncounterOrchestrator(
            repositories=OrchestratorRepositories(memory=fake_memory),
            agents=OrchestratorAgents(
                rules=FakeRulesAgent(),
                narrator=FakeNarratorAgent(),
            ),
            io=ScriptedIO([], on_exhaust="exit"),
            _player_intent_agent=FakePlayerIntentAgent([]),
        )
        orchestrator.run_encounter(encounter_id="goblin-camp")
        assert any(pair[0] == "" for pair in fake_memory.exchange_updates)


class TestHiddenConditionClearing:
    """hidden condition is cleared when the player speaks or takes a hostile action."""

    def _repo_with_hidden_player(
        self, tmp_path: Path
    ) -> tuple[StateRepository, FakeMemoryRepository]:
        actor_repo = ActorRepository(tmp_path)
        hidden_player = replace(_default_player(), conditions=("hidden",))
        actor_repo.save(hidden_player)
        encounter_repo = EncounterRepository(tmp_path)
        encounter_repo.save(
            EncounterState(
                encounter_id="goblin-camp",
                phase=EncounterPhase.SOCIAL,
                setting="A ruined roadside camp.",
                actors={"pc:talia": hidden_player, "npc:goblin-scout": _default_npc()},
            )
        )
        state_repo = StateRepository(
            actor_repo=actor_repo, encounter_repo=encounter_repo
        )
        initial_state = state_repo.load()
        return state_repo, FakeMemoryRepository(game_state=initial_state)

    def test_npc_dialogue_clears_hidden_from_player(self, tmp_path: Path) -> None:
        _, fake_memory = self._repo_with_hidden_player(tmp_path)
        orchestrator = EncounterOrchestrator(
            repositories=OrchestratorRepositories(memory=fake_memory),
            agents=OrchestratorAgents(
                rules=FakeRulesAgent(), narrator=FakeNarratorAgent()
            ),
            io=ScriptedIO(["Hello there.", "exit"]),
            _player_intent_agent=FakePlayerIntentAgent(
                [_intent(IntentCategory.NPC_DIALOGUE)]
            ),
        )
        orchestrator.run_encounter(encounter_id="goblin-camp")
        state = fake_memory.staged_game_state.encounter  # type: ignore[union-attr]
        player = state.actors["pc:talia"]
        assert not player.has_condition("hidden")

    def test_hostile_action_clears_hidden_from_player(
        self, tmp_path: Path, mocker: object
    ) -> None:
        mocker.patch(  # type: ignore[attr-defined]
            "campaignnarrator.orchestrators.encounter_orchestrator.roll",
            side_effect=[12, 18],
        )
        goblin = replace(_default_npc(), hp_current=0)
        actor_repo = ActorRepository(tmp_path)
        hidden_player = replace(_default_player(), conditions=("hidden",))
        actor_repo.save(hidden_player)
        encounter_repo = EncounterRepository(tmp_path)
        encounter_repo.save(
            EncounterState(
                encounter_id="goblin-camp",
                phase=EncounterPhase.SOCIAL,
                setting="A ruined roadside camp.",
                actors={"pc:talia": hidden_player, "npc:goblin-scout": goblin},
            )
        )
        state_repo = StateRepository(
            actor_repo=actor_repo, encounter_repo=encounter_repo
        )
        initial_state = state_repo.load()
        fake_memory = FakeMemoryRepository(game_state=initial_state)
        orchestrator = EncounterOrchestrator(
            repositories=OrchestratorRepositories(memory=fake_memory),
            agents=OrchestratorAgents(
                rules=FakeRulesAgent(), narrator=FakeNarratorAgent()
            ),
            io=ScriptedIO(["I attack!", "end turn"]),
            _player_intent_agent=FakePlayerIntentAgent(
                [_intent(IntentCategory.HOSTILE_ACTION)]
            ),
            _combat_intent_agent=_mock_combat_intent_agent(["end_turn"]),
        )
        orchestrator.run_encounter(encounter_id="goblin-camp")
        state = fake_memory.staged_game_state.encounter  # type: ignore[union-attr]
        player = state.actors["pc:talia"]
        assert not player.has_condition("hidden")

    def test_npc_dialogue_without_hidden_leaves_state_unchanged(
        self, tmp_path: Path
    ) -> None:
        state_repo = _social_repository(tmp_path)
        initial_state = state_repo.load()
        fake_memory = FakeMemoryRepository(game_state=initial_state)
        orchestrator = EncounterOrchestrator(
            repositories=OrchestratorRepositories(memory=fake_memory),
            agents=OrchestratorAgents(
                rules=FakeRulesAgent(), narrator=FakeNarratorAgent()
            ),
            io=ScriptedIO(["Hello.", "exit"]),
            _player_intent_agent=FakePlayerIntentAgent(
                [_intent(IntentCategory.NPC_DIALOGUE)]
            ),
        )
        orchestrator.run_encounter(encounter_id="goblin-camp")
        state = fake_memory.staged_game_state.encounter  # type: ignore[union-attr]
        player = state.actors["pc:talia"]
        assert not player.has_condition("hidden")
