"""Unit tests for the encounter-loop campaign orchestrator."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from campaignnarrator.domain.models import (
    ActorRegistry,
    ActorState,
    ActorType,
    CampaignState,
    CombatAssessment,
    CombatIntent,
    CombatOutcome,
    CombatState,
    CombatStatus,
    EncounterPhase,
    EncounterState,
    GameState,
    IntentCategory,
    Narration,
    NarrationFrame,
    NpcPresence,
    NpcPresenceStatus,
    PlayerIntent,
    RollRequest,
    RollVisibility,
    RulesAdjudication,
    RulesAdjudicationRequest,
    StateEffect,
    TurnOrder,
)
from campaignnarrator.orchestrators.encounter_orchestrator import (
    EncounterOrchestrator,
    OrchestratorAgents,
    OrchestratorRepositories,
)
from campaignnarrator.repositories.game_state_repository import GameStateRepository
from campaignnarrator.repositories.player_repository import PlayerRepository

from tests.conftest import ScriptedIO
from tests.fixtures.fighter_talia import TALIA
from tests.fixtures.goblin_scout import make_goblin_scout

_DAMAGED_GOBLIN_HP = 2


class FakeMemoryRepository:
    def __init__(
        self,
        prior_context: list[str] | None = None,
        *,
        exchange_buffer: tuple[str, ...] = (),
    ) -> None:
        self.events: list[dict[str, object]] = []
        self.narratives: list[tuple[str, dict[str, str]]] = []
        self._prior_context: list[str] = prior_context or []
        self.retrieve_queries: list[str] = []
        self.exchange_updates: list[tuple[str, str]] = []
        self.staged_narrations: list[tuple[str, dict]] = []
        self.combat_round_logs: list[str] = []
        self.encounter_memory_cleared: bool = False
        self._exchange_buffer: tuple[str, ...] = exchange_buffer

    def append_event(self, event: Mapping[str, object]) -> None:
        self.events.append(dict(event))

    def store_narrative(self, text: str, metadata: dict[str, str]) -> None:
        self.narratives.append((text, metadata))

    def retrieve_relevant(
        self, query: str, *, campaign_id: str, limit: int = 5
    ) -> list[str]:
        self.retrieve_queries.append(query)
        return self._prior_context[:limit]

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


class FakeGameStateRepository:
    """In-memory fake for GameStateRepository."""

    def __init__(self, initial: GameState) -> None:
        self._cache: list[GameState] = [initial]

    def load(self) -> GameState:
        return self._cache[-1]

    def persist(self, gs: GameState) -> None:
        self._cache.append(gs)


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

    def __init__(
        self,
        scene_tone: str | None = None,
        *,
        encounter_complete: bool = False,
        next_location_hint: str | None = None,
        completion_reason: str | None = None,
        traveling_actor_ids: tuple[str, ...] = (),
    ) -> None:
        self.frames: list[NarrationFrame] = []
        self._scene_tone = scene_tone
        self._encounter_complete = encounter_complete
        self._next_location_hint = next_location_hint
        self._completion_reason = completion_reason
        self._traveling_actor_ids = traveling_actor_ids

    def set_campaign_context(self, campaign_id: str) -> None:
        pass

    def narrate(self, frame: NarrationFrame) -> Narration:
        self.frames.append(frame)
        outcomes = " ".join(frame.resolved_outcomes)
        tone = self._scene_tone if frame.purpose == "scene_opening" else None
        return Narration(
            text=f"{frame.purpose}: {outcomes}".strip(),
            audience="player",
            scene_tone=tone,
            encounter_complete=self._encounter_complete,
            next_location_hint=self._next_location_hint,
            completion_reason=self._completion_reason,
            traveling_actor_ids=self._traveling_actor_ids,
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
        npc_presences: tuple[NpcPresence, ...] = (),
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


def _default_campaign() -> CampaignState:
    return CampaignState(
        campaign_id="test-campaign",
        name="Test Campaign",
        setting="A test world.",
        narrator_personality="Neutral",
        hidden_goal="None",
        bbeg_name="None",
        bbeg_description="None",
        milestones=(),
        current_milestone_index=0,
        starting_level=1,
        target_level=5,
        player_brief="You are a test character.",
        player_actor_id="pc:talia",
    )


_ENCOUNTER_PATH = Path("encounters") / "active.json"


def _write_encounter(root: Path, encounter: EncounterState) -> Path:
    """Write encounter to <root>/encounters/active.json and return the path."""
    path = root / _ENCOUNTER_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(encounter.to_dict(), indent=2, sort_keys=True) + "\n")
    return path


def _build_game_state(
    player_repo: PlayerRepository,
    encounter_path: Path,
    npc_actors: tuple[ActorState, ...] = (),
) -> GameState:
    """Build GameState with all encounter actors bootstrapped into registry."""
    encounter: EncounterState | None = None
    if encounter_path.exists():
        encounter = EncounterState.from_dict(json.loads(encounter_path.read_text()))
    player = player_repo.load()
    registry = ActorRegistry().with_actor(player)
    for actor in npc_actors:
        registry = registry.with_actor(actor)
    return GameState(
        campaign=_default_campaign(), encounter=encounter, actor_registry=registry
    )


def _scene_opening_game_state(tmp_path: Path) -> GameState:
    actor_repo = PlayerRepository(tmp_path)
    actor_repo.save(_default_player())
    enc_path = _write_encounter(
        tmp_path,
        EncounterState(
            encounter_id="goblin-camp",
            phase=EncounterPhase.SCENE_OPENING,
            setting="A ruined roadside camp.",
            actor_ids=("pc:talia", "npc:goblin-scout"),
            player_actor_id="pc:talia",
            hidden_facts={"goblin_disposition": "neutral"},
        ),
    )
    return _build_game_state(actor_repo, enc_path, npc_actors=(_default_npc(),))


def _social_game_state(
    tmp_path: Path,
    goblin_hp: int = 7,
    public_events: tuple[str, ...] = (),
) -> GameState:
    actor_repo = PlayerRepository(tmp_path)
    actor_repo.save(_default_player())
    goblin = replace(_default_npc(), hp_current=goblin_hp)
    enc_path = _write_encounter(
        tmp_path,
        EncounterState(
            encounter_id="goblin-camp",
            phase=EncounterPhase.SOCIAL,
            setting="A ruined roadside camp.",
            actor_ids=("pc:talia", "npc:goblin-scout"),
            player_actor_id="pc:talia",
            public_events=public_events,
        ),
    )
    return _build_game_state(actor_repo, enc_path, npc_actors=(goblin,))


def _combat_game_state(tmp_path: Path, goblin_hp: int = 0) -> GameState:
    """Return a GameState in COMBAT phase.

    goblin_hp defaults to 0 so combat ends after Talia passes her first turn,
    allowing ScriptedIO exhaustion ("exit") to terminate cleanly.
    """
    actor_repo = PlayerRepository(tmp_path)
    actor_repo.save(_default_player())
    goblin = replace(_default_npc(), hp_current=goblin_hp)
    enc_path = _write_encounter(
        tmp_path,
        EncounterState(
            encounter_id="goblin-camp",
            phase=EncounterPhase.COMBAT,
            setting="A ruined roadside camp.",
            actor_ids=("pc:talia", "npc:goblin-scout"),
            player_actor_id="pc:talia",
            outcome="combat",
        ),
    )
    return _build_game_state(actor_repo, enc_path, npc_actors=(goblin,))


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
    initial_game_state: GameState | None = None,
    intents: list[PlayerIntent] | None = None,
    rules_agent: FakeRulesAgent | None = None,
    narrator_agent: FakeNarratorAgent | None = None,
    io: ScriptedIO | None = None,
    combat_intents: list[str] | None = None,
    memory: FakeMemoryRepository | None = None,
    game_state_repo: FakeGameStateRepository | None = None,
) -> tuple[EncounterOrchestrator, GameState]:
    gs = (
        initial_game_state
        if initial_game_state is not None
        else _scene_opening_game_state(tmp_path)
    )
    if game_state_repo is None:
        game_state_repo = FakeGameStateRepository(gs)
    if memory is None:
        memory = FakeMemoryRepository()
    orch = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=memory,
            game_state=game_state_repo,
        ),
        agents=OrchestratorAgents(
            rules=rules_agent or FakeRulesAgent(),
            narrator=narrator_agent or FakeNarratorAgent(),
        ),
        io=io or ScriptedIO([], on_exhaust="exit"),
        _player_intent_agent=FakePlayerIntentAgent(intents),
        _combat_intent_agent=_mock_combat_intent_agent(combat_intents),
    )
    return orch, gs


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
    fake_gsr = FakeGameStateRepository(_social_game_state(tmp_path))
    mem = FakeMemoryRepository()
    gs = _social_game_state(tmp_path)
    orchestrator, _ = _orchestrator(
        tmp_path,
        intents=[
            _intent(IntentCategory.STATUS),
            _intent(IntentCategory.RECAP),
            _intent(IntentCategory.SKILL_CHECK, check_hint="Persuasion"),
        ],
        rules_agent=rules_agent,
        narrator_agent=narrator_agent,
        io=ScriptedIO(["status", "what happened", "Hello, I do not want trouble."]),
        memory=mem,
        game_state_repo=fake_gsr,
    )

    orchestrator.run(gs)

    assert any(f.purpose == "social_resolution" for f in narrator_agent.frames)
    assert any(f.purpose == "status_response" for f in narrator_agent.frames)
    assert any(f.purpose == "recap_response" for f in narrator_agent.frames)
    saved = fake_gsr.load().encounter
    assert saved is not None
    assert saved.outcome == "peaceful"


def test_status_routes_to_status_frame_without_rules_adjudication(
    tmp_path: Path,
) -> None:
    rules_agent = FakeRulesAgent()
    narrator_agent = FakeNarratorAgent()
    gs = _social_game_state(tmp_path)
    orchestrator, _ = _orchestrator(
        tmp_path,
        initial_game_state=gs,
        intents=[_intent(IntentCategory.STATUS)],
        rules_agent=rules_agent,
        narrator_agent=narrator_agent,
        io=ScriptedIO(["status", "exit"]),
    )

    orchestrator.run(gs)

    assert any(f.purpose == "status_response" for f in narrator_agent.frames)
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
    gs = _social_game_state(tmp_path)
    orchestrator, _ = _orchestrator(
        tmp_path,
        initial_game_state=gs,
        intents=[_intent(IntentCategory.LOOK_AROUND)],
        rules_agent=rules_agent,
        narrator_agent=narrator_agent,
        io=ScriptedIO(["", "   ", "look around", "exit"]),
    )

    orchestrator.run(gs)

    assert any(f.purpose == "status_response" for f in narrator_agent.frames)
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
        "campaignnarrator.domain.models.roll._roll", side_effect=[16]
    )
    narrator_agent = FakeNarratorAgent()
    gs = _social_game_state(tmp_path)
    fake_gsr = FakeGameStateRepository(gs)
    mem = FakeMemoryRepository()
    orchestrator, _ = _orchestrator(
        tmp_path,
        intents=[
            _intent(IntentCategory.SKILL_CHECK, check_hint="Persuasion"),
        ],
        rules_agent=rules_agent,
        narrator_agent=narrator_agent,
        io=ScriptedIO(["I try to calm them down.", "exit"]),
        memory=mem,
        game_state_repo=fake_gsr,
    )

    orchestrator.run(gs)

    request = rules_agent.requests[0]
    saved = fake_gsr.load().encounter
    assert request.allowed_outcomes == (
        "success",
        "failure",
        "complication",
        "peaceful",
    )
    assert request.check_hints == ("Persuasion",)
    assert [c.args[0] for c in mock_roll.call_args_list] == ["1d20+1"]
    assert saved is not None
    assert saved.outcome == "de-escalated"
    assert "Roll: calm goblins = 16" in narrator_agent.frames[-1].resolved_outcomes
    assert narrator_agent.frames[-1].player_action == "I try to calm them down."
    assert any(f.purpose == "social_resolution" for f in narrator_agent.frames)


def test_social_check_with_outcome_emits_encounter_completed_event(
    tmp_path: Path,
) -> None:
    fake_gsr = FakeGameStateRepository(_social_game_state(tmp_path))
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
    gs = _social_game_state(tmp_path)
    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=memory,
            game_state=fake_gsr,
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

    orchestrator.run(gs)

    completed = [e for e in memory.events if e.get("type") == "encounter_completed"]
    assert len(completed) == 1
    assert completed[0]["outcome"] == "de-escalated"


def test_social_check_without_outcome_does_not_emit_encounter_completed_event(
    tmp_path: Path,
) -> None:
    fake_gsr = FakeGameStateRepository(_social_game_state(tmp_path))
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
    gs = _social_game_state(tmp_path)
    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=memory,
            game_state=fake_gsr,
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

    orchestrator.run(gs)

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
    gs = _social_game_state(tmp_path)
    orchestrator, _ = _orchestrator(
        tmp_path,
        initial_game_state=gs,
        intents=[_intent(category)],
        narrator_agent=narrator_agent,
        io=ScriptedIO(["I ask what they want.", "exit"]),
    )

    orchestrator.run(gs)

    assert narrator_agent.frames[-1].purpose == purpose
    assert narrator_agent.frames[-1].player_action == "I ask what they want."
    assert any(f.purpose == purpose for f in narrator_agent.frames)


def test_aggressive_input_rolls_initiative_then_enters_combat(
    tmp_path: Path, mocker: object
) -> None:
    """Entering combat transitions phase and delegates to CombatOrchestrator.

    CombatOrchestrator is mocked since Task 4 handles registry threading there.
    """
    # Actors are rolled in actor_ids order: "pc:talia" before "npc:goblin-scout".
    # Talia gets 18, goblin gets 12 → Talia wins initiative and goes first.
    mock_roll = mocker.patch(  # type: ignore[attr-defined]
        "campaignnarrator.orchestrators.encounter_orchestrator.roll",
        side_effect=[18, 12],
    )
    narrator_agent = FakeNarratorAgent()
    initial_state = _social_game_state(tmp_path, goblin_hp=0)
    fake_gsr = FakeGameStateRepository(initial_state)
    fake_memory = FakeMemoryRepository()
    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(memory=fake_memory, game_state=fake_gsr),
        agents=OrchestratorAgents(rules=FakeRulesAgent(), narrator=narrator_agent),
        io=ScriptedIO(["I draw steel and rush the goblin."]),
        _player_intent_agent=FakePlayerIntentAgent(
            [_intent(IntentCategory.HOSTILE_ACTION)]
        ),
    )

    with patch(
        "campaignnarrator.orchestrators.encounter_orchestrator.CombatOrchestrator"
    ) as mock_cls:
        combat_state = replace(
            initial_state.encounter,
            phase=EncounterPhase.COMBAT,
            outcome="combat",
        )
        mock_cls.return_value.run.return_value = GameState(
            campaign=initial_state.campaign,
            encounter=combat_state,
            actor_registry=initial_state.actor_registry,
            combat_state=CombatState(
                turn_order=TurnOrder(),
                status=CombatStatus.ACTIVE,
            ),
        )
        result = orchestrator.run(initial_state)

    saved = fake_gsr.load().encounter
    assert result.encounter is not None
    assert result.encounter.phase is not EncounterPhase.ENCOUNTER_COMPLETE
    assert saved is not None
    assert saved.phase is EncounterPhase.COMBAT
    assert saved.outcome == "combat"
    assert [c.args[0] for c in mock_roll.call_args_list] == ["1d20+5", "1d20+2"]
    assert narrator_agent.frames[-1].purpose == "combat_start"


def test_enter_combat_emits_encounter_completed_event(
    tmp_path: Path, mocker: object
) -> None:
    # The encounter_completed event is emitted by _enter_combat before CombatOrchestrator runs.
    # CombatOrchestrator is mocked since Task 4 handles registry threading there.
    initial_state = _social_game_state(tmp_path, goblin_hp=0)
    fake_gsr = FakeGameStateRepository(initial_state)
    memory = FakeMemoryRepository()
    # Actors rolled in actor_ids order: "pc:talia" first, "npc:goblin-scout" second.
    # Talia gets 18, goblin gets 12 → Talia wins initiative and goes first.
    mocker.patch(  # type: ignore[attr-defined]
        "campaignnarrator.orchestrators.encounter_orchestrator.roll",
        side_effect=[18, 12],
    )
    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=memory,
            game_state=fake_gsr,
        ),
        agents=OrchestratorAgents(
            rules=FakeRulesAgent(),
            narrator=FakeNarratorAgent(),
        ),
        io=ScriptedIO(["I draw steel and rush the goblin."]),
        _player_intent_agent=FakePlayerIntentAgent(
            [_intent(IntentCategory.HOSTILE_ACTION)]
        ),
    )

    with patch(
        "campaignnarrator.orchestrators.encounter_orchestrator.CombatOrchestrator"
    ) as mock_cls:
        combat_state = replace(
            initial_state.encounter,
            phase=EncounterPhase.COMBAT,
            outcome="combat",
        )
        mock_cls.return_value.run.return_value = GameState(
            campaign=initial_state.campaign,
            encounter=combat_state,
            actor_registry=initial_state.actor_registry,
            combat_state=CombatState(
                turn_order=TurnOrder(),
                status=CombatStatus.ACTIVE,
            ),
        )
        orchestrator.run(initial_state)

    completed_events = [
        e for e in memory.events if e.get("type") == "encounter_completed"
    ]
    assert len(completed_events) == 1
    assert completed_events[0]["outcome"] == "combat"
    assert completed_events[0]["encounter_id"] == "goblin-camp"


def test_enter_combat_displays_initiative_rolls_to_player(
    tmp_path: Path, mocker: object
) -> None:
    """_enter_combat must display the initiative roll event string to the player."""
    initial_state = _social_game_state(tmp_path, goblin_hp=0)
    fake_gsr = FakeGameStateRepository(initial_state)
    memory = FakeMemoryRepository()
    mocker.patch(  # type: ignore[attr-defined]
        "campaignnarrator.orchestrators.encounter_orchestrator.roll",
        side_effect=[18, 12],
    )
    io = ScriptedIO(["I draw steel and rush the goblin."])
    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(memory=memory, game_state=fake_gsr),
        agents=OrchestratorAgents(
            rules=FakeRulesAgent(),
            narrator=FakeNarratorAgent(),
        ),
        io=io,
        _player_intent_agent=FakePlayerIntentAgent(
            [_intent(IntentCategory.HOSTILE_ACTION)]
        ),
    )

    with patch(
        "campaignnarrator.orchestrators.encounter_orchestrator.CombatOrchestrator"
    ) as mock_cls:
        combat_state = replace(
            initial_state.encounter,
            phase=EncounterPhase.COMBAT,
            outcome="combat",
        )
        mock_cls.return_value.run.return_value = GameState(
            campaign=initial_state.campaign,
            encounter=combat_state,
            actor_registry=initial_state.actor_registry,
            combat_state=CombatState(
                turn_order=TurnOrder(),
                status=CombatStatus.ACTIVE,
            ),
        )
        orchestrator.run(initial_state)

    # The raw event string must appear as its own display call, not embedded in narration
    assert "Initiative: Talia 18, Goblin Scout 12." in io.displayed


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
    initial_game_state = _combat_game_state(tmp_path, goblin_hp=7)
    dead_goblin = replace(_default_npc(), hp_current=0)
    fake_gsr = FakeGameStateRepository(initial_game_state)
    fake_memory = FakeMemoryRepository()
    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(memory=fake_memory, game_state=fake_gsr),
        agents=OrchestratorAgents(
            rules=rules_agent,
            narrator=FakeNarratorAgent(),
        ),
        io=ScriptedIO(["I attack the goblin scout.", "end turn"]),
        _player_intent_agent=FakePlayerIntentAgent(),
        _combat_intent_agent=_mock_combat_intent_agent(["combat_action", "end_turn"]),
    )

    # Patch CombatOrchestrator to simulate the goblin dying; Task 4 will thread registry fully.
    with patch(
        "campaignnarrator.orchestrators.encounter_orchestrator.CombatOrchestrator"
    ) as mock_cls:
        post_combat_state = replace(
            initial_game_state.encounter, phase=EncounterPhase.ENCOUNTER_COMPLETE
        )
        mock_cls.return_value.run.return_value = GameState(
            campaign=initial_game_state.campaign,
            encounter=post_combat_state,
            actor_registry=ActorRegistry(
                actors={
                    _default_player().actor_id: _default_player(),
                    "npc:goblin-scout": dead_goblin,
                }
            ),
            combat_state=CombatState(
                turn_order=TurnOrder(),
                status=CombatStatus.COMPLETE,
            ),
        )
        orchestrator.run(initial_game_state)

    assert fake_gsr.load() is not None
    assert fake_gsr.load().actor_registry.actors["npc:goblin-scout"].hp_current == 0


def test_save_and_quit_persists_active_encounter_and_records_event(
    tmp_path: Path,
) -> None:
    gs = _social_game_state(tmp_path)
    fake_gsr = FakeGameStateRepository(gs)
    memory_repository = FakeMemoryRepository()
    io = ScriptedIO(["save and quit"])
    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=memory_repository,
            game_state=fake_gsr,
        ),
        agents=OrchestratorAgents(
            rules=FakeRulesAgent(),
            narrator=FakeNarratorAgent(),
        ),
        io=io,
        _player_intent_agent=FakePlayerIntentAgent(),
    )

    result = orchestrator.run(gs)

    assert result.encounter is not None
    assert result.encounter.phase is not EncounterPhase.ENCOUNTER_COMPLETE
    assert any("saved" in s.lower() for s in io.displayed)
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
    gs = _social_game_state(tmp_path)
    fake_gsr = FakeGameStateRepository(gs)
    memory_repository = FakeMemoryRepository()
    io = ScriptedIO(["save and quit"])
    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=memory_repository,
            game_state=fake_gsr,
        ),
        agents=OrchestratorAgents(
            rules=FakeRulesAgent(),
            narrator=FakeNarratorAgent(),
        ),
        io=io,
        _player_intent_agent=FakePlayerIntentAgent(),
    )

    result = orchestrator.run(gs)

    assert result.encounter is not None
    assert result.encounter.phase is not EncounterPhase.ENCOUNTER_COMPLETE
    assert any("saved" in s.lower() for s in io.displayed)


def test_completed_encounter_records_durable_event(tmp_path: Path) -> None:
    fake_gsr = FakeGameStateRepository(_social_game_state(tmp_path))
    memory_repository = FakeMemoryRepository()
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
    gs = _social_game_state(tmp_path)
    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=memory_repository,
            game_state=fake_gsr,
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

    orchestrator.run(gs)

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
    gs = _social_game_state(tmp_path)
    orchestrator, _ = _orchestrator(
        tmp_path,
        initial_game_state=gs,
        intents=[
            _intent(IntentCategory.SKILL_CHECK, check_hint="Persuasion"),
        ],
        rules_agent=rules_agent,
        io=ScriptedIO(["I ask them to stand down.", "exit"]),
    )
    orchestrator.run(gs)
    assert len(rules_agent.requests) == 1


def test_save_and_quit_during_combat_saves_state_and_records_event(
    tmp_path: Path,
) -> None:
    """save and quit in combat should persist state and record encounter_saved.

    CombatOrchestrator is mocked since Task 4 handles registry threading there.
    """
    initial_state = _combat_game_state(tmp_path, goblin_hp=7)
    fake_gsr = FakeGameStateRepository(initial_state)
    memory_repository = FakeMemoryRepository()
    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=memory_repository,
            game_state=fake_gsr,
        ),
        agents=OrchestratorAgents(
            rules=FakeRulesAgent(),
            narrator=FakeNarratorAgent(),
        ),
        io=ScriptedIO(["save and quit"]),
        _player_intent_agent=FakePlayerIntentAgent(),
    )

    saved_state = replace(initial_state.encounter, phase=EncounterPhase.COMBAT)
    with patch(
        "campaignnarrator.orchestrators.encounter_orchestrator.CombatOrchestrator"
    ) as mock_cls:
        mock_cls.return_value.run.return_value = GameState(
            campaign=initial_state.campaign,
            encounter=saved_state,
            actor_registry=initial_state.actor_registry,
            combat_state=CombatState(
                turn_order=TurnOrder(),
                status=CombatStatus.SAVED_AND_QUIT,
            ),
        )
        orchestrator.run(initial_state)

    assert memory_repository.events == [
        {
            "type": "encounter_saved",
            "encounter_id": "goblin-camp",
            "phase": "combat",
            "outcome": "combat",
        }
    ]


def test_combat_complete_transitions_encounter_to_encounter_complete(
    tmp_path: Path,
) -> None:
    """CombatStatus.COMPLETE must set phase=ENCOUNTER_COMPLETE and mark run as done."""
    initial_state = _combat_game_state(tmp_path, goblin_hp=7)
    fake_gsr = FakeGameStateRepository(initial_state)
    memory_repository = FakeMemoryRepository()
    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=memory_repository, game_state=fake_gsr
        ),
        agents=OrchestratorAgents(rules=FakeRulesAgent(), narrator=FakeNarratorAgent()),
        io=ScriptedIO([]),
        _player_intent_agent=FakePlayerIntentAgent(),
        _combat_intent_agent=_mock_combat_intent_agent([]),
    )

    with patch(
        "campaignnarrator.orchestrators.encounter_orchestrator.CombatOrchestrator"
    ) as mock_cls:
        mock_cls.return_value.run.return_value = GameState(
            campaign=initial_state.campaign,
            encounter=initial_state.encounter,
            actor_registry=initial_state.actor_registry,
            combat_state=CombatState(
                turn_order=TurnOrder(),
                status=CombatStatus.COMPLETE,
            ),
        )
        result = orchestrator.run(initial_state)

    assert (
        result.encounter is None
        or result.encounter.phase is EncounterPhase.ENCOUNTER_COMPLETE
    )
    assert fake_gsr.load().encounter.phase is EncounterPhase.ENCOUNTER_COMPLETE


def test_exit_during_combat_saves_state(tmp_path: Path) -> None:
    """'exit' in combat must persist state via memory repository.

    CombatOrchestrator is mocked since Task 4 handles registry threading there.
    """
    initial_state = _combat_game_state(tmp_path, goblin_hp=7)
    fake_gsr = FakeGameStateRepository(initial_state)
    memory_repository = FakeMemoryRepository()
    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=memory_repository,
            game_state=fake_gsr,
        ),
        agents=OrchestratorAgents(
            rules=FakeRulesAgent(),
            narrator=FakeNarratorAgent(),
        ),
        io=ScriptedIO(["exit"]),
        _player_intent_agent=FakePlayerIntentAgent(),
    )

    saved_state = replace(initial_state.encounter, phase=EncounterPhase.COMBAT)
    with patch(
        "campaignnarrator.orchestrators.encounter_orchestrator.CombatOrchestrator"
    ) as mock_cls:
        mock_cls.return_value.run.return_value = GameState(
            campaign=initial_state.campaign,
            encounter=saved_state,
            actor_registry=initial_state.actor_registry,
            combat_state=CombatState(
                turn_order=TurnOrder(),
                status=CombatStatus.ACTIVE,
            ),
        )
        orchestrator.run(initial_state)

    state_after = fake_gsr.load().encounter
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
    result = actor.narrative_summary()
    assert "20" not in result
    assert "16" not in result  # no AC
    assert "uninjured" in result
    assert "Talia" in result


def test_narrative_summary_lightly_wounded() -> None:
    actor = _make_actor("Talia", hp_current=14, hp_max=20)  # 70% = lightly wounded
    result = actor.narrative_summary()
    assert "lightly wounded" in result


def test_narrative_summary_bloodied() -> None:
    actor = _make_actor("Talia", hp_current=9, hp_max=20)  # 45% = bloodied
    result = actor.narrative_summary()
    assert "bloodied" in result
    assert "9" not in result


def test_narrative_summary_barely_standing() -> None:
    actor = _make_actor("Goblin", hp_current=1, hp_max=7)  # ~14% = barely standing
    result = actor.narrative_summary()
    assert "barely standing" in result


def test_narrative_summary_defeated() -> None:
    actor = _make_actor("Goblin", hp_current=0, hp_max=7)
    result = actor.narrative_summary()
    assert "defeated" in result


def test_narrative_summary_includes_conditions() -> None:
    actor = _make_actor("Talia", hp_current=15, hp_max=20, conditions=("poisoned",))
    result = actor.narrative_summary()
    assert "poisoned" in result


def test_narrative_summary_no_hp_numbers() -> None:
    actor = _make_actor("Talia", hp_current=15, hp_max=20)
    result = actor.narrative_summary()
    assert "15/20" not in result
    assert "AC" not in result


def test_narrative_summary_pc_includes_player_tag() -> None:
    actor = _make_actor("Gareth", hp_current=20, hp_max=20, actor_type=ActorType.PC)
    result = actor.narrative_summary()
    assert "player" in result
    assert "Gareth" in result
    assert "uninjured" in result


def test_narrative_summary_npc_excludes_player_tag() -> None:
    actor = _make_actor("Goblin", hp_current=7, hp_max=7, actor_type=ActorType.NPC)
    result = actor.narrative_summary()
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
            npc_presences: tuple[NpcPresence, ...] = (),
        ) -> PlayerIntent:
            captured_summaries.append(actor_summaries)
            return super().classify(
                raw_text,
                phase=phase,
                setting=setting,
                recent_events=recent_events,
                actor_summaries=actor_summaries,
                npc_presences=npc_presences,
            )

    gs = _social_game_state(tmp_path)
    fake_gsr = FakeGameStateRepository(gs)
    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=FakeMemoryRepository(),
            game_state=fake_gsr,
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
    orchestrator.run(gs)

    assert captured_summaries, "classify was not called with actor summaries"
    summaries = captured_summaries[0]
    assert any("Talia" in s and "uninjured" in s for s in summaries)
    assert not any("HP" in s or "AC" in s for s in summaries)


def test_scene_tone_persisted_on_state_after_scene_opening(tmp_path: Path) -> None:
    """scene_tone returned from opening narration should be saved on EncounterState."""
    narrator = FakeNarratorAgent(scene_tone="eerie and quiet")
    fake_gsr = FakeGameStateRepository(_scene_opening_game_state(tmp_path))
    orchestrator, _ = _orchestrator(
        tmp_path,
        narrator_agent=narrator,
        io=ScriptedIO(["save and quit"]),
        game_state_repo=fake_gsr,
    )

    gs = fake_gsr.load()
    orchestrator.run(gs)

    saved = fake_gsr.load().encounter
    assert saved is not None
    assert saved.scene_tone == "eerie and quiet"


def test_tone_guidance_propagated_to_subsequent_narration_frames(
    tmp_path: Path,
) -> None:
    """NarrationFrames built after scene_opening should carry tone_guidance."""
    narrator = FakeNarratorAgent(scene_tone="tense and dark")
    gs = _scene_opening_game_state(tmp_path)
    orchestrator, _ = _orchestrator(
        tmp_path,
        initial_game_state=gs,
        intents=[_intent(IntentCategory.STATUS)],
        narrator_agent=narrator,
        io=ScriptedIO(["status", "exit"]),
    )

    orchestrator.run(gs)

    # frames[0] is scene_opening; frames[1] is the status frame
    assert narrator.frames[0].purpose == "scene_opening"
    non_opening = [f for f in narrator.frames if f.purpose != "scene_opening"]
    assert len(non_opening) >= 1
    assert all(f.tone_guidance == "tense and dark" for f in non_opening)


def test_exit_during_social_phase_saves_state(tmp_path: Path) -> None:
    """'exit' in social phase must stage state — not silently discard it."""
    gs = _social_game_state(tmp_path)
    fake_gsr = FakeGameStateRepository(gs)
    orchestrator, _ = _orchestrator(
        tmp_path,
        io=ScriptedIO(["exit"]),
        game_state_repo=fake_gsr,
    )
    orchestrator.run(gs)
    # State must have been staged
    loaded = fake_gsr.load()
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
    gs = _social_game_state(tmp_path)
    orchestrator, _ = _orchestrator(
        tmp_path,
        initial_game_state=gs,
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

    result = orchestrator.run(gs)

    assert (
        result.encounter is None
        or result.encounter.phase is EncounterPhase.ENCOUNTER_COMPLETE
    )
    assert result.encounter is not None
    assert result.encounter.encounter_id == "goblin-camp"
    # Rules were called exactly once for the completing action.
    assert len(rules_agent.requests) == 1
    # The narrator was called only for the completion narration; the last frame
    # must be social_resolution, not any frame spawned by "let us celebrate".
    assert narrator_agent.frames[-1].purpose == "social_resolution"


def test_encounter_orchestrator_raises_if_neither_adapter_nor_player_intent_agent_provided(
    tmp_path: Path,
) -> None:
    """EncounterOrchestrator without adapter= or _player_intent_agent= must raise."""
    gs = _scene_opening_game_state(tmp_path)
    with pytest.raises(ValueError, match="EncounterOrchestrator requires adapter="):
        EncounterOrchestrator(
            repositories=OrchestratorRepositories(
                memory=FakeMemoryRepository(),
                game_state=FakeGameStateRepository(gs),
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
    orchestrator, gs = _orchestrator(
        tmp_path,
        intents=[_intent(IntentCategory.SCENE_OBSERVATION)],
        io=io,
    )
    orchestrator.run(gs)
    assert any("..." in msg for msg in io.displayed)


def test_considering_rules_displayed_before_adjudication(
    tmp_path: Path,
) -> None:
    """'Considering the rules...' must appear when action routes to adjudication."""
    io = ScriptedIO(["I try to pick the lock.", "exit"])
    orchestrator, gs = _orchestrator(
        tmp_path,
        intents=[
            _intent(IntentCategory.SKILL_CHECK, check_hint="Dexterity"),
        ],
        io=io,
    )
    orchestrator.run(gs)
    assert any("Considering the rules" in msg for msg in io.displayed)


def test_resume_encounter_displays_recap_before_prompt(tmp_path: Path) -> None:
    """When resuming with a non-empty exchange buffer, session_resume narration appears."""
    io = ScriptedIO(["exit"])
    fake_gsr = FakeGameStateRepository(_social_game_state(tmp_path))
    memory = FakeMemoryRepository(
        exchange_buffer=("I spoke to the goblin.", "The goblin eyed you warily."),
    )
    gs = fake_gsr.load()
    narrator_agent = FakeNarratorAgent()
    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(memory=memory, game_state=fake_gsr),
        agents=OrchestratorAgents(rules=FakeRulesAgent(), narrator=narrator_agent),
        io=io,
        _player_intent_agent=FakePlayerIntentAgent(),
    )
    orchestrator.run(gs)
    assert any(f.purpose == "session_resume" for f in narrator_agent.frames)


def test_fresh_encounter_does_not_show_recap(tmp_path: Path) -> None:
    """A brand-new SCENE_OPENING encounter must show the scene narration, not a recap."""
    io = ScriptedIO(["exit"])
    gs = _scene_opening_game_state(tmp_path)
    narrator_agent = FakeNarratorAgent()
    orchestrator, _ = _orchestrator(
        tmp_path,
        initial_game_state=gs,
        narrator_agent=narrator_agent,
        io=io,
    )
    orchestrator.run(gs)
    assert any(f.purpose == "scene_opening" for f in narrator_agent.frames)
    assert not any(f.purpose == "recap_response" for f in narrator_agent.frames)


def test_save_exit_intent_saves_state_and_breaks_loop(tmp_path: Path) -> None:
    fake_gsr = FakeGameStateRepository(_social_game_state(tmp_path))
    memory = FakeMemoryRepository()
    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=memory,
            game_state=fake_gsr,
        ),
        agents=OrchestratorAgents(
            rules=FakeRulesAgent(),
            narrator=FakeNarratorAgent(),
        ),
        io=ScriptedIO(["save and exit the game"]),
        _player_intent_agent=FakePlayerIntentAgent([_intent(IntentCategory.SAVE_EXIT)]),
    )

    gs = fake_gsr.load()
    result = orchestrator.run(gs)

    assert result.encounter is not None
    assert result.encounter.phase is not EncounterPhase.ENCOUNTER_COMPLETE
    saved = [e for e in memory.events if e.get("type") == "encounter_saved"]
    assert len(saved) == 1
    assert saved[0]["encounter_id"] == "goblin-camp"


def test_narration_stored_to_memory_during_encounter(tmp_path: Path) -> None:
    """Every narrate() call must store a record in the memory repository."""
    fake_gsr = FakeGameStateRepository(_scene_opening_game_state(tmp_path))
    memory = FakeMemoryRepository()
    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=memory,
            game_state=fake_gsr,
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

    gs = fake_gsr.load()
    orchestrator.run(gs)

    narration_entries = [
        m for _, m in memory.narratives if m.get("event_type") == "narration"
    ]
    # At minimum: scene_opening + npc_dialogue
    min_expected = 2
    assert len(narration_entries) >= min_expected
    assert all(m["encounter_id"] == "goblin-camp" for m in narration_entries)


def test_save_exit_stores_partial_summary_in_memory(tmp_path: Path) -> None:
    """save-and-quit must generate and store a partial encounter summary."""
    fake_gsr = FakeGameStateRepository(_scene_opening_game_state(tmp_path))
    memory = FakeMemoryRepository()
    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=memory,
            game_state=fake_gsr,
        ),
        agents=OrchestratorAgents(
            rules=FakeRulesAgent(),
            narrator=FakeNarratorAgent(),
        ),
        io=ScriptedIO(["save and quit"]),
        _player_intent_agent=FakePlayerIntentAgent([_intent(IntentCategory.SAVE_EXIT)]),
    )

    gs = fake_gsr.load()
    orchestrator.run(gs)

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
    gs = _social_game_state(tmp_path)
    orchestrator, _ = _orchestrator(
        tmp_path,
        initial_game_state=gs,
        intents=[_intent(IntentCategory.SKILL_CHECK, check_hint="Persuasion")],
        rules_agent=rules_agent,
        io=io,
    )

    orchestrator.run(gs)

    assert any("Roll:" in msg for msg in io.displayed)


def test_resume_recap_populates_prior_narrative_context_from_memory(
    tmp_path: Path,
) -> None:
    """On resume, prior session context is retrieved from memory and passed to narrator."""
    prior_summary = "You searched the woods and found a mysterious mirror."
    narrator_agent = FakeNarratorAgent()

    actor_repo = PlayerRepository(tmp_path)
    actor_repo.save(_default_player())
    enc_path = _write_encounter(
        tmp_path,
        EncounterState(
            encounter_id="goblin-camp",
            phase=EncounterPhase.SOCIAL,
            setting="A ruined roadside camp.",
            actor_ids=("pc:talia",),
            player_actor_id="pc:talia",
            public_events=("Roll: Investigation = 15.",),  # triggers recap path
        ),
    )
    fake_gsr = FakeGameStateRepository(_build_game_state(actor_repo, enc_path))
    memory_repository = FakeMemoryRepository(
        prior_context=[prior_summary],
        exchange_buffer=("I searched the camp.",),  # triggers session_resume path
    )
    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=memory_repository,
            game_state=fake_gsr,
        ),
        agents=OrchestratorAgents(
            rules=FakeRulesAgent(),
            narrator=narrator_agent,
        ),
        io=ScriptedIO(["exit"]),
        _player_intent_agent=FakePlayerIntentAgent(),
    )

    gs = fake_gsr.load()
    orchestrator.run(gs)

    # session_resume replaces recap_response in the new exchange-buffer-based resume flow
    resume_frames = [f for f in narrator_agent.frames if f.purpose == "session_resume"]
    assert resume_frames, "Expected at least one session_resume frame"
    assert prior_summary in resume_frames[0].prior_narrative_context


def test_resume_recap_includes_exchange_buffer_in_prior_context(
    tmp_path: Path,
) -> None:
    """On resume, exchange buffer entries appear in the prior_narrative_context."""
    narrator_agent = FakeNarratorAgent()

    actor_repo = PlayerRepository(tmp_path)
    actor_repo.save(_default_player())
    enc_path = _write_encounter(
        tmp_path,
        EncounterState(
            encounter_id="goblin-camp",
            phase=EncounterPhase.SOCIAL,
            setting="A ruined roadside camp.",
            actor_ids=("pc:talia",),
            player_actor_id="pc:talia",
            public_events=("Roll: Investigation = 15.",),
        ),
    )
    fake_gsr = FakeGameStateRepository(_build_game_state(actor_repo, enc_path))
    memory_repository = FakeMemoryRepository(
        exchange_buffer=("I search the camp.", "You find charred goblin bones."),
    )
    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=memory_repository, game_state=fake_gsr
        ),
        agents=OrchestratorAgents(rules=FakeRulesAgent(), narrator=narrator_agent),
        io=ScriptedIO(["exit"]),
        _player_intent_agent=FakePlayerIntentAgent(),
    )

    gs = fake_gsr.load()
    orchestrator.run(gs)

    resume_frames = [f for f in narrator_agent.frames if f.purpose == "session_resume"]
    assert resume_frames, "Expected at least one session_resume frame"
    assert "I search the camp." in resume_frames[0].prior_narrative_context
    assert "You find charred goblin bones." in resume_frames[0].prior_narrative_context


class TestSaveExitPath:
    def test_save_exit_stages_partial_summary(self, tmp_path: Path) -> None:
        """SAVE_EXIT must call stage_narration() — not store_narrative() directly."""
        gs = _social_game_state(tmp_path)
        fake_gsr = FakeGameStateRepository(gs)
        fake_memory = FakeMemoryRepository()
        orchestrator = EncounterOrchestrator(
            repositories=OrchestratorRepositories(
                memory=fake_memory, game_state=fake_gsr
            ),
            agents=OrchestratorAgents(
                rules=FakeRulesAgent(),
                narrator=FakeNarratorAgent(),
            ),
            io=ScriptedIO(["save and quit"]),
            _player_intent_agent=FakePlayerIntentAgent(
                [_intent(IntentCategory.SAVE_EXIT)]
            ),
        )
        orchestrator.run(gs)
        assert any(
            m[1].get("event_type") == "encounter_partial_summary"
            for m in fake_memory.staged_narrations
        )

    def test_save_exit_persists_game_state(self, tmp_path: Path) -> None:
        """SAVE_EXIT must call game_state_repo.persist() so SIGTERM has current state."""
        gs = _social_game_state(tmp_path)
        fake_gsr = FakeGameStateRepository(gs)
        orchestrator = EncounterOrchestrator(
            repositories=OrchestratorRepositories(
                memory=FakeMemoryRepository(), game_state=fake_gsr
            ),
            agents=OrchestratorAgents(
                rules=FakeRulesAgent(),
                narrator=FakeNarratorAgent(),
            ),
            io=ScriptedIO(["save and quit"]),
            _player_intent_agent=FakePlayerIntentAgent(
                [_intent(IntentCategory.SAVE_EXIT)]
            ),
        )
        orchestrator.run(gs)
        assert len(fake_gsr._cache) > 1


class TestApplyAction:
    def test_apply_action_updates_exchange_buffer(self, tmp_path: Path) -> None:
        """After a non-combat action, update_exchange() is called with input + narration."""
        gs = _social_game_state(tmp_path)
        fake_gsr = FakeGameStateRepository(gs)
        fake_memory = FakeMemoryRepository()
        orchestrator = EncounterOrchestrator(
            repositories=OrchestratorRepositories(
                memory=fake_memory, game_state=fake_gsr
            ),
            agents=OrchestratorAgents(
                rules=FakeRulesAgent(),
                narrator=FakeNarratorAgent(),
            ),
            io=ScriptedIO(["I ask what they want.", "exit"]),
            _player_intent_agent=FakePlayerIntentAgent(
                [_intent(IntentCategory.NPC_DIALOGUE)]
            ),
        )
        orchestrator.run(gs)
        assert len(fake_memory.exchange_updates) >= 1
        assert any(
            pair[0] == "I ask what they want." for pair in fake_memory.exchange_updates
        )

    def test_scene_opening_updates_exchange_buffer(self, tmp_path: Path) -> None:
        """Scene opening narration is appended with empty player input."""
        gs = _scene_opening_game_state(tmp_path)
        fake_gsr = FakeGameStateRepository(gs)
        fake_memory = FakeMemoryRepository()
        orchestrator = EncounterOrchestrator(
            repositories=OrchestratorRepositories(
                memory=fake_memory, game_state=fake_gsr
            ),
            agents=OrchestratorAgents(
                rules=FakeRulesAgent(),
                narrator=FakeNarratorAgent(),
            ),
            io=ScriptedIO([], on_exhaust="exit"),
            _player_intent_agent=FakePlayerIntentAgent([]),
        )
        orchestrator.run(gs)
        assert any(pair[0] == "" for pair in fake_memory.exchange_updates)


class TestHiddenConditionClearing:
    """hidden condition is cleared when the player speaks or takes a hostile action."""

    def _repo_with_hidden_player(self, tmp_path: Path) -> FakeGameStateRepository:
        actor_repo = PlayerRepository(tmp_path)
        hidden_player = replace(_default_player(), conditions=("hidden",))
        actor_repo.save(hidden_player)
        enc_path = _write_encounter(
            tmp_path,
            EncounterState(
                encounter_id="goblin-camp",
                phase=EncounterPhase.SOCIAL,
                setting="A ruined roadside camp.",
                actor_ids=("pc:talia", "npc:goblin-scout"),
                player_actor_id="pc:talia",
            ),
        )
        npc = _default_npc()
        registry = ActorRegistry(
            actors={"pc:talia": hidden_player, "npc:goblin-scout": npc}
        )
        encounter = EncounterState.from_dict(json.loads(enc_path.read_text()))
        initial_state = GameState(
            campaign=_default_campaign(), encounter=encounter, actor_registry=registry
        )
        return FakeGameStateRepository(initial_state)

    def test_npc_dialogue_clears_hidden_from_player(self, tmp_path: Path) -> None:
        fake_gsr = self._repo_with_hidden_player(tmp_path)
        gs = fake_gsr.load()
        orchestrator = EncounterOrchestrator(
            repositories=OrchestratorRepositories(
                memory=FakeMemoryRepository(), game_state=fake_gsr
            ),
            agents=OrchestratorAgents(
                rules=FakeRulesAgent(), narrator=FakeNarratorAgent()
            ),
            io=ScriptedIO(["Hello there.", "exit"]),
            _player_intent_agent=FakePlayerIntentAgent(
                [_intent(IntentCategory.NPC_DIALOGUE)]
            ),
        )
        orchestrator.run(gs)
        player = fake_gsr.load().actor_registry.actors["pc:talia"]
        assert not player.has_condition("hidden")

    def test_hostile_action_clears_hidden_from_player(
        self, tmp_path: Path, mocker: object
    ) -> None:
        """CombatOrchestrator is mocked since Task 4 handles registry threading there."""
        mocker.patch(  # type: ignore[attr-defined]
            "campaignnarrator.orchestrators.encounter_orchestrator.roll",
            side_effect=[12, 18],
        )
        goblin = replace(_default_npc(), hp_current=0)
        actor_repo = PlayerRepository(tmp_path)
        hidden_player = replace(_default_player(), conditions=("hidden",))
        actor_repo.save(hidden_player)
        enc_path = _write_encounter(
            tmp_path,
            EncounterState(
                encounter_id="goblin-camp",
                phase=EncounterPhase.SOCIAL,
                setting="A ruined roadside camp.",
                actor_ids=("pc:talia", "npc:goblin-scout"),
                player_actor_id="pc:talia",
            ),
        )
        registry = ActorRegistry(
            actors={"pc:talia": hidden_player, "npc:goblin-scout": goblin}
        )
        encounter = EncounterState.from_dict(json.loads(enc_path.read_text()))
        initial_state = GameState(
            campaign=_default_campaign(), encounter=encounter, actor_registry=registry
        )
        fake_gsr = FakeGameStateRepository(initial_state)
        orchestrator = EncounterOrchestrator(
            repositories=OrchestratorRepositories(
                memory=FakeMemoryRepository(), game_state=fake_gsr
            ),
            agents=OrchestratorAgents(
                rules=FakeRulesAgent(), narrator=FakeNarratorAgent()
            ),
            io=ScriptedIO(["I attack!"]),
            _player_intent_agent=FakePlayerIntentAgent(
                [_intent(IntentCategory.HOSTILE_ACTION)]
            ),
        )
        with patch(
            "campaignnarrator.orchestrators.encounter_orchestrator.CombatOrchestrator"
        ) as mock_cls:
            post_combat_state = replace(
                initial_state.encounter,
                phase=EncounterPhase.COMBAT,
            )
            # Use a registry with hidden already cleared, matching what
            # _clear_player_hidden produces before _run_combat is called.
            mock_cls.return_value.run.return_value = GameState(
                campaign=initial_state.campaign,
                encounter=post_combat_state,
                actor_registry=ActorRegistry(
                    actors={
                        "pc:talia": replace(hidden_player, conditions=()),
                        "npc:goblin-scout": goblin,
                    }
                ),
                combat_state=CombatState(
                    turn_order=TurnOrder(),
                    status=CombatStatus.ACTIVE,
                ),
            )
            orchestrator.run(initial_state)
        player = fake_gsr.load().actor_registry.actors["pc:talia"]
        assert not player.has_condition("hidden")

    def test_npc_dialogue_without_hidden_leaves_state_unchanged(
        self, tmp_path: Path
    ) -> None:
        gs = _social_game_state(tmp_path)
        fake_gsr = FakeGameStateRepository(gs)
        orchestrator = EncounterOrchestrator(
            repositories=OrchestratorRepositories(
                memory=FakeMemoryRepository(), game_state=fake_gsr
            ),
            agents=OrchestratorAgents(
                rules=FakeRulesAgent(), narrator=FakeNarratorAgent()
            ),
            io=ScriptedIO(["Hello.", "exit"]),
            _player_intent_agent=FakePlayerIntentAgent(
                [_intent(IntentCategory.NPC_DIALOGUE)]
            ),
        )
        orchestrator.run(gs)
        player = fake_gsr.load().actor_registry.actors["pc:talia"]
        assert not player.has_condition("hidden")


class TestDCResolution:
    """_apply_adjudication captures DC roll outcome and filters state_effects by apply_on."""

    def test_dc_success_applies_success_and_always_effects_excludes_failure(
        self, tmp_path: Path, mocker: object
    ) -> None:
        """When the DC roll succeeds, apply_on='failure' effects are excluded."""
        rules_agent = FakeRulesAgent(
            [
                RulesAdjudication(
                    is_legal=True,
                    action_type="skill_check",
                    summary="The player attempts to hide.",
                    roll_requests=(
                        RollRequest(
                            owner="pc:talia",
                            visibility=RollVisibility.PUBLIC,
                            expression="1d20+2",
                            purpose="Stealth check",
                            difficulty_class=15,
                        ),
                    ),
                    state_effects=(
                        StateEffect(
                            effect_type="add_condition",
                            target="pc:talia",
                            value="hidden",
                            apply_on="success",
                        ),
                        StateEffect(
                            effect_type="add_condition",
                            target="pc:talia",
                            value="spotted",
                            apply_on="failure",
                        ),
                        StateEffect(
                            effect_type="append_public_event",
                            target="encounter:goblin-camp",
                            value="Stealth attempted.",
                            apply_on="always",
                        ),
                    ),
                )
            ]
        )
        mocker.patch(  # type: ignore[attr-defined]
            "campaignnarrator.domain.models.roll._roll",
            side_effect=[18],  # above DC 15
        )
        narrator_agent = FakeNarratorAgent()
        fake_gsr = FakeGameStateRepository(_social_game_state(tmp_path))
        gs = _social_game_state(tmp_path)
        fake_gsr = FakeGameStateRepository(gs)
        orchestrator = EncounterOrchestrator(
            repositories=OrchestratorRepositories(
                memory=FakeMemoryRepository(), game_state=fake_gsr
            ),
            agents=OrchestratorAgents(rules=rules_agent, narrator=narrator_agent),
            io=ScriptedIO(["I try to hide.", "exit"]),
            _player_intent_agent=FakePlayerIntentAgent(
                [_intent(IntentCategory.SKILL_CHECK, check_hint="Stealth")]
            ),
        )

        orchestrator.run(gs)

        assert (
            fake_gsr.load().actor_registry.actors["pc:talia"].has_condition("hidden")
        )  # success effect applied
        assert (
            not fake_gsr.load()
            .actor_registry.actors["pc:talia"]
            .has_condition("spotted")
        )  # failure effect excluded
        # Roll result appears in resolved_outcomes; LLM summary does not
        frame = narrator_agent.frames[-1]
        assert any("Succeeded (DC 15)" in o for o in frame.resolved_outcomes)
        assert "The player attempts to hide." not in frame.resolved_outcomes

    def test_dc_failure_applies_failure_and_always_effects_excludes_success(
        self, tmp_path: Path, mocker: object
    ) -> None:
        """When the DC roll fails, apply_on='success' effects are excluded."""
        rules_agent = FakeRulesAgent(
            [
                RulesAdjudication(
                    is_legal=True,
                    action_type="skill_check",
                    summary="The player attempts to hide.",
                    roll_requests=(
                        RollRequest(
                            owner="pc:talia",
                            visibility=RollVisibility.PUBLIC,
                            expression="1d20+2",
                            purpose="Stealth check",
                            difficulty_class=15,
                        ),
                    ),
                    state_effects=(
                        StateEffect(
                            effect_type="add_condition",
                            target="pc:talia",
                            value="hidden",
                            apply_on="success",
                        ),
                        StateEffect(
                            effect_type="add_condition",
                            target="pc:talia",
                            value="spotted",
                            apply_on="failure",
                        ),
                    ),
                )
            ]
        )
        mocker.patch(  # type: ignore[attr-defined]
            "campaignnarrator.domain.models.roll._roll",
            side_effect=[8],  # below DC 15
        )
        narrator_agent = FakeNarratorAgent()
        gs = _social_game_state(tmp_path)
        fake_gsr = FakeGameStateRepository(gs)
        orchestrator = EncounterOrchestrator(
            repositories=OrchestratorRepositories(
                memory=FakeMemoryRepository(), game_state=fake_gsr
            ),
            agents=OrchestratorAgents(rules=rules_agent, narrator=narrator_agent),
            io=ScriptedIO(["I try to hide.", "exit"]),
            _player_intent_agent=FakePlayerIntentAgent(
                [_intent(IntentCategory.SKILL_CHECK, check_hint="Stealth")]
            ),
        )

        orchestrator.run(gs)

        assert (
            not fake_gsr.load()
            .actor_registry.actors["pc:talia"]
            .has_condition("hidden")
        )  # success effect excluded
        assert (
            fake_gsr.load().actor_registry.actors["pc:talia"].has_condition("spotted")
        )  # failure effect applied
        frame = narrator_agent.frames[-1]
        assert any("Failed (DC 15)" in o for o in frame.resolved_outcomes)
        assert "The player attempts to hide." not in frame.resolved_outcomes

    def test_no_dc_applies_all_effects_and_includes_summary(
        self, tmp_path: Path, mocker: object
    ) -> None:
        """Without a DC roll, all effects apply and adjudication.summary is in resolved_outcomes."""
        rules_agent = FakeRulesAgent(
            [
                RulesAdjudication(
                    is_legal=True,
                    action_type="skill_check",
                    summary="The goblins are impressed.",
                    roll_requests=(
                        RollRequest(
                            owner="pc:talia",
                            visibility=RollVisibility.PUBLIC,
                            expression="1d20+2",
                            purpose="Persuasion check",
                            # No difficulty_class set
                        ),
                    ),
                    state_effects=(
                        StateEffect(
                            effect_type="add_condition",
                            target="pc:talia",
                            value="charmed",
                            apply_on="success",
                        ),
                    ),
                )
            ]
        )
        mocker.patch(  # type: ignore[attr-defined]
            "campaignnarrator.domain.models.roll._roll", side_effect=[12]
        )
        narrator_agent = FakeNarratorAgent()
        gs = _social_game_state(tmp_path)
        fake_gsr = FakeGameStateRepository(gs)
        orchestrator = EncounterOrchestrator(
            repositories=OrchestratorRepositories(
                memory=FakeMemoryRepository(), game_state=fake_gsr
            ),
            agents=OrchestratorAgents(rules=rules_agent, narrator=narrator_agent),
            io=ScriptedIO(["I try to convince them.", "exit"]),
            _player_intent_agent=FakePlayerIntentAgent(
                [_intent(IntentCategory.SKILL_CHECK, check_hint="Persuasion")]
            ),
        )

        orchestrator.run(gs)

        # Without DC, all effects apply regardless of apply_on value
        assert (
            fake_gsr.load().actor_registry.actors["pc:talia"].has_condition("charmed")
        )
        # LLM summary IS included in resolved_outcomes when no DC
        frame = narrator_agent.frames[-1]
        assert "The goblins are impressed." in frame.resolved_outcomes


_EXPECTED_ALL_ACTOR_COUNT = 2


def test_public_actor_summaries_excludes_departed_npcs() -> None:
    """public_actor_summaries filters out DEPARTED actors when npc_presences is set."""
    talia = TALIA
    goblin = make_goblin_scout("npc:goblin-scout", "Goblin Scout")
    departed_presence = NpcPresence(
        actor_id="npc:goblin-scout",
        display_name="Goblin Scout",
        description="the goblin scout",
        name_known=True,
        status=NpcPresenceStatus.DEPARTED,
    )
    state = EncounterState(
        encounter_id="test",
        phase=EncounterPhase.SOCIAL,
        setting="A camp.",
        actor_ids=(talia.actor_id, "npc:goblin-scout"),
        player_actor_id=talia.actor_id,
        npc_presences=(departed_presence,),
    )
    registry = ActorRegistry(actors={talia.actor_id: talia, "npc:goblin-scout": goblin})
    summaries = GameState(
        encounter=state, actor_registry=registry
    ).public_actor_summaries()
    # Talia (PC) must appear; goblin (DEPARTED) must not
    assert any("Talia" in s for s in summaries)
    assert not any("Goblin" in s for s in summaries)


def test_public_actor_summaries_includes_concealed_npcs() -> None:
    """CONCEALED NPCs remain in summaries — they are present in the scene."""
    talia = TALIA
    goblin = make_goblin_scout("npc:goblin-scout", "Goblin Scout")
    concealed_presence = NpcPresence(
        actor_id="npc:goblin-scout",
        display_name="Goblin Scout",
        description="the goblin scout",
        name_known=True,
        status=NpcPresenceStatus.CONCEALED,
    )
    state = EncounterState(
        encounter_id="test",
        phase=EncounterPhase.SOCIAL,
        setting="A camp.",
        actor_ids=(talia.actor_id, "npc:goblin-scout"),
        player_actor_id=talia.actor_id,
        npc_presences=(concealed_presence,),
    )
    registry = ActorRegistry(actors={talia.actor_id: talia, "npc:goblin-scout": goblin})
    summaries = GameState(
        encounter=state, actor_registry=registry
    ).public_actor_summaries()
    # CONCEALED NPC must still appear — it is in the scene
    assert any("Goblin" in s for s in summaries)


def test_public_actor_summaries_includes_all_when_no_presences() -> None:
    """public_actor_summaries includes all actors when npc_presences is empty (backward compat)."""
    talia = TALIA
    goblin = make_goblin_scout("npc:goblin-scout", "Goblin Scout")
    state = EncounterState(
        encounter_id="test",
        phase=EncounterPhase.SOCIAL,
        setting="A camp.",
        actor_ids=(talia.actor_id, "npc:goblin-scout"),
        player_actor_id=talia.actor_id,
        npc_presences=(),
    )
    registry = ActorRegistry(actors={talia.actor_id: talia, "npc:goblin-scout": goblin})
    summaries = GameState(
        encounter=state, actor_registry=registry
    ).public_actor_summaries()
    assert len(summaries) == _EXPECTED_ALL_ACTOR_COUNT


def test_narrator_encounter_complete_signal_closes_encounter(
    tmp_path: Path,
) -> None:
    """Valid signal (next_location_hint set, purpose=scene_response) closes the encounter."""
    narrator_agent = FakeNarratorAgent(
        encounter_complete=True,
        next_location_hint="Cave of Whispers",
        completion_reason="Player departed the grove.",
    )
    gs = _social_game_state(tmp_path)
    orchestrator, _ = _orchestrator(
        tmp_path,
        initial_game_state=gs,
        intents=[_intent(IntentCategory.SCENE_OBSERVATION)],
        io=ScriptedIO(["I head to the cave."]),
        narrator_agent=narrator_agent,
    )

    result = orchestrator.run(gs)

    assert (
        result.encounter is None
        or result.encounter.phase is EncounterPhase.ENCOUNTER_COMPLETE
    )


def test_narrator_encounter_complete_without_location_hint_does_not_close(
    tmp_path: Path,
) -> None:
    """Signal missing next_location_hint is rejected — encounter stays open."""
    narrator_agent = FakeNarratorAgent(
        encounter_complete=True,
        next_location_hint=None,
        completion_reason="Player departed.",
    )
    gs = _social_game_state(tmp_path)
    orchestrator, _ = _orchestrator(
        tmp_path,
        initial_game_state=gs,
        intents=[
            _intent(IntentCategory.SCENE_OBSERVATION),
            _intent(IntentCategory.SAVE_EXIT),
        ],
        io=ScriptedIO(["I head to the cave.", "exit"]),
        narrator_agent=narrator_agent,
    )

    result = orchestrator.run(gs)

    assert result.encounter is not None
    assert result.encounter.phase is not EncounterPhase.ENCOUNTER_COMPLETE


def test_narrator_encounter_complete_on_skill_check_does_not_close(
    tmp_path: Path,
) -> None:
    """Signal raised during a skill check narration (purpose not in allowed set) is rejected."""
    narrator_agent = FakeNarratorAgent(
        encounter_complete=True,
        next_location_hint="somewhere",
        completion_reason="Erroneous signal.",
    )
    rules_agent = FakeRulesAgent(
        [
            RulesAdjudication(
                is_legal=True,
                action_type="skill_check",
                summary="Talia scans the clearing.",
                roll_requests=(),
                state_effects=(),
                reasoning_summary="Nothing special found.",
            )
        ]
    )
    gs = _social_game_state(tmp_path)
    orchestrator, _ = _orchestrator(
        tmp_path,
        initial_game_state=gs,
        intents=[
            _intent(IntentCategory.SKILL_CHECK, check_hint="Perception"),
            _intent(IntentCategory.SAVE_EXIT),
        ],
        io=ScriptedIO(["I search the clearing for danger.", "exit"]),
        narrator_agent=narrator_agent,
        rules_agent=rules_agent,
    )

    result = orchestrator.run(gs)

    assert result.encounter is not None
    assert result.encounter.phase is not EncounterPhase.ENCOUNTER_COMPLETE


# ---------------------------------------------------------------------------
# Helpers for NPC tracking tests (Tasks 1-3)
# ---------------------------------------------------------------------------


def _make_state(**kwargs: object) -> EncounterState:
    """Build a minimal EncounterState suitable for direct orchestrator method tests."""
    defaults: dict[str, object] = {
        "encounter_id": "test-enc",
        "phase": EncounterPhase.SOCIAL,
        "setting": "A ruined camp.",
        "actor_ids": ("pc:talia",),
        "player_actor_id": "pc:talia",
        "npc_presences": (),
    }
    defaults.update(kwargs)
    return EncounterState(**defaults)  # type: ignore[arg-type]


@pytest.fixture
def make_state():
    """Fixture that returns the _make_state factory."""
    return _make_state


def _make_orchestrator(
    *,
    _player_intent_agent: object | None = None,
    narrator_agent: object | None = None,
) -> EncounterOrchestrator:
    """Build a minimal EncounterOrchestrator for direct method tests."""

    fake_game_state = GameState(
        campaign=_default_campaign(),
        encounter=_make_state(),
        actor_registry=ActorRegistry(actors={"pc:talia": _default_player()}),
    )
    fake_gsr = FakeGameStateRepository(fake_game_state)
    return EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=FakeMemoryRepository(), game_state=fake_gsr
        ),
        agents=OrchestratorAgents(
            rules=FakeRulesAgent(),
            narrator=narrator_agent or FakeNarratorAgent(),
        ),
        io=ScriptedIO([], on_exhaust="exit"),
        _player_intent_agent=_player_intent_agent or FakePlayerIntentAgent(),
    )


# ---------------------------------------------------------------------------
# npc_presences forwarded to intent agent — verified through run_encounter()
# ---------------------------------------------------------------------------


def test_classify_intent_passes_npc_presences_to_agent() -> None:
    """The intent agent must receive the encounter's npc_presences on every classification."""
    captured_presences: list = []

    class CapturingIntentAgent:
        def classify(
            self,
            raw_text,
            *,
            phase,
            setting,
            recent_events,
            actor_summaries,
            npc_presences=(),
        ):
            captured_presences.extend(npc_presences)
            return PlayerIntent(category=IntentCategory.SAVE_EXIT)

    presence = NpcPresence(
        actor_id="npc:elder",
        display_name="Elder Rovan",
        description="the village elder",
        name_known=True,
        status=NpcPresenceStatus.AVAILABLE,
    )
    encounter = EncounterState(
        encounter_id="enc-npc-presences",
        phase=EncounterPhase.SOCIAL,
        setting="The village square.",
        actor_ids=(TALIA.actor_id,),
        player_actor_id=TALIA.actor_id,
        npc_presences=(presence,),
    )
    fake_gsr = FakeGameStateRepository(
        GameState(
            campaign=_default_campaign(),
            encounter=encounter,
            actor_registry=ActorRegistry(actors={TALIA.actor_id: TALIA}),
        )
    )
    orch = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=FakeMemoryRepository(), game_state=fake_gsr
        ),
        agents=OrchestratorAgents(rules=FakeRulesAgent(), narrator=FakeNarratorAgent()),
        io=ScriptedIO(["look around"]),
        _player_intent_agent=CapturingIntentAgent(),
    )
    gs = fake_gsr.load()
    orch.run(gs)
    assert len(captured_presences) == 1
    assert captured_presences[0].actor_id == "npc:elder"


