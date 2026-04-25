"""Unit tests for the narrator agent."""

from __future__ import annotations

import json
from dataclasses import replace
from unittest.mock import MagicMock

import pytest
from campaignnarrator.adapters.pydantic_ai_adapter import PydanticAIAdapter
from campaignnarrator.agents.narrator_agent import NarratorAgent
from campaignnarrator.agents.prompts import (
    BASE_NARRATE_INSTRUCTIONS,
    SCENE_OPENING_INSTRUCTIONS,
)
from campaignnarrator.domain.models import (
    CampaignState,
    CombatAssessment,
    EncounterPhase,
    EncounterState,
    Milestone,
    ModuleState,
    NarrationFrame,
    NarrationResponse,
    NpcPresence,
    SceneOpeningResponse,
)
from campaignnarrator.repositories.memory_repository import MemoryRepository
from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel


def _make_assess_model(data: dict) -> FunctionModel:
    """FunctionModel that returns a CombatAssessment tool call."""

    def fn(messages, info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[ToolCallPart("final_result", json.dumps(data))])

    return FunctionModel(fn)


def _frame(purpose: str = "social_resolution") -> NarrationFrame:
    return NarrationFrame(
        purpose=purpose,
        phase=EncounterPhase.SOCIAL,
        setting="A ruined roadside camp.",
        public_actor_summaries=("Talia has 12 of 12 hit points.",),
        recent_public_events=("Talia offers peace.",),
        resolved_outcomes=("Encounter outcome: peaceful",),
        allowed_disclosures=("visible_npcs", "public_events"),
    )


def _make_narrator(
    text: str = "The goblins lower their weapons.",
    scene_response: SceneOpeningResponse | None = None,
) -> tuple[NarratorAgent, MagicMock, MagicMock]:
    """Return (narrator, mock_adapter, mock_scene_agent).

    narrator._narrate_agent is a MagicMock configured to return NarrationResponse(text).
    """
    mock_adapter = MagicMock()
    mock_adapter.generate_text.return_value = text

    mock_scene_agent = MagicMock()
    if scene_response is not None:
        mock_scene_agent.run_sync.return_value.output = scene_response

    mock_narrate_agent = MagicMock()
    mock_narrate_agent.run_sync.return_value.output = NarrationResponse(
        text=text, current_location="A ruined roadside camp."
    )

    mock_memory_repo = MagicMock()
    mock_memory_repo.retrieve_relevant.return_value = []
    mock_memory_repo.get_exchange_buffer.return_value = ()

    narrator = NarratorAgent(
        adapter=mock_adapter,
        personality="Test narrator.",
        memory_repository=mock_memory_repo,
        _scene_agent=mock_scene_agent,
        _assess_agent=MagicMock(),
        _narrate_agent=mock_narrate_agent,
    )
    return narrator, mock_adapter, mock_scene_agent


def test_narrator_uses_narrate_agent_for_non_opening_frames() -> None:
    narrator, mock_adapter, _ = _make_narrator("The goblins lower their weapons.")
    result = narrator.narrate(_frame("social_resolution"))
    assert result.text == "The goblins lower their weapons."
    assert result.audience == "player"
    narrator._narrate_agent.run_sync.assert_called_once()
    mock_adapter.generate_text.assert_not_called()


def test_narrator_rejects_empty_text_output() -> None:
    narrator, _, __ = _make_narrator()
    narrator._narrate_agent.run_sync.return_value.output = NarrationResponse(
        text="   ", current_location="somewhere"
    )
    with pytest.raises(ValueError, match="empty narration output"):
        narrator.narrate(_frame())


def test_narrator_prompt_includes_safety_guardrails() -> None:
    assert "Do not invent mechanics" in BASE_NARRATE_INSTRUCTIONS
    assert "Use only provided public and allowed context." in BASE_NARRATE_INSTRUCTIONS


def test_narrator_input_includes_disclosures_and_outcomes() -> None:
    narrator, _, __ = _make_narrator()
    narrator.narrate(_frame("status_response"))
    input_json = narrator._narrate_agent.run_sync.call_args[0][0]
    assert '"allowed_disclosures": [' in input_json
    assert '"resolved_outcomes": [' in input_json


def test_narrator_personality_is_prepended_to_instructions() -> None:
    narrator, _, __ = _make_narrator()
    instructions = narrator._instructions(BASE_NARRATE_INSTRUCTIONS)
    assert instructions.startswith("Test narrator.")


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
    narrator._narrate_agent.run_sync.assert_called_once()
    mock_adapter.generate_text.assert_not_called()


