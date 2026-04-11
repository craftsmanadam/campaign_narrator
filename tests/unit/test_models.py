"""Unit tests for the generic campaign narrator domain models."""

from campaignnarrator.domain import models
from campaignnarrator.domain.models import (
    ActorState,
    EncounterPhase,
    EncounterState,
    Narration,
    NarrationFrame,
    OrchestrationDecision,
    PlayerInput,
    RollRequest,
    RollVisibility,
    RulesAdjudication,
    RulesAdjudicationRequest,
    StateEffect,
)


def test_encounter_state_tracks_public_and_hidden_state() -> None:
    """Encounter state should preserve actor order and public/private data."""

    actors = {
        "pc:talia": ActorState(
            actor_id="pc:talia",
            name="Talia",
            kind="pc",
            hp_current=12,
            hp_max=12,
            armor_class=15,
        ),
        "npc:goblin-scout": ActorState(
            actor_id="npc:goblin-scout",
            name="Goblin Scout",
            kind="npc",
            hp_current=5,
            hp_max=5,
            armor_class=13,
        ),
    }
    hidden_facts = {"alarm_level": "high"}
    state = EncounterState(
        encounter_id="encounter:goblin-camp",
        phase=EncounterPhase.SOCIAL,
        setting="Goblin camp outskirts",
        actors=actors,
        public_events=("Talia approaches the camp.",),
        hidden_facts=hidden_facts,
    )

    actors["pc:talia"] = ActorState(
        actor_id="pc:talia",
        name="Changed Talia",
        kind="pc",
        hp_current=1,
        hp_max=12,
        armor_class=10,
    )
    hidden_facts["alarm_level"] = "low"

    assert state.player_actor_id == "pc:talia"
    assert state.actors["pc:talia"].name == "Talia"
    assert state.hidden_facts["alarm_level"] == "high"
    assert state.public_events == ("Talia approaches the camp.",)
    assert state.visible_actor_names() == ("Talia", "Goblin Scout")


def test_orchestration_decision_is_structured() -> None:
    """Orchestration decisions should expose the generic control fields."""

    decision = OrchestrationDecision(
        next_step="request_check",
        next_actor="npc:goblin-scout",
        requires_rules_resolution=True,
        recommended_check="persuasion",
        phase_transition="rules_resolution",
        player_prompt="What do you say to the scout?",
        reason_summary="The scout is open to negotiation.",
    )

    assert decision.next_step == "request_check"
    assert decision.next_actor == "npc:goblin-scout"
    assert decision.requires_rules_resolution is True
    assert decision.recommended_check == "persuasion"
    assert decision.phase_transition == "rules_resolution"
    assert decision.player_prompt == "What do you say to the scout?"
    assert decision.reason_summary == "The scout is open to negotiation."


def test_roll_visibility_values_are_public_and_hidden() -> None:
    """Roll visibility enum should expose the expected wire values."""

    assert RollVisibility.PUBLIC.value == "public"
    assert RollVisibility.HIDDEN.value == "hidden"


def test_rules_adjudication_carries_rolls_and_state_effects() -> None:
    """Rules adjudication should include checks, effects, and rule refs."""

    roll_request = RollRequest(
        owner="player",
        visibility=RollVisibility.PUBLIC,
        expression="1d20+2",
        purpose="Persuasion check",
    )
    effect = StateEffect(
        effect_type="set_encounter_outcome",
        target="encounter:goblin-camp",
        value="de-escalated",
    )
    request = RulesAdjudicationRequest(
        actor_id="pc:talia",
        intent="persuade the scout",
        phase=EncounterPhase.SOCIAL,
        allowed_outcomes=("de-escalated", "hostile"),
        rules_context=("social_check",),
        compendium_context=("goblins",),
    )
    adjudication = RulesAdjudication(
        is_legal=True,
        action_type="social_check",
        summary="Talia attempts to talk the scout down.",
        roll_requests=(roll_request,),
        state_effects=(effect,),
        rule_references=("rules/social/persuasion.md",),
        reasoning_summary="A public persuasion roll resolves the scene.",
    )

    assert request.actor_id == "pc:talia"
    assert request.intent == "persuade the scout"
    assert request.phase is EncounterPhase.SOCIAL
    assert request.allowed_outcomes == ("de-escalated", "hostile")
    assert request.rules_context == ("social_check",)
    assert request.compendium_context == ("goblins",)
    assert adjudication.is_legal is True
    assert adjudication.action_type == "social_check"
    assert adjudication.roll_requests == (roll_request,)
    assert adjudication.state_effects == (effect,)
    assert adjudication.rule_references == ("rules/social/persuasion.md",)
    assert adjudication.reasoning_summary == (
        "A public persuasion roll resolves the scene."
    )


def test_narration_frame_contains_resolved_public_context() -> None:
    """Narration frames should capture only the public-facing outcome summary."""

    frame = NarrationFrame(
        purpose="status_response",
        phase=EncounterPhase.RULES_RESOLUTION,
        setting="Goblin camp outskirts",
        public_actor_summaries=("Talia stands before the scout.",),
        visible_npc_summaries=("Goblin Scout is tense but listening.",),
        recent_public_events=("The scout lowers his spear.",),
        resolved_outcomes=("Encounter de-escalated.",),
        allowed_disclosures=("The scout's alarm system remains hidden.",),
    )

    assert frame.purpose == "status_response"
    assert frame.phase is EncounterPhase.RULES_RESOLUTION
    assert frame.setting == "Goblin camp outskirts"
    assert frame.public_actor_summaries == ("Talia stands before the scout.",)
    assert frame.visible_npc_summaries == ("Goblin Scout is tense but listening.",)
    assert frame.recent_public_events == ("The scout lowers his spear.",)
    assert frame.resolved_outcomes == ("Encounter de-escalated.",)
    assert frame.allowed_disclosures == ("The scout's alarm system remains hidden.",)


def test_narration_stores_text_and_audience() -> None:
    """Narration should preserve the spoken text and intended audience."""

    narration = Narration(text="Talia speaks calmly.", audience="player")

    assert narration.text == "Talia speaks calmly."
    assert narration.audience == "player"


def test_player_input_normalizes_text() -> None:
    """Player input should normalize casing and whitespace."""

    player_input = PlayerInput(raw_text="  STATUS  ")

    assert player_input.raw_text == "  STATUS  "
    assert player_input.normalized == "status"


def test_legacy_potion_resolution_models_are_not_exported() -> None:
    """Legacy potion-specific models should not be exported anymore."""

    assert all("potion" not in name.lower() for name in models.__all__)