# ---------------------------------------------------------------------------
# Task 2: _update_npc_interaction
# ---------------------------------------------------------------------------


def test_update_npc_interaction_sets_status_to_interacted(make_state) -> None:
    presence = NpcPresence(
        actor_id="npc:elder",
        display_name="Elder Rovan",
        description="the village elder",
        name_known=True,
        status=NpcPresenceStatus.AVAILABLE,
    )
    state = make_state(npc_presences=(presence,))
    updated = state.update_npc_interaction(
        "npc:elder", "Player asked about children; Elder denied knowledge."
    )
    updated_presence = next(
        p for p in updated.npc_presences if p.actor_id == "npc:elder"
    )
    assert updated_presence.status is NpcPresenceStatus.INTERACTED


def test_update_npc_interaction_appends_summary(make_state) -> None:
    presence = NpcPresence(
        actor_id="npc:elder",
        display_name="Elder Rovan",
        description="the village elder",
        name_known=True,
        status=NpcPresenceStatus.AVAILABLE,
    )
    state = make_state(npc_presences=(presence,))
    updated = state.update_npc_interaction(
        "npc:elder", "Player asked about children; Elder denied knowledge."
    )
    updated_presence = next(
        p for p in updated.npc_presences if p.actor_id == "npc:elder"
    )
    assert len(updated_presence.interaction_summaries) == 1
    assert "Elder denied knowledge" in updated_presence.interaction_summaries[0]


