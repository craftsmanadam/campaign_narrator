"""Unit tests for the narrator agent."""

from __future__ import annotations

import json
from dataclasses import replace
from unittest.mock import MagicMock

import pytest
from campaignnarrator.adapters.pydantic_ai_adapter import PydanticAIAdapter
from campaignnarrator.agents.narrator_agent import NarratorAgent
from campaignnarrator.domain.models import (
    ActorState,
    CampaignState,
    CombatAssessment,
    CritReview,
    EncounterPhase,
    EncounterState,
    Milestone,
    ModuleState,
    NarrationFrame,
    NextEncounterPlan,
    SceneOpeningResponse,
)
from campaignnarrator.repositories.memory_repository import MemoryRepository
from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from tests.fixtures.fighter_talia import TALIA


def _make_assess_model(data: dict) -> FunctionModel:
    """FunctionModel that returns a CombatAssessment tool call."""

    def fn(messages, info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[ToolCallPart("final_result", json.dumps(data))])

    return FunctionModel(fn)


def _make_crit_model(data: dict) -> FunctionModel:
    """FunctionModel that returns a CritReview tool call."""

    def fn(messages, info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[ToolCallPart("final_result", json.dumps(data))])

    return FunctionModel(fn)


def _frame(purpose: str = "social_resolution") -> NarrationFrame:
    return NarrationFrame(
        purpose=purpose,
        phase=EncounterPhase.SOCIAL,
        setting="A ruined roadside camp.",
        public_actor_summaries=("Talia has 12 of 12 hit points.",),
        visible_npc_summaries=("Goblin Scout is wary.",),
        recent_public_events=("Talia offers peace.",),
        resolved_outcomes=("Encounter outcome: peaceful",),
        allowed_disclosures=("visible_npcs", "public_events"),
    )


def _make_narrator(
    text: str = "The goblins lower their weapons.",
    scene_response: SceneOpeningResponse | None = None,
) -> tuple[NarratorAgent, MagicMock, MagicMock]:
    """Return (narrator, mock_adapter, mock_scene_agent)."""
    mock_adapter = MagicMock()
    mock_adapter.generate_text.return_value = text

    mock_scene_agent = MagicMock()
    if scene_response is not None:
        mock_scene_agent.run_sync.return_value.output = scene_response

    narrator = NarratorAgent(
        adapter=mock_adapter,
        personality="Test narrator.",
        _scene_agent=mock_scene_agent,
        _assess_agent=MagicMock(),
        _crit_agent=MagicMock(),
        _plan_agent=MagicMock(),
    )
    return narrator, mock_adapter, mock_scene_agent


def test_narrator_uses_generate_text_for_non_opening_frames() -> None:
    narrator, mock_adapter, _ = _make_narrator("The goblins lower their weapons.")
    result = narrator.narrate(_frame("social_resolution"))
    assert result.text == "The goblins lower their weapons."
    assert result.audience == "player"
    mock_adapter.generate_text.assert_called_once()


def test_narrator_rejects_empty_text_output() -> None:
    narrator, _, __ = _make_narrator("   ")
    with pytest.raises(ValueError, match="empty narration output"):
        narrator.narrate(_frame())


def test_narrator_prompt_includes_safety_guardrails() -> None:
    narrator, mock_adapter, _ = _make_narrator()
    narrator.narrate(_frame("recap_response"))
    call_kwargs = mock_adapter.generate_text.call_args[1]
    assert "Do not invent mechanics" in call_kwargs["instructions"]
    assert (
        "Use only provided public and allowed context." in call_kwargs["instructions"]
    )


def test_narrator_input_includes_disclosures_and_outcomes() -> None:
    narrator, mock_adapter, _ = _make_narrator()
    narrator.narrate(_frame("status_response"))
    call_kwargs = mock_adapter.generate_text.call_args[1]
    assert '"allowed_disclosures": [' in call_kwargs["input_text"]
    assert '"resolved_outcomes": [' in call_kwargs["input_text"]