def test_narrate_scene_opening_prepends_personality_to_scene_instructions() -> None:
    mock_scene_agent = MagicMock()
    narrator = NarratorAgent(
        adapter=MagicMock(),
        personality="Gothic style.",
        _scene_agent=mock_scene_agent,
        _assess_agent=MagicMock(),
        _narrate_agent=MagicMock(),
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
        _narrate_agent=MagicMock(),
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
        _narrate_agent=MagicMock(),
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
        _narrate_agent=MagicMock(),
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
        _narrate_agent=MagicMock(),
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
        _narrate_agent=MagicMock(),
    )
    with pytest.raises(ValueError, match="combat_active=False but no outcome"):
        narrator.assess_combat_from_json(
            json.dumps({"actors": [], "recent_events": []})
        )


# ---------------------------------------------------------------------------
# retrieve_memory, summarize_encounter
# ---------------------------------------------------------------------------


def _make_narrator_with_memory(
    memory_returns: list[str] | None = None,
    exchange_buffer: tuple[str, ...] = (),
) -> tuple[NarratorAgent, MagicMock]:
    mock_adapter = MagicMock()
    mock_adapter.generate_text.return_value = "Some narration."
    mock_memory_repo = MagicMock(spec=MemoryRepository)
    mock_memory_repo.retrieve_relevant.return_value = memory_returns or []
    mock_memory_repo.get_exchange_buffer.return_value = exchange_buffer
    narrator = NarratorAgent(
        adapter=mock_adapter,
        personality="Grim narrator.",
        memory_repository=mock_memory_repo,
        _scene_agent=MagicMock(),
        _assess_agent=MagicMock(),
        _narrate_agent=MagicMock(),
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
    narrator, _ = _make_narrator_with_memory(memory_returns=[], exchange_buffer=())
    result = narrator.retrieve_memory("nothing")
    assert result == "No prior records found."


def test_retrieve_memory_includes_exchange_buffer_entries() -> None:
    narrator, _ = _make_narrator_with_memory(
        memory_returns=[],
        exchange_buffer=("I search the room.", "You find a hidden lever."),
    )
    result = narrator.retrieve_memory("room")
    assert "I search the room." in result
    assert "You find a hidden lever." in result


def test_retrieve_memory_combines_lancedb_and_exchange_buffer() -> None:
    narrator, _ = _make_narrator_with_memory(
        memory_returns=["Malachar was seen at the docks."],
        exchange_buffer=("I follow Malachar.", "He disappears into the fog."),
    )
    result = narrator.retrieve_memory("Malachar")
    assert "Malachar was seen at the docks." in result
    assert "I follow Malachar." in result
    assert "He disappears into the fog." in result


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


# --- summarize_encounter_partial tests ---


def _make_in_progress_encounter() -> EncounterState:
    return EncounterState(
        encounter_id="goblin-camp",
        phase=EncounterPhase.SOCIAL,
        setting="A ruined roadside camp.",
        actors={},
        public_events=("The goblin scout eyed you warily.",),
        outcome=None,
    )


def test_summarize_encounter_partial_returns_adapter_text() -> None:
    narrator, _ = _make_narrator_with_memory()
    narrator._adapter.generate_text.return_value = (
        "The player arrived at the camp and spoke cautiously."
    )
    result = narrator.summarize_encounter_partial(_make_in_progress_encounter())
    assert result == "The player arrived at the camp and spoke cautiously."
    narrator._adapter.generate_text.assert_called_once()


def test_summarize_encounter_partial_includes_setting_in_prompt() -> None:
    narrator, _ = _make_narrator_with_memory()
    narrator._adapter.generate_text.return_value = "Notes."
    narrator.summarize_encounter_partial(_make_in_progress_encounter())
    call_kwargs = narrator._adapter.generate_text.call_args[1]
    assert "ruined roadside camp" in call_kwargs["input_text"]


def test_summarize_encounter_partial_marks_outcome_as_in_progress() -> None:
    narrator, _ = _make_narrator_with_memory()
    narrator._adapter.generate_text.return_value = "Notes."
    narrator.summarize_encounter_partial(_make_in_progress_encounter())
    call_kwargs = narrator._adapter.generate_text.call_args[1]
    assert "in_progress" in call_kwargs["input_text"]


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
        recent_public_events=(),
        resolved_outcomes=(),
        allowed_disclosures=(),
    )