def test_update_npc_interaction_appends_to_existing_summaries(make_state) -> None:
    presence = NpcPresence(
        actor_id="npc:elder",
        display_name="Elder Rovan",
        description="the village elder",
        name_known=True,
        status=NpcPresenceStatus.INTERACTED,
        interaction_summaries=("First exchange.",),
    )
    state = make_state(npc_presences=(presence,))
    updated = state.update_npc_interaction("npc:elder", "Second exchange.")
    updated_presence = next(
        p for p in updated.npc_presences if p.actor_id == "npc:elder"
    )
    assert updated_presence.interaction_summaries == (
        "First exchange.",
        "Second exchange.",
    )


def test_update_npc_interaction_returns_state_unchanged_when_actor_not_found(
    make_state,
) -> None:
    state = make_state(npc_presences=())
    updated = state.update_npc_interaction("npc:nobody", "summary")
    assert updated is state


# ---------------------------------------------------------------------------
# NPC interaction tracking — verified through run_encounter()
# ---------------------------------------------------------------------------


def _elder_presence(
    status: NpcPresenceStatus = NpcPresenceStatus.AVAILABLE,
) -> NpcPresence:
    return NpcPresence(
        actor_id="npc:elder",
        display_name="Elder Rovan",
        description="the village elder",
        name_known=True,
        status=status,
    )