def test_narrator_personality_is_prepended_to_instructions() -> None:
    narrator, mock_adapter, _ = _make_narrator()
    narrator.narrate(_frame())
    call_kwargs = mock_adapter.generate_text.call_args[1]
    assert call_kwargs["instructions"].startswith("Test narrator.")


def test_narrate_scene_opening_calls_scene_agent() -> None:
    scene_response = SceneOpeningResponse(
        text="The camp looms ahead.",
        scene_tone="tense and foreboding",
    )
    narrator, mock_adapter, mock_scene_agent = _make_narrator(
        scene_response=scene_response
    )

    result = narrator.narrate(
        NarrationFrame(
            purpose="scene_opening",
            phase=EncounterPhase.SCENE_OPENING,
            setting="Forest",
            public_actor_summaries=(),
            visible_npc_summaries=(),
            recent_public_events=(),
            resolved_outcomes=(),
            allowed_disclosures=(),
        )
    )

    assert result.text == "The camp looms ahead."
    assert result.scene_tone == "tense and foreboding"
    mock_scene_agent.run_sync.assert_called_once()
    mock_adapter.generate_text.assert_not_called()


def test_narrate_non_opening_does_not_use_scene_agent() -> None:
    narrator, mock_adapter, mock_scene_agent = _make_narrator("Some narration.")
    result = narrator.narrate(_frame("social_resolution"))
    assert result.scene_tone is None
    mock_scene_agent.run_sync.assert_not_called()
    mock_adapter.generate_text.assert_called_once()


def test_narrate_scene_opening_prepends_personality_to_scene_instructions() -> None:
    mock_scene_agent = MagicMock()
    narrator = NarratorAgent(
        adapter=MagicMock(),
        personality="Gothic style.",
        _scene_agent=mock_scene_agent,
        _assess_agent=MagicMock(),
        _crit_agent=MagicMock(),
        _plan_agent=MagicMock(),
    )
    assert "Gothic style." in narrator._scene_instructions
    assert "opening a new encounter scene" in narrator._scene_instructions


# ---------------------------------------------------------------------------
# declare_npc_intent_from_json
# ---------------------------------------------------------------------------


def test_declare_npc_intent_from_json_returns_prose_string() -> None:
    """declare_npc_intent_from_json should return the adapter generate_text output."""
    adapter = MagicMock(spec=PydanticAIAdapter)
    adapter.generate_text.return_value = (
        "The goblin scout eyes Talia hungrily and raises its scimitar."
    )
    narrator = NarratorAgent(
        adapter=adapter,
        _scene_agent=MagicMock(),
        _assess_agent=MagicMock(),
        _crit_agent=MagicMock(),
        _plan_agent=MagicMock(),
    )
    context_json = json.dumps(
        {"actor_id": "npc:goblin-1", "name": "Goblin Scout", "hp_current": 7}
    )
    result = narrator.declare_npc_intent_from_json(context_json)
    assert result == "The goblin scout eyes Talia hungrily and raises its scimitar."
    adapter.generate_text.assert_called_once()
    _, call_kwargs = adapter.generate_text.call_args
    assert call_kwargs["input_text"] == context_json


def test_declare_npc_intent_from_json_raises_value_error_on_blank_response() -> None:
    """Blank prose output should fail closed with ValueError."""
    adapter = MagicMock(spec=PydanticAIAdapter)
    adapter.generate_text.return_value = "   "
    narrator = NarratorAgent(
        adapter=adapter,
        _scene_agent=MagicMock(),
        _assess_agent=MagicMock(),
        _crit_agent=MagicMock(),
        _plan_agent=MagicMock(),
    )
    with pytest.raises(ValueError, match="empty npc intent"):
        narrator.declare_npc_intent_from_json(json.dumps({"actor_id": "npc:goblin-1"}))


# ---------------------------------------------------------------------------
# assess_combat_from_json
# ---------------------------------------------------------------------------


