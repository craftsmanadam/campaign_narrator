"""Integration tests for EncounterOrchestrator intent routing.

Tests that the right handler fires for each intent category.
Real orchestrator, real domain models, fake agents and repos.
No Docker, no WireMock, no live LLM calls.

Entry point: _run_loop() — avoids SCENE_OPENING setup while exercising
full routing logic through real match/case and _apply_action paths.
"""

from __future__ import annotations

from collections.abc import Mapping
from unittest.mock import patch

import pytest
from campaignnarrator.domain.models import (
    ActorRegistry,
    CampaignState,
    CombatAssessment,
    CombatOutcome,
    EncounterPhase,
    EncounterState,
    GameState,
    IntentCategory,
    Milestone,
    ModuleState,
    Narration,
    NarrationFrame,
    NpcPresence,
    PlayerIntent,
    RulesAdjudication,
    RulesAdjudicationRequest,
)
from campaignnarrator.orchestrators.encounter_orchestrator import (
    EncounterOrchestrator,
    OrchestratorAgents,
    OrchestratorRepositories,
)

from tests.conftest import ScriptedIO
from tests.fixtures.fighter_talia import TALIA

# ── Fakes ─────────────────────────────────────────────────────────────────────


class _FakeMemory:
    def __init__(self) -> None:
        self.staged: list[tuple[str, dict]] = []
        self.events: list[dict] = []
        self.narratives: list[tuple[str, dict]] = []
        self.exchanges: list[tuple[str, str]] = []

    def get_exchange_buffer(self) -> tuple[str, ...]:
        return ()

    def retrieve_relevant(
        self, query: str, *, campaign_id: str, limit: int = 5
    ) -> list[str]:
        return []

    def stage_narration(self, text: str, metadata: dict) -> None:
        self.staged.append((text, metadata))

    def store_narrative(self, text: str, metadata: dict) -> None:
        self.narratives.append((text, metadata))

    def update_exchange(self, player_input: str, narrator_output: str) -> None:
        self.exchanges.append((player_input, narrator_output))

    def append_event(self, event: Mapping[str, object]) -> None:
        self.events.append(dict(event))


class _FakeGameStateRepo:
    def __init__(self, initial: GameState) -> None:
        self._states: list[GameState] = [initial]
        self.persist_count = 0

    def load(self) -> GameState:
        return self._states[-1]

    def persist(self, gs: GameState) -> None:
        self._states.append(gs)
        self.persist_count += 1


class _FakeRules:
    def __init__(self, adjudications: list[RulesAdjudication] | None = None) -> None:
        self._adjudications = list(adjudications or [])
        self.call_count = 0

    def adjudicate(self, _request: RulesAdjudicationRequest) -> RulesAdjudication:
        self.call_count += 1
        if not self._adjudications:
            pytest.fail("_FakeRules: no more adjudications queued")
        return self._adjudications.pop(0)


class _FakeNarrator:
    def __init__(self) -> None:
        self.narrate_count = 0

    def set_campaign_context(self, _campaign_id: str) -> None:
        pass

    def narrate(self, _frame: NarrationFrame) -> Narration:
        self.narrate_count += 1
        return Narration(text="The scene unfolds.")

    def summarize_encounter_partial(self, _encounter: object) -> str:
        return "A partial encounter summary."

    def declare_npc_intent_from_json(self, _context_json: str) -> str:
        return "The NPC acts."

    def assess_combat_from_json(self, _state_json: str) -> CombatAssessment:
        return CombatAssessment(
            combat_active=False,
            outcome=CombatOutcome(short_description="Over", full_description="Done."),
        )


class _FakeIntentAgent:
    """Returns scripted intents; defaults to SAVE_EXIT when queue is exhausted."""

    def __init__(self, intents: list[PlayerIntent]) -> None:
        self._intents = list(intents)

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
        if self._intents:
            return self._intents.pop(0)
        return PlayerIntent(category=IntentCategory.SAVE_EXIT, reason="exhausted")


# ── Shared builders ────────────────────────────────────────────────────────────

_MILESTONE = Milestone(
    milestone_id="m1", title="First Blood", description="Enter city."
)

_CAMPAIGN = CampaignState(
    campaign_id="c1",
    name="Test Campaign",
    setting="A dark world.",
    narrator_personality="Grim.",
    hidden_goal="Defeat the lich.",
    bbeg_name="Malachar",
    bbeg_description="A lich.",
    milestones=(_MILESTONE,),
    current_milestone_index=0,
    starting_level=1,
    target_level=5,
    player_brief="Dark fantasy.",
    player_actor_id=TALIA.actor_id,
)

_MODULE = ModuleState(
    module_id="module-001",
    campaign_id="c1",
    title="Test Module",
    summary="A test module.",
    guiding_milestone_id="m1",
)