def _npc_dialogue_repo(
    npc_presences: tuple[NpcPresence, ...],
) -> FakeGameStateRepository:
    encounter = EncounterState(
        encounter_id="enc-npc",
        phase=EncounterPhase.SOCIAL,
        setting="The village square.",
        actor_ids=(TALIA.actor_id,),
        player_actor_id=TALIA.actor_id,
        npc_presences=npc_presences,
    )
    return FakeGameStateRepository(
        GameState(
            campaign=_default_campaign(),
            encounter=encounter,
            actor_registry=ActorRegistry(actors={TALIA.actor_id: TALIA}),
        )
    )


def test_npc_dialogue_updates_npc_interaction_when_summary_and_target_present() -> None:
    """After npc_dialogue intent with a target, NPC becomes INTERACTED and summary is stored."""

    class _NarratorWithSummary:
        def set_campaign_context(self, campaign_id: str) -> None:
            pass

        def narrate(self, frame: NarrationFrame) -> Narration:
            return Narration(
                text="Elder Rovan eyes you warily.",
                npc_interaction_summary="Player asked about children; Elder denied knowledge.",
            )

        def summarize_encounter_partial(self, state: object) -> str:
            return "Partial summary."

    fake_gsr = _npc_dialogue_repo(npc_presences=(_elder_presence(),))
    orch = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=FakeMemoryRepository(), game_state=fake_gsr
        ),
        agents=OrchestratorAgents(
            rules=FakeRulesAgent(), narrator=_NarratorWithSummary()
        ),
        io=ScriptedIO(["hello elder", "exit"]),
        _player_intent_agent=FakePlayerIntentAgent(
            intents=[
                PlayerIntent(
                    category=IntentCategory.NPC_DIALOGUE, target_npc_id="npc:elder"
                )
            ]
        ),
    )
    gs = fake_gsr.load()
    orch.run(gs)
    updated_presence = next(
        p for p in fake_gsr.load().encounter.npc_presences if p.actor_id == "npc:elder"
    )
    assert updated_presence.status is NpcPresenceStatus.INTERACTED
    assert len(updated_presence.interaction_summaries) == 1