def test_assess_combat_from_json_returns_active_assessment_when_combat_continues() -> (
    None
):
    """When the model signals combat is still active, outcome must be None."""
    assess_agent = Agent(
        _make_assess_model({"combat_active": True, "outcome": None}),
        output_type=CombatAssessment,
        instructions="assess",
    )
    adapter = MagicMock(spec=PydanticAIAdapter)
    narrator = NarratorAgent(
        adapter=adapter,
        _scene_agent=MagicMock(),
        _assess_agent=assess_agent,
        _crit_agent=MagicMock(),
        _plan_agent=MagicMock(),
    )
    assessment = narrator.assess_combat_from_json(
        json.dumps({"actors": [], "recent_events": []})
    )
    assert isinstance(assessment, CombatAssessment)
    assert assessment.combat_active is True
    assert assessment.outcome is None


def test_assess_combat_from_json_returns_inactive_assessment_with_outcome() -> None:
    """When combat ends, the assessment must carry a populated CombatOutcome."""
    assess_agent = Agent(
        _make_assess_model(
            {
                "combat_active": False,
                "outcome": {
                    "short_description": "Goblins routed",
                    "full_description": (
                        "The last goblin stumbles away, broken and bleeding."
                    ),
                },
            }
        ),
        output_type=CombatAssessment,
        instructions="assess",
    )
    adapter = MagicMock(spec=PydanticAIAdapter)
    narrator = NarratorAgent(
        adapter=adapter,
        _scene_agent=MagicMock(),
        _assess_agent=assess_agent,
        _crit_agent=MagicMock(),
        _plan_agent=MagicMock(),
    )
    assessment = narrator.assess_combat_from_json(
        json.dumps({"actors": [], "recent_events": []})
    )
    assert assessment.combat_active is False
    assert assessment.outcome is not None
    assert assessment.outcome.short_description == "Goblins routed"
    assert "broken and bleeding" in assessment.outcome.full_description


def test_assess_combat_from_json_raises_value_error_when_inactive_but_no_outcome() -> (
    None
):
    """combat_active=False with outcome=None is a semantic error — must raise."""
    assess_agent = Agent(
        _make_assess_model({"combat_active": False, "outcome": None}),
        output_type=CombatAssessment,
        instructions="assess",
    )
    adapter = MagicMock(spec=PydanticAIAdapter)
    narrator = NarratorAgent(
        adapter=adapter,
        _scene_agent=MagicMock(),
        _assess_agent=assess_agent,
        _crit_agent=MagicMock(),
        _plan_agent=MagicMock(),
    )
    with pytest.raises(ValueError, match="combat_active=False but no outcome"):
        narrator.assess_combat_from_json(
            json.dumps({"actors": [], "recent_events": []})
        )


# ---------------------------------------------------------------------------
# review_crit_from_json
# ---------------------------------------------------------------------------


def test_review_crit_from_json_returns_approved_review() -> None:
    """Approved critical hit should return CritReview(approved=True)."""
    crit_agent = Agent(
        _make_crit_model({"approved": True, "reason": None}),
        output_type=CritReview,
        instructions="review crit",
    )
    adapter = MagicMock(spec=PydanticAIAdapter)
    narrator = NarratorAgent(
        adapter=adapter,
        _scene_agent=MagicMock(),
        _assess_agent=MagicMock(),
        _crit_agent=crit_agent,
        _plan_agent=MagicMock(),
    )
    review = narrator.review_crit_from_json(
        json.dumps({"attacker": "npc:goblin-1", "target": "pc:talia", "damage": 8})
    )
    assert isinstance(review, CritReview)
    assert review.approved is True
    assert review.reason is None


