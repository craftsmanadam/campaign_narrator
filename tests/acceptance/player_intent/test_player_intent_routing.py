"""Acceptance tests for EncounterOrchestrator player intent routing.

These tests inject fakes directly — no Docker, no WireMock, no live LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest
from campaignnarrator.domain.models import (
    CombatAssessment,
    CombatIntent,
    CombatOutcome,
    CritReview,
    EncounterPhase,
    EncounterState,
    GameState,
    IntentCategory,
    Narration,
    NarrationFrame,
    PlayerIntent,
    RulesAdjudication,
    RulesAdjudicationRequest,
)
from campaignnarrator.orchestrators.encounter_orchestrator import (
    EncounterOrchestrator,
    OrchestratorAgents,
    OrchestratorRepositories,
    OrchestratorTools,
)
from campaignnarrator.repositories.actor_repository import ActorRepository
from campaignnarrator.repositories.encounter_repository import EncounterRepository
from campaignnarrator.repositories.state_repository import StateRepository
from pytest_bdd import given, parsers, scenario, then, when

from tests.conftest import ScriptedIO
from tests.fixtures.fighter_talia import TALIA
from tests.fixtures.goblin_scout import make_goblin_scout

# ---------------------------------------------------------------------------
# Fake collaborators
# ---------------------------------------------------------------------------


class FakePlayerIntentAgent:
    """Returns a pre-configured PlayerIntent sequence on classify calls.

    Returns the first intent for the first call, then cycles to the last intent
    for all subsequent calls. This allows tests to control the first intent and
    ensure the loop terminates via a SAVE_EXIT intent on the final call.
    """

    _NO_INTENTS_MSG = "at least one intent must be provided"

    def __init__(self, *intents: PlayerIntent) -> None:
        if not intents:
            raise ValueError(self._NO_INTENTS_MSG)
        self._intents = list(intents)
        self._call_index: int = 0

    def classify(
        self,
        raw_text: str,
        *,
        phase: EncounterPhase,
        setting: str,
        recent_events: tuple[str, ...],
        actor_summaries: tuple[str, ...],
    ) -> PlayerIntent:
        index = min(self._call_index, len(self._intents) - 1)
        self._call_index += 1
        return self._intents[index]


class FakeRulesAgent:
    """Captures adjudication requests and returns a no-op adjudication."""

    def __init__(self) -> None:
        self.last_request: RulesAdjudicationRequest | None = None

    def adjudicate(self, request: RulesAdjudicationRequest) -> RulesAdjudication:
        self.last_request = request
        return RulesAdjudication(
            is_legal=True,
            action_type="free_action",
            summary="The action proceeds without complication.",
        )


class FakeNarratorAgent:
    """Returns stub narration; counts calls; supports CombatOrchestrator protocol."""

    def __init__(self) -> None:
        self.narrate_call_count: int = 0
        self._narration_log: list[str] = []

    def narrate(self, frame: NarrationFrame) -> Narration:
        self.narrate_call_count += 1
        self._narration_log.append(frame.purpose)
        return Narration(text=f"[narrated: {frame.purpose}]")

    def declare_npc_intent_from_json(self, context_json: str) -> str:
        return "The goblin holds its ground."

    def assess_combat_from_json(self, state_json: str) -> CombatAssessment:
        return CombatAssessment(
            combat_active=False,
            outcome=CombatOutcome(
                short_description="combat_over",
                full_description="The enemy has been defeated.",
            ),
        )

    def review_crit_from_json(self, context_json: str) -> CritReview:
        return CritReview(approved=False, reason="Downgraded for fairness.")


class FakeMemoryRepository:
    """Minimal memory repository that satisfies the EncounterOrchestrator contract."""

    def __init__(self) -> None:
        self.appended_events: list[dict] = []
        self.stored_narratives: list[tuple[str, dict]] = []

    def append_event(self, event: dict) -> None:
        self.appended_events.append(event)

    def store_narrative(self, text: str, metadata: dict) -> None:
        self.stored_narratives.append((text, metadata))


@dataclass
class FakeCombatIntentAgent:
    """Always returns 'end_turn' so the combat loop exits after one player prompt."""

    def run_sync(self, prompt: str) -> object:
        return _CombatIntentResult()


@dataclass
class _CombatIntentResult:
    output: CombatIntent = field(
        default_factory=lambda: CombatIntent(intent="end_turn")
    )


# ---------------------------------------------------------------------------
# Repository helpers
# ---------------------------------------------------------------------------


def _make_player() -> object:
    return TALIA


def _make_npc() -> object:
    return make_goblin_scout("npc:goblin-scout", "Goblin Scout")


def _make_social_repository(tmp_path: Path) -> StateRepository:
    actor_repo = ActorRepository(tmp_path)
    actor_repo.save(_make_player())
    encounter_repo = EncounterRepository(tmp_path)
    encounter_repo.save(
        EncounterState(
            encounter_id="goblin-camp",
            phase=EncounterPhase.SOCIAL,
            setting="A ruined roadside camp.",
            actors={
                "pc:talia": _make_player(),
                "npc:goblin-scout": _make_npc(),
            },
        )
    )
    return StateRepository(actor_repo=actor_repo, encounter_repo=encounter_repo)


# ---------------------------------------------------------------------------
# Shared context fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def context() -> dict:
    return {}


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


@scenario(
    "player_intent_routing.feature",
    "Present-tense attack routes to combat",
)
def test_attack_routes_to_combat() -> None:
    """Attack input with hostile intent transitions to combat phase."""


@scenario(
    "player_intent_routing.feature",
    "Past-tense recounting does not trigger combat",
)
def test_past_tense_does_not_trigger_combat() -> None:
    """Past-tense input classified as scene_observation stays in social phase."""


@scenario(
    "player_intent_routing.feature",
    "Save and exit saves state without narration agent involvement",
)
def test_save_exit_no_extra_narration() -> None:
    """Save-and-exit intent persists state and produces no further narration."""


@scenario(
    "player_intent_routing.feature",
    "Stealth attempt routes to skill check with correct hint",
)
def test_stealth_routes_to_skill_check() -> None:
    """Skill check intent with Stealth hint reaches the rules agent correctly."""


# ---------------------------------------------------------------------------
# Background step
# ---------------------------------------------------------------------------


@given("an active encounter in social phase", target_fixture="social_encounter_setup")
def active_social_encounter(tmp_path: Path, context: dict) -> dict:
    state_repo = _make_social_repository(tmp_path)
    memory_repo = FakeMemoryRepository()
    context["state_repo"] = state_repo
    context["memory_repo"] = memory_repo
    return context


# ---------------------------------------------------------------------------
# When steps
# ---------------------------------------------------------------------------


@when(parsers.parse('the player inputs "{player_input}" with hostile intent'))
def player_inputs_with_hostile_intent(
    player_input: str,
    social_encounter_setup: dict,
    context: dict,
) -> None:
    hostile_intent = PlayerIntent(
        category=IntentCategory.HOSTILE_ACTION,
        check_hint=None,
        reason="direct attack",
    )
    fake_narrator = FakeNarratorAgent()
    fake_rules = FakeRulesAgent()
    fake_player_intent = FakePlayerIntentAgent(hostile_intent)
    fake_combat_intent = FakeCombatIntentAgent()

    goblin_dead = make_goblin_scout("npc:goblin-scout", "Goblin Scout")
    goblin_dead = replace(goblin_dead, hp_current=0)
    io = ScriptedIO([player_input, "end turn"])

    state_repo: StateRepository = context["state_repo"]
    memory_repo: FakeMemoryRepository = context["memory_repo"]

    # Patch the encounter to have a dead goblin so combat resolves quickly
    game_state = state_repo.load()
    updated_actors = dict(game_state.encounter.actors)
    updated_actors["npc:goblin-scout"] = goblin_dead
    updated_encounter = replace(game_state.encounter, actors=updated_actors)
    state_repo.save(GameState(player=game_state.player, encounter=updated_encounter))

    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(state=state_repo, memory=memory_repo),
        agents=OrchestratorAgents(rules=fake_rules, narrator=fake_narrator),
        tools=OrchestratorTools(roll_dice=lambda _: 10),
        io=io,
        _player_intent_agent=fake_player_intent,
        _combat_intent_agent=fake_combat_intent,
    )
    orchestrator.run_encounter(encounter_id="goblin-camp")
    context["final_state"] = state_repo.load().encounter


@when(parsers.parse('the player inputs "{player_input}" with scene observation intent'))
def player_inputs_with_scene_observation_intent(
    player_input: str,
    social_encounter_setup: dict,
    context: dict,
) -> None:
    scene_observation_intent = PlayerIntent(
        category=IntentCategory.SCENE_OBSERVATION,
        check_hint=None,
        reason="recounting past events",
    )
    # Second intent terminates the loop gracefully after the first action is handled
    save_exit_intent = PlayerIntent(
        category=IntentCategory.SAVE_EXIT,
        check_hint=None,
        reason="exiting after observation",
    )
    fake_narrator = FakeNarratorAgent()
    fake_rules = FakeRulesAgent()
    fake_player_intent = FakePlayerIntentAgent(
        scene_observation_intent, save_exit_intent
    )

    # Provide two inputs: the actual observation input and an exit command
    io = ScriptedIO([player_input, "exit"])

    state_repo: StateRepository = context["state_repo"]
    memory_repo: FakeMemoryRepository = context["memory_repo"]

    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(state=state_repo, memory=memory_repo),
        agents=OrchestratorAgents(rules=fake_rules, narrator=fake_narrator),
        tools=OrchestratorTools(roll_dice=lambda _: 10),
        io=io,
        _player_intent_agent=fake_player_intent,
    )
    orchestrator.run_encounter(encounter_id="goblin-camp")
    context["final_state"] = state_repo.load().encounter
    context["narrator_agent"] = fake_narrator


@when(parsers.parse('the player inputs "{player_input}" with save exit intent'))
def player_inputs_with_save_exit_intent(
    player_input: str,
    social_encounter_setup: dict,
    context: dict,
) -> None:
    save_exit_intent = PlayerIntent(
        category=IntentCategory.SAVE_EXIT,
        check_hint=None,
        reason="player wants to save",
    )
    fake_narrator = FakeNarratorAgent()
    fake_rules = FakeRulesAgent()
    fake_player_intent = FakePlayerIntentAgent(save_exit_intent)

    io = ScriptedIO([player_input])

    state_repo: StateRepository = context["state_repo"]
    memory_repo: FakeMemoryRepository = context["memory_repo"]

    narrate_count_before = fake_narrator.narrate_call_count
    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(state=state_repo, memory=memory_repo),
        agents=OrchestratorAgents(rules=fake_rules, narrator=fake_narrator),
        tools=OrchestratorTools(roll_dice=lambda _: 10),
        io=io,
        _player_intent_agent=fake_player_intent,
    )
    orchestrator.run_encounter(encounter_id="goblin-camp")

    context["final_state"] = state_repo.load().encounter
    context["memory_repo"] = memory_repo
    context["narrator_agent"] = fake_narrator
    context["narrate_count_before"] = narrate_count_before


@when(
    parsers.parse(
        'the player inputs "{player_input}" with skill check intent for Stealth'
    )
)
def player_inputs_with_skill_check_intent(
    player_input: str,
    social_encounter_setup: dict,
    context: dict,
) -> None:
    skill_check_intent = PlayerIntent(
        category=IntentCategory.SKILL_CHECK,
        check_hint="Stealth",
        reason="attempting to sneak",
    )
    # Second intent terminates the loop after the skill check is handled
    save_exit_intent = PlayerIntent(
        category=IntentCategory.SAVE_EXIT,
        check_hint=None,
        reason="exiting after skill check",
    )
    fake_narrator = FakeNarratorAgent()
    fake_rules = FakeRulesAgent()
    fake_player_intent = FakePlayerIntentAgent(skill_check_intent, save_exit_intent)

    io = ScriptedIO([player_input, "exit"])

    state_repo: StateRepository = context["state_repo"]
    memory_repo: FakeMemoryRepository = context["memory_repo"]

    orchestrator = EncounterOrchestrator(
        repositories=OrchestratorRepositories(state=state_repo, memory=memory_repo),
        agents=OrchestratorAgents(rules=fake_rules, narrator=fake_narrator),
        tools=OrchestratorTools(roll_dice=lambda _: 10),
        io=io,
        _player_intent_agent=fake_player_intent,
    )
    orchestrator.run_encounter(encounter_id="goblin-camp")

    context["final_state"] = state_repo.load().encounter
    context["rules_agent"] = fake_rules


# ---------------------------------------------------------------------------
# Then steps
# ---------------------------------------------------------------------------


@then("the encounter transitions to combat phase")
def encounter_transitions_to_combat(context: dict) -> None:
    final_state: EncounterState = context["final_state"]
    assert final_state is not None
    # After combat resolves, outcome should be "combat" (set when entering combat)
    assert final_state.outcome == "combat"


@then("the encounter remains in social phase")
def encounter_remains_in_social(context: dict) -> None:
    final_state: EncounterState = context["final_state"]
    assert final_state is not None
    assert final_state.phase is EncounterPhase.SOCIAL


@then(parsers.parse("a narration is produced for {purpose}"))
def narration_produced_for_purpose(purpose: str, context: dict) -> None:
    narrator: FakeNarratorAgent = context["narrator_agent"]
    assert any(purpose in log for log in narrator._narration_log)


@then("the encounter is saved")
def encounter_is_saved(context: dict) -> None:
    memory_repo: FakeMemoryRepository = context["memory_repo"]
    saved_events = [
        e for e in memory_repo.appended_events if e.get("type") == "encounter_saved"
    ]
    assert len(saved_events) >= 1


@then("no narration is produced after scene opening")
def no_narration_after_scene_opening(context: dict) -> None:
    narrator: FakeNarratorAgent = context["narrator_agent"]
    # The scene is SOCIAL (not SCENE_OPENING) so no scene_opening narration occurs.
    # After save-exit intent is processed, no additional narration should be produced.
    # narrate_call_count should be 0 since scene starts in SOCIAL phase (no scene_opening
    # narration) and save-exit exits without calling narrate.
    assert narrator.narrate_call_count == 0


@then(
    parsers.parse(
        "the rules agent receives a request with check_hints containing Stealth"
    )
)
def rules_agent_receives_stealth_hint(context: dict) -> None:
    rules_agent: FakeRulesAgent = context["rules_agent"]
    assert rules_agent.last_request is not None
    assert "Stealth" in rules_agent.last_request.check_hints