def test_npc_dialogue_skips_update_when_no_summary() -> None:
    """If the narrator returns no npc_interaction_summary, NPC status is not updated."""

    class _NarratorNoSummary:
        def set_campaign_context(self, campaign_id: str) -> None:
            pass

        def narrate(self, frame: NarrationFrame) -> Narration:
            return Narration(text="Elder Rovan nods.", npc_interaction_summary=None)

        def summarize_encounter_partial(self, state: object) -> str:
            return "Partial summary."

    fake_gsr = _npc_dialogue_repo(npc_presences=(_elder_presence(),))
    orch = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=FakeMemoryRepository(), game_state=fake_gsr
        ),
        agents=OrchestratorAgents(
            rules=FakeRulesAgent(), narrator=_NarratorNoSummary()
        ),
        io=ScriptedIO(["hello elder", "exit"]),
        _player_intent_agent=FakePlayerIntentAgent(
            intents=[
                PlayerIntent(
                    category=IntentCategory.NPC_DIALOGUE, target_npc_id="npc:elder"
                )
            ]
        ),
    )
    gs = fake_gsr.load()
    orch.run(gs)
    updated_presence = next(
        p for p in fake_gsr.load().encounter.npc_presences if p.actor_id == "npc:elder"
    )
    assert updated_presence.status is NpcPresenceStatus.AVAILABLE