def test_review_crit_from_json_returns_downgraded_review_with_reason() -> None:
    """Downgraded critical hit should return CritReview(approved=False, reason=...)."""
    crit_agent = Agent(
        _make_crit_model(
            {
                "approved": False,
                "reason": "Would be unfair this early in the encounter.",
            }
        ),
        output_type=CritReview,
        instructions="review crit",
    )
    adapter = MagicMock(spec=PydanticAIAdapter)
    narrator = NarratorAgent(
        adapter=adapter,
        _scene_agent=MagicMock(),
        _assess_agent=MagicMock(),
        _crit_agent=crit_agent,
        _plan_agent=MagicMock(),
    )
    review = narrator.review_crit_from_json(
        json.dumps({"attacker": "npc:goblin-1", "target": "pc:talia", "damage": 8})
    )
    assert review.approved is False
    assert review.reason == "Would be unfair this early in the encounter."


# ---------------------------------------------------------------------------
# retrieve_memory, summarize_encounter, plan_next_encounter
# ---------------------------------------------------------------------------


def _make_narrator_with_memory(
    memory_returns: list[str] | None = None,
) -> tuple[NarratorAgent, MagicMock]:
    mock_adapter = MagicMock()
    mock_adapter.generate_text.return_value = "Some narration."
    mock_memory_repo = MagicMock(spec=MemoryRepository)
    mock_memory_repo.retrieve_relevant.return_value = memory_returns or []
    narrator = NarratorAgent(
        adapter=mock_adapter,
        personality="Grim narrator.",
        memory_repository=mock_memory_repo,
        _scene_agent=MagicMock(),
        _assess_agent=MagicMock(),
        _crit_agent=MagicMock(),
        _plan_agent=MagicMock(),
    )
    return narrator, mock_memory_repo


def _make_completed_encounter() -> EncounterState:
    return EncounterState(
        encounter_id="module-001-enc-001",
        phase=EncounterPhase.ENCOUNTER_COMPLETE,
        setting="The fog-shrouded docks of Darkholm.",
        actors={},
        public_events=("Aldric fought a cultist.",),
        outcome=(
            "The cultist was subdued and revealed the location of the Drowned Lady."
        ),
    )


def _make_module_for_narrator() -> ModuleState:
    return ModuleState(
        module_id="module-001",
        campaign_id="c-1",
        title="The Dockside Murders",
        summary="Bodies wash ashore.",
        guiding_milestone_id="m1",
    )


def _make_campaign_for_narrator() -> CampaignState:
    return CampaignState(
        campaign_id="c-1",
        name="The Cursed Coast",
        setting="A fog-draped coastal city.",
        narrator_personality="Grim and dramatic.",
        hidden_goal="Awaken the drowned god.",
        bbeg_name="Malachar",
        bbeg_description="A lich.",
        milestones=(
            Milestone(milestone_id="m1", title="First Blood", description="Survive."),
        ),
        current_milestone_index=0,
        starting_level=1,
        target_level=5,
        player_brief="Dark coastal horror.",
        player_actor_id="pc:player",
    )


# --- retrieve_memory tests ---


def test_retrieve_memory_returns_joined_results() -> None:
    narrator, mock_repo = _make_narrator_with_memory(
        memory_returns=["Entry one.", "Entry two."]
    )
    result = narrator.retrieve_memory("docks")
    mock_repo.retrieve_relevant.assert_called_once_with("docks", limit=5)
    assert "Entry one." in result
    assert "Entry two." in result


def test_retrieve_memory_no_results_returns_sentinel() -> None:
    narrator, _ = _make_narrator_with_memory(memory_returns=[])
    result = narrator.retrieve_memory("nothing")
    assert result == "No prior records found."


def test_retrieve_memory_no_repo_returns_sentinel() -> None:
    mock_adapter = MagicMock()
    narrator = NarratorAgent(
        adapter=mock_adapter,
        _scene_agent=MagicMock(),
        _assess_agent=MagicMock(),
        _crit_agent=MagicMock(),
        _plan_agent=MagicMock(),
    )
    result = narrator.retrieve_memory("anything")
    assert result == "No prior records found."


# --- summarize_encounter tests ---