def _make_scene_narrator(
    memory_returns: list[str] | None = None,
    mock_repo: MagicMock | None = None,
    exchange_buffer: tuple[str, ...] = (),
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
        mock_repo.get_exchange_buffer.return_value = exchange_buffer

    narrator = NarratorAgent(
        adapter=MagicMock(),
        memory_repository=mock_repo,
        _scene_agent=mock_scene_agent,
        _assess_agent=MagicMock(),
        _narrate_agent=MagicMock(),
    )
    return narrator, mock_repo, mock_scene_agent


def test_scene_opening_retrieves_memory_with_setting_as_query() -> None:
    """Prior to _scene_agent, retrieve_memory must be called with the frame setting."""
    narrator, mock_repo, mock_scene_agent = _make_scene_narrator(
        memory_returns=["Malachar had pale hollow eyes."]
    )
    narrator.narrate(_make_scene_frame("The docks at midnight."))

    mock_repo.retrieve_relevant.assert_called_once_with(
        "The docks at midnight.", limit=5
    )
    call_args = mock_scene_agent.run_sync.call_args[0][0]
    assert "Malachar had pale hollow eyes." in call_args


def test_scene_opening_injects_sentinel_when_no_memory_matches() -> None:
    """When no memory matches, sentinel appears in the scene agent input."""
    narrator, _, mock_scene_agent = _make_scene_narrator(memory_returns=[])
    narrator.narrate(_make_scene_frame("Forest"))

    call_args = mock_scene_agent.run_sync.call_args[0][0]
    assert "No prior records found." in call_args


# ---------------------------------------------------------------------------
# open_scene
# ---------------------------------------------------------------------------


@pytest.fixture
def narrator_with_mock_scene_agent() -> tuple[NarratorAgent, MagicMock]:
    """Return (narrator, mock_scene_agent) for open_scene tests."""
    mock_scene_agent = MagicMock()
    mock_memory_repo = MagicMock()
    mock_memory_repo.retrieve_relevant.return_value = []
    mock_memory_repo.get_exchange_buffer.return_value = ()
    narrator = NarratorAgent(
        adapter=MagicMock(),
        memory_repository=mock_memory_repo,
        _scene_agent=mock_scene_agent,
        _assess_agent=MagicMock(),
        _narrate_agent=MagicMock(),
    )
    return narrator, mock_scene_agent


def test_open_scene_returns_scene_opening_response(
    narrator_with_mock_scene_agent: tuple[NarratorAgent, MagicMock],
) -> None:
    """open_scene() returns SceneOpeningResponse directly (not wrapped in Narration)."""
    narrator, mock_scene_agent = narrator_with_mock_scene_agent
    fake_response = SceneOpeningResponse(
        text="A flickering torch lights the room.",
        scene_tone="tense and foreboding",
    )
    mock_scene_agent.run_sync.return_value.output = fake_response

    frame = NarrationFrame(
        purpose="scene_opening",
        phase=EncounterPhase.SCENE_OPENING,
        setting="A dungeon corridor.",
        public_actor_summaries=(),
        recent_public_events=(),
        resolved_outcomes=(),
        allowed_disclosures=("public encounter state",),
    )
    result = narrator.open_scene(frame)
    assert result.text == "A flickering torch lights the room."
    assert result.scene_tone == "tense and foreboding"


def test_open_scene_raises_on_empty_text(
    narrator_with_mock_scene_agent: tuple[NarratorAgent, MagicMock],
) -> None:
    """open_scene() raises ValueError when narration text is blank."""
    narrator, mock_scene_agent = narrator_with_mock_scene_agent
    mock_scene_agent.run_sync.return_value.output = SceneOpeningResponse(
        text="   ",
        scene_tone="quiet",
    )

    frame = NarrationFrame(
        purpose="scene_opening",
        phase=EncounterPhase.SCENE_OPENING,
        setting="An empty room.",
        public_actor_summaries=(),
        recent_public_events=(),
        resolved_outcomes=(),
        allowed_disclosures=(),
    )
    with pytest.raises(ValueError, match="empty narration output"):
        narrator.open_scene(frame)


# ---------------------------------------------------------------------------
# Hard rules and NPC presence serialization
# ---------------------------------------------------------------------------


def test_base_narrate_instructions_contain_hard_rules() -> None:
    """BASE_NARRATE_INSTRUCTIONS must include all four hard rules."""
    assert "Never expose mechanical stats" in BASE_NARRATE_INSTRUCTIONS
    assert "Do not reset or re-describe the opening scene" in BASE_NARRATE_INSTRUCTIONS
    assert "Do not introduce new named characters" in BASE_NARRATE_INSTRUCTIONS
    assert "name_known is false" in BASE_NARRATE_INSTRUCTIONS


def test_scene_opening_instructions_contain_npc_declaration_guidance() -> None:
    """SCENE_OPENING_INSTRUCTIONS must reference NPC stat source fields."""
    assert "monster_compendium" in SCENE_OPENING_INSTRUCTIONS
    assert "simple_npc" in SCENE_OPENING_INSTRUCTIONS
    assert "public_actor_summaries" in SCENE_OPENING_INSTRUCTIONS


def test_narrate_serializes_npc_presences_in_frame() -> None:
    """NarrationFrame.npc_presences appear as ESTABLISHED NPCs block in LLM context."""
    narrator, _, __ = _make_narrator()

    presence = NpcPresence(
        actor_id="npc:mira-000",
        display_name="Mira",
        description="the innkeeper",
        name_known=False,
        visible=True,
    )
    frame = NarrationFrame(
        purpose="scene_response",
        phase=EncounterPhase.SOCIAL,
        setting="A tavern.",
        public_actor_summaries=("Fighter (uninjured)",),
        npc_presences=(presence,),
        recent_public_events=(),
        resolved_outcomes=(),
        allowed_disclosures=("public encounter state",),
    )
    narrator.narrate(frame)

    input_text = narrator._narrate_agent.run_sync.call_args[0][0]
    assert "ESTABLISHED NPCs" in input_text
    assert "the innkeeper" in input_text


def test_narrate_includes_player_action_in_frame_when_present() -> None:
    """player_action must appear in the LLM input when set on the frame."""
    narrator, _, __ = _make_narrator()

    frame = NarrationFrame(
        purpose="npc_dialogue",
        phase=EncounterPhase.SOCIAL,
        setting="A muddy road.",
        public_actor_summaries=("Fighter (uninjured)",),
        recent_public_events=(),
        resolved_outcomes=(),
        allowed_disclosures=("public encounter state",),
        player_action="What is your name and who is the Baron's Shadow?",
    )
    narrator.narrate(frame)

    input_text = narrator._narrate_agent.run_sync.call_args[0][0]
    assert "player_action" in input_text
    assert "Baron's Shadow" in input_text


def test_narrate_omits_player_action_key_when_none() -> None:
    """player_action must not appear in the LLM input when not set."""
    narrator, _, __ = _make_narrator()

    narrator.narrate(_frame("scene_response"))

    input_text = narrator._narrate_agent.run_sync.call_args[0][0]
    assert "player_action" not in input_text


def test_narrate_scene_opening_skips_retrieve_memory_when_context_pre_populated() -> (
    None
):
    """When prior_narrative_context is pre-populated, retrieve_memory is not called."""
    narrator, mock_repo, mock_scene_agent = _make_scene_narrator(
        memory_returns=["should not appear"]
    )
    frame = replace(
        _make_scene_frame("The docks at midnight."),
        prior_narrative_context="Pre-existing lore about the docks.",
    )
    narrator.narrate(frame)

    mock_repo.retrieve_relevant.assert_not_called()
    call_args = mock_scene_agent.run_sync.call_args[0][0]
    assert "Pre-existing lore about the docks." in call_args


def test_narrate_non_opening_includes_prior_narrative_context_when_set() -> None:
    """Non-scene-opening frames include prior_narrative_context in LLM input when set."""
    narrator, _, __ = _make_narrator("Narration text.")
    frame = replace(
        _frame("social_resolution"),
        prior_narrative_context="Earlier, the party camped near the river.",
    )
    narrator.narrate(frame)

    input_text = narrator._narrate_agent.run_sync.call_args[0][0]
    assert "prior_narrative_context" in input_text
    assert "Earlier, the party camped near the river." in input_text


def test_open_scene_retrieves_memory_and_injects_it() -> None:
    """open_scene() retrieves memory using the frame setting and injects it."""
    narrator, mock_repo, mock_scene_agent = _make_scene_narrator(
        memory_returns=["Malachar had pale hollow eyes."]
    )
    narrator.open_scene(_make_scene_frame("The docks at midnight."))

    mock_repo.retrieve_relevant.assert_called_once_with(
        "The docks at midnight.", limit=5
    )
    call_args = mock_scene_agent.run_sync.call_args[0][0]
    assert "Malachar had pale hollow eyes." in call_args


def test_open_scene_skips_retrieve_memory_when_context_pre_populated() -> None:
    """open_scene() does not call retrieve_memory when prior_narrative_context is set."""
    narrator, mock_repo, mock_scene_agent = _make_scene_narrator(
        memory_returns=["should not appear"]
    )
    frame = replace(
        _make_scene_frame("The docks at midnight."),
        prior_narrative_context="Pre-loaded context from the caller.",
    )
    narrator.open_scene(frame)

    mock_repo.retrieve_relevant.assert_not_called()
    call_args = mock_scene_agent.run_sync.call_args[0][0]
    assert "Pre-loaded context from the caller." in call_args