def test_npc_dialogue_skips_update_when_no_target_npc_id() -> None:
    """If the intent carries no target_npc_id, state is not updated even with a summary."""

    class _NarratorWithSummary:
        def set_campaign_context(self, campaign_id: str) -> None:
            pass

        def narrate(self, frame: NarrationFrame) -> Narration:
            return Narration(
                text="Someone replies.",
                npc_interaction_summary="Some exchange happened.",
            )

        def summarize_encounter_partial(self, state: object) -> str:
            return "Partial summary."

    fake_gsr = _npc_dialogue_repo(npc_presences=(_elder_presence(),))
    orch = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=FakeMemoryRepository(), game_state=fake_gsr
        ),
        agents=OrchestratorAgents(
            rules=FakeRulesAgent(), narrator=_NarratorWithSummary()
        ),
        io=ScriptedIO(["hello", "exit"]),
        _player_intent_agent=FakePlayerIntentAgent(
            intents=[
                PlayerIntent(category=IntentCategory.NPC_DIALOGUE, target_npc_id=None)
            ]
        ),
    )
    gs = fake_gsr.load()
    orch.run(gs)
    updated_presence = next(
        p for p in fake_gsr.load().encounter.npc_presences if p.actor_id == "npc:elder"
    )
    assert updated_presence.status is NpcPresenceStatus.AVAILABLE