def test_summarize_encounter_returns_adapter_text() -> None:
    narrator, _ = _make_narrator_with_memory()
    narrator._adapter.generate_text.return_value = "Rich session notes prose here."
    summary = narrator.summarize_encounter(
        _make_completed_encounter(),
        _make_module_for_narrator(),
        _make_campaign_for_narrator(),
    )
    assert summary == "Rich session notes prose here."
    narrator._adapter.generate_text.assert_called_once()


def test_summarize_encounter_includes_setting_in_prompt() -> None:
    narrator, _ = _make_narrator_with_memory()
    narrator._adapter.generate_text.return_value = "Notes."
    narrator.summarize_encounter(
        _make_completed_encounter(),
        _make_module_for_narrator(),
        _make_campaign_for_narrator(),
    )
    call_kwargs = narrator._adapter.generate_text.call_args[1]
    assert "fog-shrouded docks" in call_kwargs["input_text"]


def test_summarize_encounter_includes_outcome_in_prompt() -> None:
    narrator, _ = _make_narrator_with_memory()
    narrator._adapter.generate_text.return_value = "Notes."
    narrator.summarize_encounter(
        _make_completed_encounter(),
        _make_module_for_narrator(),
        _make_campaign_for_narrator(),
    )
    call_kwargs = narrator._adapter.generate_text.call_args[1]
    assert "Drowned Lady" in call_kwargs["input_text"]


# --- plan_next_encounter tests ---


def _make_plan_model(seed: str, milestone_achieved: bool) -> FunctionModel:
    data = {"seed": seed, "milestone_achieved": milestone_achieved}

    def fn(messages: object, info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[ToolCallPart("final_result", json.dumps(data))])

    return FunctionModel(fn)


def _make_player_actor() -> ActorState:
    return replace(TALIA, actor_id="pc:player", name="Aldric", race="Human")


def test_plan_next_encounter_returns_next_encounter_plan() -> None:
    narrator, _ = _make_narrator_with_memory()
    plan_model = _make_plan_model(
        seed="The warehouse district at midnight.",
        milestone_achieved=False,
    )
    narrator._plan_agent = Agent(plan_model, output_type=NextEncounterPlan)
    _milestone = Milestone(
        milestone_id="m1", title="First Blood", description="Survive."
    )
    result = narrator.plan_next_encounter(
        campaign=_make_campaign_for_narrator(),
        module=_make_module_for_narrator(),
        milestone=_milestone,
        player=_make_player_actor(),
        last_outcome="Cultist subdued.",
    )
    assert result.seed == "The warehouse district at midnight."
    assert result.milestone_achieved is False


def test_plan_next_encounter_milestone_achieved_true() -> None:
    narrator, _ = _make_narrator_with_memory()
    plan_model = _make_plan_model(seed="", milestone_achieved=True)
    narrator._plan_agent = Agent(plan_model, output_type=NextEncounterPlan)
    _milestone = Milestone(
        milestone_id="m1", title="First Blood", description="Survive."
    )
    result = narrator.plan_next_encounter(
        campaign=_make_campaign_for_narrator(),
        module=_make_module_for_narrator(),
        milestone=_milestone,
        player=_make_player_actor(),
        last_outcome="Malachar defeated.",
    )
    assert result.milestone_achieved is True


def _make_scene_response_model(
    text: str = "You arrive at the docks.",
    scene_tone: str = "tense and foreboding",
) -> FunctionModel:
    """FunctionModel that immediately returns a SceneOpeningResponse."""

    def fn(messages: object, info: AgentInfo) -> ModelResponse:
        return ModelResponse(
            parts=[
                ToolCallPart(
                    "final_result",
                    json.dumps({"text": text, "scene_tone": scene_tone}),
                )
            ]
        )

    return FunctionModel(fn)


def _make_scene_frame(setting: str = "The docks at midnight.") -> NarrationFrame:
    return NarrationFrame(
        purpose="scene_opening",
        phase=EncounterPhase.SCENE_OPENING,
        setting=setting,
        public_actor_summaries=(),
        visible_npc_summaries=(),
        recent_public_events=(),
        resolved_outcomes=(),
        allowed_disclosures=(),
    )


