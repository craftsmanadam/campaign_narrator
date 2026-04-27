"""Unit tests for narration domain models."""

from __future__ import annotations

import pytest
from campaignnarrator.domain.models import (
    EncounterPhase,
    Narration,
    NarrationFrame,
    NarrationResponse,
    NpcPresence,
    NpcPresenceStatus,
)
from pydantic import ValidationError


def test_narration_frame_contains_resolved_public_context() -> None:
    """Narration frames should capture only the public-facing outcome summary."""

    frame = NarrationFrame(
        purpose="status_response",
        phase=EncounterPhase.RULES_RESOLUTION,
        setting="Goblin camp outskirts",
        public_actor_summaries=("Talia stands before the scout.",),
        recent_public_events=("The scout lowers his spear.",),
        resolved_outcomes=("Encounter de-escalated.",),
        allowed_disclosures=("The scout's alarm system remains hidden.",),
    )

    assert frame.purpose == "status_response"
    assert frame.phase is EncounterPhase.RULES_RESOLUTION
    assert frame.setting == "Goblin camp outskirts"
    assert frame.public_actor_summaries == ("Talia stands before the scout.",)
    assert frame.recent_public_events == ("The scout lowers his spear.",)
    assert frame.resolved_outcomes == ("Encounter de-escalated.",)
    assert frame.allowed_disclosures == ("The scout's alarm system remains hidden.",)


def test_narration_stores_text_and_audience() -> None:
    """Narration should preserve the spoken text and intended audience."""

    narration = Narration(text="Talia speaks calmly.", audience="player")

    assert narration.text == "Talia speaks calmly."
    assert narration.audience == "player"


def test_narration_frame_compendium_context_defaults_to_empty() -> None:
    frame = NarrationFrame(
        purpose="test",
        phase=EncounterPhase.SOCIAL,
        setting="A forest.",
        public_actor_summaries=(),
        recent_public_events=(),
        resolved_outcomes=(),
        allowed_disclosures=("public encounter state",),
    )
    assert frame.compendium_context == ()


def test_narration_frame_accepts_compendium_context() -> None:
    frame = NarrationFrame(
        purpose="test",
        phase=EncounterPhase.SOCIAL,
        setting="A forest.",
        public_actor_summaries=(),
        recent_public_events=(),
        resolved_outcomes=(),
        allowed_disclosures=("public encounter state",),
        compendium_context=("Rogue class text...",),
    )
    assert frame.compendium_context == ("Rogue class text...",)


def test_narration_frame_has_npc_presences_not_visible_summaries() -> None:
    presence = NpcPresence(
        actor_id="npc:innkeeper-001",
        display_name="Mira",
        description="the innkeeper",
        name_known=False,
        status=NpcPresenceStatus.PRESENT,
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
    assert len(frame.npc_presences) == 1
    assert frame.npc_presences[0].display_name == "Mira"
    assert not hasattr(frame, "visible_npc_summaries")


def test_narration_defaults_scene_tone_to_none() -> None:
    n = Narration(text="hello")
    assert n.scene_tone is None


def test_narration_accepts_scene_tone() -> None:
    n = Narration(text="hello", scene_tone="warm and welcoming")
    assert n.scene_tone == "warm and welcoming"


def test_narration_response_defaults_encounter_complete_to_false() -> None:
    response = NarrationResponse(
        text="You step into the grove.", current_location="the grove"
    )
    assert response.encounter_complete is False
    assert response.completion_reason is None
    assert response.next_location_hint is None


def test_narration_response_accepts_all_completion_fields() -> None:
    response = NarrationResponse(
        text="You leave the grove.",
        current_location="the road north",
        encounter_complete=True,
        completion_reason="Player departed to a new location.",
        next_location_hint="Cave of Whispers",
    )
    assert response.encounter_complete is True
    assert response.completion_reason == "Player departed to a new location."
    assert response.next_location_hint == "Cave of Whispers"


def test_narration_response_validator_rejects_complete_without_hint() -> None:
    with pytest.raises(ValidationError):
        NarrationResponse(
            text="You leave.",
            current_location="the road",
            encounter_complete=True,
            completion_reason="Player departed.",
            next_location_hint=None,
        )


def test_narration_response_validator_rejects_complete_without_reason() -> None:
    with pytest.raises(ValidationError):
        NarrationResponse(
            text="You leave.",
            current_location="the road",
            encounter_complete=True,
            completion_reason=None,
            next_location_hint="Cave of Whispers",
        )


def test_narration_defaults_encounter_complete_to_false() -> None:
    narration = Narration(text="The grove is quiet.")
    assert narration.encounter_complete is False
    assert narration.completion_reason is None
    assert narration.next_location_hint is None


def test_narration_accepts_encounter_complete_fields() -> None:
    narration = Narration(
        text="You head toward the cave.",
        encounter_complete=True,
        completion_reason="Player departed.",
        next_location_hint="Cave of Whispers",
    )
    assert narration.encounter_complete is True
    assert narration.completion_reason == "Player departed."
    assert narration.next_location_hint == "Cave of Whispers"


def test_scene_opening_response_stores_text_and_tone() -> None:
    from campaignnarrator.domain.models import SceneOpeningResponse

    r = SceneOpeningResponse(text="The ruins loom.", scene_tone="eerie and quiet")
    assert r.text == "The ruins loom."
    assert r.scene_tone == "eerie and quiet"