def test_narrate_sets_traveling_actor_ids_on_encounter_complete() -> None:
    """Valid INTERACTED NPC committed to travel is captured in encounter state."""
    elara = make_goblin_scout("npc:elara", "Elara")
    encounter = replace(
        EncounterState(
            encounter_id="enc-001",
            phase=EncounterPhase.SOCIAL,
            setting="A forest glade.",
            actor_ids=(TALIA.actor_id, "npc:elara"),
            player_actor_id=TALIA.actor_id,
        ),
        npc_presences=(
            NpcPresence(
                actor_id="npc:elara",
                display_name="Elara",
                description="the herbalist",
                name_known=True,
                status=NpcPresenceStatus.INTERACTED,
            ),
        ),
    )
    fake_gsr = FakeGameStateRepository(
        GameState(
            campaign=_default_campaign(),
            encounter=encounter,
            actor_registry=ActorRegistry(
                actors={TALIA.actor_id: TALIA, "npc:elara": elara}
            ),
        )
    )
    narrator = FakeNarratorAgent(
        encounter_complete=True,
        next_location_hint="The cave entrance",
        completion_reason="Player departed.",
        traveling_actor_ids=("npc:elara",),
    )
    orch = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=FakeMemoryRepository(), game_state=fake_gsr
        ),
        agents=OrchestratorAgents(rules=FakeRulesAgent(), narrator=narrator),
        io=ScriptedIO(["look around"]),
        _player_intent_agent=FakePlayerIntentAgent(
            intents=[
                PlayerIntent(
                    category=IntentCategory.SCENE_OBSERVATION, reason="looks around"
                )
            ]
        ),
    )
    gs = fake_gsr.load()
    orch.run(gs)
    assert fake_gsr.load().encounter.traveling_actor_ids == ("npc:elara",)
    assert fake_gsr.load().encounter.next_location_hint == "The cave entrance"


def test_narrate_filters_invalid_traveling_actor_ids_on_completion() -> None:
    """IDs not in active NPC presences are dropped; only valid INTERACTED/AVAILABLE IDs kept."""
    elara = make_goblin_scout("npc:elara", "Elara")
    encounter = replace(
        EncounterState(
            encounter_id="enc-001",
            phase=EncounterPhase.SOCIAL,
            setting="A forest glade.",
            actor_ids=(TALIA.actor_id, "npc:elara"),
            player_actor_id=TALIA.actor_id,
        ),
        npc_presences=(
            NpcPresence(
                actor_id="npc:elara",
                display_name="Elara",
                description="the herbalist",
                name_known=True,
                status=NpcPresenceStatus.INTERACTED,
            ),
        ),
    )
    fake_gsr = FakeGameStateRepository(
        GameState(
            campaign=_default_campaign(),
            encounter=encounter,
            actor_registry=ActorRegistry(
                actors={TALIA.actor_id: TALIA, "npc:elara": elara}
            ),
        )
    )
    narrator = FakeNarratorAgent(
        encounter_complete=True,
        next_location_hint="The road north",
        completion_reason="Left.",
        traveling_actor_ids=("npc:elara", "npc:nonexistent"),
    )
    orch = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=FakeMemoryRepository(), game_state=fake_gsr
        ),
        agents=OrchestratorAgents(rules=FakeRulesAgent(), narrator=narrator),
        io=ScriptedIO(["go north"]),
        _player_intent_agent=FakePlayerIntentAgent(
            intents=[
                PlayerIntent(category=IntentCategory.SCENE_OBSERVATION, reason="go")
            ]
        ),
    )
    gs = fake_gsr.load()
    orch.run(gs)
    assert fake_gsr.load().encounter.traveling_actor_ids == ("npc:elara",)


def test_narrate_excludes_player_from_traveling_actor_ids() -> None:
    """The player's own actor_id is never included in traveling_actor_ids even if the narrator returns it."""
    elara = make_goblin_scout("npc:elara", "Elara")
    encounter = replace(
        EncounterState(
            encounter_id="enc-001",
            phase=EncounterPhase.SOCIAL,
            setting="A forest glade.",
            actor_ids=(TALIA.actor_id, "npc:elara"),
            player_actor_id=TALIA.actor_id,
        ),
        npc_presences=(
            NpcPresence(
                actor_id="npc:elara",
                display_name="Elara",
                description="the herbalist",
                name_known=True,
                status=NpcPresenceStatus.INTERACTED,
            ),
        ),
    )
    fake_gsr = FakeGameStateRepository(
        GameState(
            campaign=_default_campaign(),
            encounter=encounter,
            actor_registry=ActorRegistry(
                actors={TALIA.actor_id: TALIA, "npc:elara": elara}
            ),
        )
    )
    narrator = FakeNarratorAgent(
        encounter_complete=True,
        next_location_hint="The road north",
        completion_reason="Departed.",
        traveling_actor_ids=(
            TALIA.actor_id,
            "npc:elara",
        ),  # player ID included by narrator
    )
    orch = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=FakeMemoryRepository(), game_state=fake_gsr
        ),
        agents=OrchestratorAgents(rules=FakeRulesAgent(), narrator=narrator),
        io=ScriptedIO(["go north"]),
        _player_intent_agent=FakePlayerIntentAgent(
            intents=[
                PlayerIntent(category=IntentCategory.SCENE_OBSERVATION, reason="go")
            ]
        ),
    )
    gs = fake_gsr.load()
    orch.run(gs)
    assert TALIA.actor_id not in fake_gsr.load().encounter.traveling_actor_ids
    assert fake_gsr.load().encounter.traveling_actor_ids == ("npc:elara",)