def _make_scene_narrator(
    memory_returns: list[str] | None = None,
    mock_repo: MagicMock | None = None,
) -> tuple[NarratorAgent, MagicMock, MagicMock]:
    """Build a narrator with a mock scene agent and optional memory repo."""
    scene_response = SceneOpeningResponse(
        text="You arrive at the docks.", scene_tone="tense and foreboding"
    )
    mock_scene_agent = MagicMock()
    mock_scene_agent.run_sync.return_value.output = scene_response

    if mock_repo is None:
        mock_repo = MagicMock(spec=MemoryRepository)
        mock_repo.retrieve_relevant.return_value = memory_returns or []

    narrator = NarratorAgent(
        adapter=MagicMock(),
        memory_repository=mock_repo,
        _scene_agent=mock_scene_agent,
        _assess_agent=MagicMock(),
        _crit_agent=MagicMock(),
        _plan_agent=MagicMock(),
    )
    return narrator, mock_repo, mock_scene_agent


def test_scene_opening_retrieves_memory_with_setting_as_query() -> None:
    """Prior to _scene_agent, retrieve_memory must be called with the frame setting."""
    narrator, mock_repo, mock_scene_agent = _make_scene_narrator(
        memory_returns=["Malachar had pale hollow eyes."]
    )
    narrator.narrate(_make_scene_frame("The docks at midnight."))

    mock_repo.retrieve_relevant.assert_called_once_with("The docks at midnight.", limit=5)
    call_args = mock_scene_agent.run_sync.call_args[0][0]
    assert "Malachar had pale hollow eyes." in call_args


def test_scene_opening_injects_sentinel_when_no_memory_matches() -> None:
    """When no memory matches, sentinel appears in the scene agent input."""
    narrator, mock_repo, mock_scene_agent = _make_scene_narrator(memory_returns=[])
    narrator.narrate(_make_scene_frame("Forest"))

    call_args = mock_scene_agent.run_sync.call_args[0][0]
    assert "No prior records found." in call_args


def test_scene_opening_injects_sentinel_when_no_repository() -> None:
    """When memory_repository is None, sentinel appears in the scene agent input."""
    scene_response = SceneOpeningResponse(text="The forest.", scene_tone="quiet")
    mock_scene_agent = MagicMock()
    mock_scene_agent.run_sync.return_value.output = scene_response

    narrator = NarratorAgent(
        adapter=MagicMock(),
        memory_repository=None,
        _scene_agent=mock_scene_agent,
        _assess_agent=MagicMock(),
        _crit_agent=MagicMock(),
        _plan_agent=MagicMock(),
    )

    narrator.narrate(_make_scene_frame("The docks."))

    call_args = mock_scene_agent.run_sync.call_args[0][0]
    assert "No prior records found." in call_args


def test_plan_next_encounter_includes_prior_narrative_context() -> None:
    """plan_next_encounter pre-fetches memory and injects it into the plan agent input."""
    narrator, mock_memory_repo = _make_narrator_with_memory(
        memory_returns=["Aldric fought the cultist."]
    )
    mock_plan_agent = MagicMock()
    mock_plan_agent.run_sync.return_value.output = NextEncounterPlan(
        seed="The warehouse.", milestone_achieved=False
    )
    narrator._plan_agent = mock_plan_agent

    _milestone = Milestone(
        milestone_id="m1", title="First Blood", description="Survive."
    )
    narrator.plan_next_encounter(
        campaign=_make_campaign_for_narrator(),
        module=_make_module_for_narrator(),
        milestone=_milestone,
        player=_make_player_actor(),
        last_outcome="Cultist subdued.",
    )

    call_args = mock_plan_agent.run_sync.call_args[0][0]
    assert "Aldric fought the cultist." in call_args
