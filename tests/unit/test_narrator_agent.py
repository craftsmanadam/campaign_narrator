"""Unit tests for the narrator agent."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from campaignnarrator.agents.narrator_agent import NarratorAgent
from campaignnarrator.domain.models import (
    EncounterPhase,
    NarrationFrame,
    SceneOpeningResponse,
)


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
    )
    assert "Gothic style." in narrator._scene_instructions
    assert "opening a new encounter scene" in narrator._scene_instructions