def test_narrate_logs_warning_for_invalid_traveling_actor_ids(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A warning is emitted when the narrator returns an actor_id not in active presences."""
    elara = make_goblin_scout("npc:elara", "Elara")
    encounter = replace(
        EncounterState(
            encounter_id="enc-001",
            phase=EncounterPhase.SOCIAL,
            setting="A forest glade.",
            actor_ids=(TALIA.actor_id, "npc:elara"),
            player_actor_id=TALIA.actor_id,
        ),
        npc_presences=(
            NpcPresence(
                actor_id="npc:elara",
                display_name="Elara",
                description="the herbalist",
                name_known=True,
                status=NpcPresenceStatus.INTERACTED,
            ),
        ),
    )
    fake_gsr = FakeGameStateRepository(
        GameState(
            campaign=_default_campaign(),
            encounter=encounter,
            actor_registry=ActorRegistry(
                actors={TALIA.actor_id: TALIA, "npc:elara": elara}
            ),
        )
    )
    narrator = FakeNarratorAgent(
        encounter_complete=True,
        next_location_hint="The road north",
        completion_reason="Left.",
        traveling_actor_ids=("npc:elara", "npc:nonexistent"),
    )
    orch = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=FakeMemoryRepository(), game_state=fake_gsr
        ),
        agents=OrchestratorAgents(rules=FakeRulesAgent(), narrator=narrator),
        io=ScriptedIO(["go north"]),
        _player_intent_agent=FakePlayerIntentAgent(
            intents=[
                PlayerIntent(category=IntentCategory.SCENE_OBSERVATION, reason="go")
            ]
        ),
    )
    gs = fake_gsr.load()
    with caplog.at_level(logging.WARNING):
        orch.run(gs)
    assert any("npc:nonexistent" in r.message for r in caplog.records), (
        "Expected warning mentioning the ignored actor_id"
    )


def test_narrate_does_not_set_traveling_fields_when_encounter_not_complete() -> None:
    """traveling_actor_ids and next_location_hint stay at defaults when encounter_complete=False."""
    elara = make_goblin_scout("npc:elara", "Elara")
    encounter = replace(
        EncounterState(
            encounter_id="enc-001",
            phase=EncounterPhase.SOCIAL,
            setting="A forest glade.",
            actor_ids=(TALIA.actor_id, "npc:elara"),
            player_actor_id=TALIA.actor_id,
        ),
        npc_presences=(
            NpcPresence(
                actor_id="npc:elara",
                display_name="Elara",
                description="the herbalist",
                name_known=True,
                status=NpcPresenceStatus.INTERACTED,
            ),
        ),
    )
    fake_gsr = FakeGameStateRepository(
        GameState(
            campaign=_default_campaign(),
            encounter=encounter,
            actor_registry=ActorRegistry(
                actors={TALIA.actor_id: TALIA, "npc:elara": elara}
            ),
        )
    )
    # Narrator signals travel intent but does NOT complete the encounter — fields must be ignored.
    narrator = FakeNarratorAgent(
        encounter_complete=False,
        traveling_actor_ids=("npc:elara",),
        next_location_hint="The cave entrance",
    )
    orch = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=FakeMemoryRepository(), game_state=fake_gsr
        ),
        agents=OrchestratorAgents(rules=FakeRulesAgent(), narrator=narrator),
        io=ScriptedIO(["look around"]),
        _player_intent_agent=FakePlayerIntentAgent(
            intents=[
                PlayerIntent(
                    category=IntentCategory.SCENE_OBSERVATION, reason="looks around"
                ),
                # Second intent exhausts to SAVE_EXIT, ending the encounter without completing it.
            ]
        ),
    )
    gs = fake_gsr.load()
    orch.run(gs)
    assert fake_gsr.load().encounter.traveling_actor_ids == ()
    assert fake_gsr.load().encounter.next_location_hint is None


def test_apply_action_syncs_dead_actor_to_registry() -> None:
    """When a rules adjudication kills an NPC, the dead actor is written to the registry."""
    alive_goblin = replace(
        make_goblin_scout("npc:goblin", "Goblin Scout"), hp_current=1
    )
    encounter = EncounterState(
        encounter_id="enc-001",
        phase=EncounterPhase.SOCIAL,
        setting="The docks.",
        actor_ids=(TALIA.actor_id, "npc:goblin"),
        player_actor_id=TALIA.actor_id,
    )
    fake_gsr = FakeGameStateRepository(
        GameState(
            campaign=_default_campaign(),
            encounter=encounter,
            actor_registry=ActorRegistry(
                actors={TALIA.actor_id: TALIA, "npc:goblin": alive_goblin}
            ),
        )
    )
    rules_agent = FakeRulesAgent(
        adjudications=[
            RulesAdjudication(
                is_legal=True,
                action_type="success",
                roll_requests=(),
                state_effects=(
                    StateEffect(effect_type="change_hp", target="npc:goblin", value=-5),
                ),
                summary="You strike the goblin dead.",
            )
        ]
    )
    orch = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=FakeMemoryRepository(), game_state=fake_gsr
        ),
        agents=OrchestratorAgents(rules=rules_agent, narrator=FakeNarratorAgent()),
        io=ScriptedIO(["attack goblin"]),
        _player_intent_agent=FakePlayerIntentAgent(
            intents=[PlayerIntent(category=IntentCategory.SKILL_CHECK, reason="attack")]
        ),
    )
    gs = fake_gsr.load()
    orch.run(gs)
    assert "npc:goblin" in fake_gsr.load().actor_registry.actors
    assert fake_gsr.load().actor_registry.actors["npc:goblin"].hp_current == 0


def test_run_combat_syncs_dead_actor_to_registry() -> None:
    """After combat kills an NPC, the dead actor is written to the registry."""
    alive_goblin = replace(
        make_goblin_scout("npc:goblin", "Goblin Scout"), hp_current=5
    )
    dead_goblin = replace(make_goblin_scout("npc:goblin", "Goblin Scout"), hp_current=0)

    encounter = EncounterState(
        encounter_id="enc-001",
        phase=EncounterPhase.COMBAT,
        setting="The battlefield.",
        actor_ids=(TALIA.actor_id, "npc:goblin"),
        player_actor_id=TALIA.actor_id,
    )
    fake_gsr = FakeGameStateRepository(
        GameState(
            campaign=_default_campaign(),
            encounter=encounter,
            actor_registry=ActorRegistry(
                actors={TALIA.actor_id: TALIA, "npc:goblin": alive_goblin}
            ),
        )
    )

    post_combat_encounter = replace(
        encounter,
        phase=EncounterPhase.ENCOUNTER_COMPLETE,
    )

    orch = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=FakeMemoryRepository(), game_state=fake_gsr
        ),
        agents=OrchestratorAgents(rules=FakeRulesAgent(), narrator=FakeNarratorAgent()),
        io=ScriptedIO([]),
        _player_intent_agent=FakePlayerIntentAgent(),
    )

    initial_gs = fake_gsr.load()
    with patch(
        "campaignnarrator.orchestrators.encounter_orchestrator.CombatOrchestrator"
    ) as mock_cls:
        mock_cls.return_value.run.return_value = GameState(
            campaign=initial_gs.campaign,
            encounter=post_combat_encounter,
            actor_registry=ActorRegistry(
                actors={TALIA.actor_id: TALIA, "npc:goblin": dead_goblin}
            ),
            combat_state=CombatState(
                turn_order=TurnOrder(),
                status=CombatStatus.COMPLETE,
            ),
        )
        orch.run(initial_gs)

    assert "npc:goblin" in fake_gsr.load().actor_registry.actors
    assert fake_gsr.load().actor_registry.actors["npc:goblin"].hp_current == 0


def test_apply_action_syncs_living_actors_to_registry() -> None:
    """After a non-combat action, ALL encounter actors appear in the registry — not just dead ones."""
    goblin = replace(make_goblin_scout("npc:goblin", "Goblin Scout"), hp_current=5)
    encounter = EncounterState(
        encounter_id="enc-001",
        phase=EncounterPhase.SOCIAL,
        setting="The docks.",
        actor_ids=(TALIA.actor_id, "npc:goblin"),
        player_actor_id=TALIA.actor_id,
    )
    fake_gsr = FakeGameStateRepository(
        GameState(
            campaign=_default_campaign(),
            encounter=encounter,
            actor_registry=ActorRegistry(
                actors={TALIA.actor_id: TALIA, "npc:goblin": goblin}
            ),
        )
    )
    rules_agent = FakeRulesAgent(
        adjudications=[
            RulesAdjudication(
                is_legal=True,
                action_type="success",
                roll_requests=(),
                state_effects=(
                    StateEffect(effect_type="change_hp", target="npc:goblin", value=-2),
                ),
                summary="You graze the goblin.",
            )
        ]
    )
    orch = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=FakeMemoryRepository(), game_state=fake_gsr
        ),
        agents=OrchestratorAgents(rules=rules_agent, narrator=FakeNarratorAgent()),
        io=ScriptedIO(["attack goblin"]),
        _player_intent_agent=FakePlayerIntentAgent(
            intents=[PlayerIntent(category=IntentCategory.SKILL_CHECK, reason="attack")]
        ),
    )
    gs = fake_gsr.load()
    orch.run(gs)
    registry = fake_gsr.load().actor_registry
    assert "npc:goblin" in registry.actors
    assert registry.actors["npc:goblin"].hp_current == goblin.hp_current - 2
    assert TALIA.actor_id in registry.actors


def test_run_combat_syncs_all_actors_to_registry() -> None:
    """After combat, all post-combat actors (living and dead) are in the registry."""
    alive_goblin = replace(
        make_goblin_scout("npc:goblin", "Goblin Scout"), hp_current=5
    )
    wounded_goblin = replace(
        make_goblin_scout("npc:goblin", "Goblin Scout"), hp_current=2
    )

    encounter = EncounterState(
        encounter_id="enc-001",
        phase=EncounterPhase.COMBAT,
        setting="The battlefield.",
        actor_ids=(TALIA.actor_id, "npc:goblin"),
        player_actor_id=TALIA.actor_id,
    )
    fake_gsr = FakeGameStateRepository(
        GameState(
            campaign=_default_campaign(),
            encounter=encounter,
            actor_registry=ActorRegistry(
                actors={TALIA.actor_id: TALIA, "npc:goblin": alive_goblin}
            ),
        )
    )

    post_combat_encounter = replace(
        encounter,
        phase=EncounterPhase.ENCOUNTER_COMPLETE,
    )

    orch = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=FakeMemoryRepository(), game_state=fake_gsr
        ),
        agents=OrchestratorAgents(rules=FakeRulesAgent(), narrator=FakeNarratorAgent()),
        io=ScriptedIO([]),
        _player_intent_agent=FakePlayerIntentAgent(),
    )
    initial_gs = fake_gsr.load()
    with patch(
        "campaignnarrator.orchestrators.encounter_orchestrator.CombatOrchestrator"
    ) as mock_cls:
        mock_cls.return_value.run.return_value = GameState(
            campaign=initial_gs.campaign,
            encounter=post_combat_encounter,
            actor_registry=ActorRegistry(
                actors={TALIA.actor_id: TALIA, "npc:goblin": wounded_goblin}
            ),
            combat_state=CombatState(
                turn_order=TurnOrder(),
                status=CombatStatus.COMPLETE,
            ),
        )
        orch.run(initial_gs)

    registry = fake_gsr.load().actor_registry
    assert "npc:goblin" in registry.actors
    assert registry.actors["npc:goblin"].hp_current == wounded_goblin.hp_current
    assert TALIA.actor_id in registry.actors


def test_run_sets_campaign_context_on_narrator() -> None:
    """run() must call set_campaign_context with the campaign_id from the game state."""
    mock_narrator = MagicMock()
    fake_game_state = GameState(
        campaign=_default_campaign(),
        encounter=_make_state(),
        actor_registry=ActorRegistry(actors={"pc:talia": _default_player()}),
    )
    fake_gsr = FakeGameStateRepository(fake_game_state)
    orch = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=FakeMemoryRepository(), game_state=fake_gsr
        ),
        agents=OrchestratorAgents(
            rules=FakeRulesAgent(),
            narrator=mock_narrator,
        ),
        io=ScriptedIO([], on_exhaust="exit"),
        _player_intent_agent=FakePlayerIntentAgent(),
    )
    orch.run(fake_game_state)
    mock_narrator.set_campaign_context.assert_called_once_with("test-campaign")


def test_save_exit_preserves_registry_synced_by_prior_action() -> None:
    """Registry updated by a preceding action is not discarded on SAVE_EXIT."""
    goblin = replace(make_goblin_scout("npc:goblin", "Goblin Scout"), hp_current=5)
    encounter = EncounterState(
        encounter_id="enc-001",
        phase=EncounterPhase.SOCIAL,
        setting="The docks.",
        actor_ids=(TALIA.actor_id, "npc:goblin"),
        player_actor_id=TALIA.actor_id,
    )
    fake_gsr = FakeGameStateRepository(
        GameState(
            campaign=_default_campaign(),
            encounter=encounter,
            actor_registry=ActorRegistry(
                actors={TALIA.actor_id: TALIA, "npc:goblin": goblin}
            ),
        )
    )
    rules_agent = FakeRulesAgent(
        adjudications=[
            RulesAdjudication(
                is_legal=True,
                action_type="success",
                roll_requests=(),
                state_effects=(
                    StateEffect(effect_type="change_hp", target="npc:goblin", value=-2),
                ),
                summary="You graze the goblin.",
            )
        ]
    )
    orch = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=FakeMemoryRepository(), game_state=fake_gsr
        ),
        agents=OrchestratorAgents(rules=rules_agent, narrator=FakeNarratorAgent()),
        io=ScriptedIO(["attack goblin", "save and exit"]),
        _player_intent_agent=FakePlayerIntentAgent(
            intents=[
                PlayerIntent(category=IntentCategory.SKILL_CHECK, reason="attack"),
                PlayerIntent(category=IntentCategory.SAVE_EXIT, reason="quit"),
            ]
        ),
    )
    gs = fake_gsr.load()
    orch.run(gs)
    registry = fake_gsr.load().actor_registry
    assert "npc:goblin" in registry.actors
    assert registry.actors["npc:goblin"].hp_current == goblin.hp_current - 2


# ---------------------------------------------------------------------------
# run(GameState) — new primary interface
# ---------------------------------------------------------------------------


def _make_game_state_repo(initial: GameState) -> MagicMock:
    """Build a GameStateRepository mock that persists in memory."""
    repo = MagicMock(spec=GameStateRepository)
    cache: list[GameState] = [initial]

    def _load() -> GameState:
        return cache[-1]

    def _persist(gs: GameState) -> None:
        cache.append(gs)

    repo.load.side_effect = _load
    repo.persist.side_effect = _persist
    return repo


def test_run_returns_game_state(tmp_path: Path) -> None:
    """run() must return a GameState."""
    gs = _social_game_state(tmp_path)
    gs_repo = _make_game_state_repo(gs)
    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=FakeMemoryRepository(),
            game_state=gs_repo,
        ),
        agents=OrchestratorAgents(rules=FakeRulesAgent(), narrator=FakeNarratorAgent()),
        io=ScriptedIO(["exit"]),
        _player_intent_agent=FakePlayerIntentAgent([_intent(IntentCategory.SAVE_EXIT)]),
    )
    result = orchestrator.run(gs)
    assert isinstance(result, GameState)


def test_run_persists_once_on_save_exit(tmp_path: Path) -> None:
    """run() must call game_state_repo.persist() on SAVE_EXIT."""
    gs = _social_game_state(tmp_path)
    gs_repo = _make_game_state_repo(gs)
    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=FakeMemoryRepository(),
            game_state=gs_repo,
        ),
        agents=OrchestratorAgents(rules=FakeRulesAgent(), narrator=FakeNarratorAgent()),
        io=ScriptedIO(["save and exit the game"]),
        _player_intent_agent=FakePlayerIntentAgent([_intent(IntentCategory.SAVE_EXIT)]),
    )
    orchestrator.run(gs)
    gs_repo.persist.assert_called()


def test_run_scene_opening_stages_updated_state(tmp_path: Path) -> None:
    """run() must stage the post-opening state before entering the loop."""
    gs = _scene_opening_game_state(tmp_path)
    gs_repo = _make_game_state_repo(gs)
    narrator = FakeNarratorAgent(scene_tone="dark and stormy")
    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(
            memory=FakeMemoryRepository(),
            game_state=gs_repo,
        ),
        agents=OrchestratorAgents(rules=FakeRulesAgent(), narrator=narrator),
        io=ScriptedIO(["save and quit"]),
        _player_intent_agent=FakePlayerIntentAgent([_intent(IntentCategory.SAVE_EXIT)]),
    )
    result = orchestrator.run(gs)
    assert result.encounter is not None
    assert result.encounter.scene_tone == "dark and stormy"
    assert result.encounter.phase is EncounterPhase.SOCIAL