def _make_social_game_state() -> GameState:
    encounter = EncounterState(
        encounter_id="test-enc-001",
        phase=EncounterPhase.SOCIAL,
        setting="A goblin camp.",
        actor_ids=(TALIA.actor_id,),
        player_actor_id=TALIA.actor_id,
    )
    return GameState(
        actor_registry=ActorRegistry(actors={TALIA.actor_id: TALIA}),
        encounter=encounter,
        campaign=_CAMPAIGN,
        module=_MODULE,
    )


def _success_adjudication() -> RulesAdjudication:
    return RulesAdjudication(
        is_legal=True,
        action_type="success",
        summary="Action succeeds.",
        roll_requests=(),
        state_effects=(),
    )


def _make_orchestrator(
    intents: list[PlayerIntent],
    rules: _FakeRules | None = None,
) -> tuple[
    EncounterOrchestrator, _FakeRules, _FakeNarrator, _FakeGameStateRepo, _FakeMemory
]:
    game_state = _make_social_game_state()
    memory = _FakeMemory()
    gs_repo = _FakeGameStateRepo(game_state)
    rules_agent = rules or _FakeRules()
    narrator = _FakeNarrator()
    io = ScriptedIO(["action input"] * 10, on_exhaust="save and quit")
    orch = EncounterOrchestrator(
        repositories=OrchestratorRepositories(memory=memory, game_state=gs_repo),
        agents=OrchestratorAgents(rules=rules_agent, narrator=narrator),
        io=io,
        _player_intent_agent=_FakeIntentAgent(intents),
    )
    return orch, rules_agent, narrator, gs_repo, memory


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestIntentRouting:
    def test_hostile_action_enters_combat_via_run_combat(self) -> None:
        """HOSTILE_ACTION sets phase to COMBAT, triggering _run_combat."""
        game_state = _make_social_game_state()
        intent = PlayerIntent(
            category=IntentCategory.HOSTILE_ACTION, reason="I attack."
        )
        orch, _, _, _, _ = _make_orchestrator([intent])

        with patch.object(orch, "_run_combat", return_value=game_state) as mock_combat:
            orch._run_loop(game_state)

        mock_combat.assert_called_once()

    def test_save_exit_persists_state_and_displays_game_saved(self) -> None:
        """SAVE_EXIT calls persist and displays a save confirmation."""
        game_state = _make_social_game_state()
        intent = PlayerIntent(category=IntentCategory.SAVE_EXIT, reason="quit")
        orch, _, _, gs_repo, _ = _make_orchestrator([intent])
        io = orch._io

        orch._run_loop(game_state)

        assert gs_repo.persist_count >= 1
        assert any("saved" in msg.lower() for msg in io.displayed)

    def test_skill_check_invokes_rules_agent(self) -> None:
        """SKILL_CHECK routes to rules adjudication; rules agent called exactly once."""
        game_state = _make_social_game_state()
        intents = [
            PlayerIntent(
                category=IntentCategory.SKILL_CHECK,
                check_hint="Perception",
                reason="I look around carefully.",
            ),
            PlayerIntent(category=IntentCategory.SAVE_EXIT, reason="quit"),
        ]
        rules = _FakeRules([_success_adjudication()])
        orch, rules_agent, _, _, _ = _make_orchestrator(intents, rules=rules)

        orch._run_loop(game_state)

        assert rules_agent.call_count == 1

    def test_scene_observation_uses_narrator_not_rules(self) -> None:
        """SCENE_OBSERVATION routes to narrator only — rules agent never called."""
        game_state = _make_social_game_state()
        intents = [
            PlayerIntent(
                category=IntentCategory.SCENE_OBSERVATION,
                reason="I examine the camp.",
            ),
            PlayerIntent(category=IntentCategory.SAVE_EXIT, reason="quit"),
        ]
        orch, rules_agent, narrator, _, _ = _make_orchestrator(intents)

        orch._run_loop(game_state)

        assert rules_agent.call_count == 0
        assert narrator.narrate_count >= 1

    def test_npc_dialogue_uses_narrator_not_rules(self) -> None:
        """NPC_DIALOGUE routes to narrator only — rules agent never called."""
        game_state = _make_social_game_state()
        intents = [
            PlayerIntent(
                category=IntentCategory.NPC_DIALOGUE,
                reason="I talk to the goblin.",
            ),
            PlayerIntent(category=IntentCategory.SAVE_EXIT, reason="quit"),
        ]
        orch, rules_agent, narrator, _, _ = _make_orchestrator(intents)

        orch._run_loop(game_state)

        assert rules_agent.call_count == 0
        assert narrator.narrate_count >= 1
