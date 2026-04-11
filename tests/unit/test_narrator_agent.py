"""Unit tests for the narrator agent."""

from __future__ import annotations

import pytest
from campaignnarrator.agents.narrator_agent import NarratorAgent
from campaignnarrator.domain.models import EncounterPhase, Narration, NarrationFrame


class _FakeAdapter:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[dict[str, object]] = []

    def generate_text(self, *, instructions: str, input_text: str) -> str:
        self.calls.append({"instructions": instructions, "input_text": input_text})
        return self.text


def test_narrator_uses_generic_narration_frame() -> None:
    """Narration should be rendered from the generic frame context."""

    adapter = _FakeAdapter("The goblins lower their weapons.")
    narrator = NarratorAgent(adapter=adapter)

    narration = narrator.narrate(
        NarrationFrame(
            purpose="social_resolution",
            phase=EncounterPhase.SOCIAL,
            setting="A ruined roadside camp.",
            public_actor_summaries=("Talia has 12 of 12 hit points.",),
            visible_npc_summaries=("Goblin Scout is wary.",),
            recent_public_events=("Talia offers peace.",),
            resolved_outcomes=("Encounter outcome: peaceful",),
            allowed_disclosures=("visible_npcs", "public_events"),
        )
    )

    assert narration == Narration(
        text="The goblins lower their weapons.",
        audience="player",
    )
    assert adapter.calls[0]["input_text"] is not None
    assert "social_resolution" in adapter.calls[0]["input_text"]


def test_narrator_rejects_empty_output() -> None:
    """Blank text output should fail closed."""

    adapter = _FakeAdapter("   ")
    narrator = NarratorAgent(adapter=adapter)

    with pytest.raises(ValueError, match="empty narration output"):
        narrator.narrate(
            NarrationFrame(
                purpose="social_resolution",
                phase=EncounterPhase.SOCIAL,
                setting="A ruined roadside camp.",
                public_actor_summaries=("Talia has 12 of 12 hit points.",),
                visible_npc_summaries=("Goblin Scout is wary.",),
                recent_public_events=("Talia offers peace.",),
                resolved_outcomes=("Encounter outcome: peaceful",),
                allowed_disclosures=("visible_npcs", "public_events"),
            )
        )


def test_narrator_prompt_includes_safety_guardrails() -> None:
    """The instructions should constrain the narrator from inventing details."""

    adapter = _FakeAdapter("The goblins lower their weapons.")
    narrator = NarratorAgent(adapter=adapter)

    narrator.narrate(
        NarrationFrame(
            purpose="recap_response",
            phase=EncounterPhase.SOCIAL,
            setting="A ruined roadside camp.",
            public_actor_summaries=("Talia has 12 of 12 hit points.",),
            visible_npc_summaries=("Goblin Scout is wary.",),
            recent_public_events=("Talia offers peace.",),
            resolved_outcomes=("Encounter outcome: peaceful",),
            allowed_disclosures=("visible_npcs", "public_events"),
        )
    )

    instructions = adapter.calls[0]["instructions"]
    assert (
        "Do not invent mechanics, rolls, HP changes, inventory changes, or hidden "
        "facts."
    ) in instructions
    assert "Use only provided public and allowed context." in instructions


def test_narrator_input_includes_disclosures_and_outcomes() -> None:
    """The narrator input should include the full frame context."""

    adapter = _FakeAdapter("The goblins lower their weapons.")
    narrator = NarratorAgent(adapter=adapter)

    narrator.narrate(
        NarrationFrame(
            purpose="status_response",
            phase=EncounterPhase.SOCIAL,
            setting="A ruined roadside camp.",
            public_actor_summaries=("Talia has 12 of 12 hit points.",),
            visible_npc_summaries=("Goblin Scout is wary.",),
            recent_public_events=("Talia offers peace.",),
            resolved_outcomes=("Encounter outcome: peaceful",),
            allowed_disclosures=("visible_npcs", "public_events"),
        )
    )

    input_text = adapter.calls[0]["input_text"]
    assert '"allowed_disclosures": [' in input_text
    assert '"resolved_outcomes": [' in input_text
