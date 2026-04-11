"""Unit tests for state update helpers."""

from __future__ import annotations

import pytest
from campaignnarrator.domain.models import EncounterPhase, StateEffect
from campaignnarrator.repositories.state_repository import StateRepository
from campaignnarrator.tools.state_updates import apply_state_effects


def test_apply_state_effects_updates_phase_and_public_events() -> None:
    """Structured effects should update encounter phase and public narration."""

    state = StateRepository.from_default_encounter().load_encounter("goblin-camp")

    updated = apply_state_effects(
        state,
        (
            StateEffect("set_phase", "encounter:goblin-camp", EncounterPhase.COMBAT),
            StateEffect(
                "append_public_event",
                "encounter:goblin-camp",
                "Initiative begins.",
            ),
        ),
    )

    assert updated.phase is EncounterPhase.COMBAT
    assert updated.public_events[-1] == "Initiative begins."


def test_change_hp_clamps_to_zero() -> None:
    """Damage effects should not drive hit points below zero."""

    state = StateRepository.from_default_encounter().load_encounter("goblin-camp")

    updated = apply_state_effects(
        state,
        (StateEffect("change_hp", "pc:talia", -99),),
    )

    assert updated.actors["pc:talia"].hp_current == 0


def test_change_hp_clamps_above_hp_max() -> None:
    """Healing effects should not exceed the actor's maximum hit points."""

    state = StateRepository.from_default_encounter().load_encounter("goblin-camp")

    updated = apply_state_effects(
        state,
        (StateEffect("change_hp", "npc:goblin-scout", 99),),
    )

    assert (
        updated.actors["npc:goblin-scout"].hp_current
        == state.actors["npc:goblin-scout"].hp_max
    )


def test_remove_inventory_item_removes_one_matching_item() -> None:
    """Removing an item should only consume a single matching inventory entry."""

    state = StateRepository.from_seed(
        {
            "encounter_id": "goblin-camp",
            "setting": "A ruined roadside camp.",
            "phase": "scene_opening",
            "actors": {
                "pc:talia": {
                    "actor_id": "pc:talia",
                    "name": "Talia",
                    "kind": "pc",
                    "hp_current": 12,
                    "hp_max": 12,
                    "armor_class": 18,
                    "inventory": ["torch", "torch", "rope"],
                    "conditions": [],
                    "is_visible": True,
                }
            },
        }
    ).load_encounter("goblin-camp")

    updated = apply_state_effects(
        state,
        (StateEffect("remove_inventory_item", "pc:talia", "torch"),),
    )

    assert updated.actors["pc:talia"].inventory == ("torch", "rope")


def test_remove_inventory_item_rejects_missing_item() -> None:
    """Missing inventory items should fail with a clear actor-specific error."""

    state = StateRepository.from_default_encounter().load_encounter("goblin-camp")

    with pytest.raises(
        ValueError,
        match=r"actor pc:talia does not have item: lantern",
    ):
        apply_state_effects(
            state,
            (StateEffect("remove_inventory_item", "pc:talia", "lantern"),),
        )


def test_set_encounter_outcome_sets_state_outcome() -> None:
    """Encounter outcome effects should set the canonical outcome field."""

    state = StateRepository.from_default_encounter().load_encounter("goblin-camp")

    updated = apply_state_effects(
        state,
        (StateEffect("set_encounter_outcome", "encounter:goblin-camp", "victory"),),
    )

    assert updated.outcome == "victory"


def test_apply_state_effects_rejects_unknown_actor() -> None:
    """Unknown actors should be rejected with a stable error message."""

    state = StateRepository.from_default_encounter().load_encounter("goblin-camp")

    with pytest.raises(ValueError, match=r"unknown actor: npc:missing"):
        apply_state_effects(state, (StateEffect("change_hp", "npc:missing", -1),))


def test_apply_state_effects_rejects_unknown_effect_type() -> None:
    """Unsupported effect types should fail closed."""

    state = StateRepository.from_default_encounter().load_encounter("goblin-camp")

    with pytest.raises(ValueError, match=r"unsupported state effect: teleport"):
        apply_state_effects(
            state,
            (StateEffect("teleport", "encounter:goblin-camp", "elsewhere"),),
        )


def test_apply_state_effects_rejects_wrong_encounter_target() -> None:
    """Encounter effects should enforce the exact encounter target."""

    state = StateRepository.from_default_encounter().load_encounter("goblin-camp")

    with pytest.raises(
        ValueError,
        match=r"state effect target mismatch: encounter:other-camp",
    ):
        apply_state_effects(
            state,
            (
                StateEffect(
                    "set_phase",
                    "encounter:other-camp",
                    EncounterPhase.COMBAT,
                ),
            ),
        )


def test_apply_state_effects_never_mutates_input_state() -> None:
    """Effect application should return a fresh state and leave input untouched."""

    state = StateRepository.from_default_encounter().load_encounter("goblin-camp")
    original_public_events = state.public_events
    original_hp = state.actors["pc:talia"].hp_current

    updated = apply_state_effects(
        state,
        (
            StateEffect("append_public_event", "encounter:goblin-camp", "Alarm bells!"),
            StateEffect("change_hp", "pc:talia", -3),
        ),
    )

    assert state.public_events == original_public_events
    assert state.actors["pc:talia"].hp_current == original_hp
    assert updated is not state


def test_apply_state_effects_deep_copies_nested_hidden_facts_on_set_phase() -> None:
    """Nested hidden facts should not alias when a phase change is applied."""

    state = StateRepository.from_seed(
        {
            "encounter_id": "goblin-camp",
            "setting": "A ruined roadside camp.",
            "phase": "scene_opening",
            "hidden_facts": {"nested": {"alarms": ["bell"]}},
            "actors": {
                "pc:talia": {
                    "actor_id": "pc:talia",
                    "name": "Talia",
                    "kind": "pc",
                    "hp_current": 12,
                    "hp_max": 12,
                    "armor_class": 18,
                    "inventory": [],
                    "conditions": [],
                    "is_visible": True,
                }
            },
        }
    ).load_encounter("goblin-camp")

    updated = apply_state_effects(
        state,
        (StateEffect("set_phase", "encounter:goblin-camp", EncounterPhase.COMBAT),),
    )

    updated.hidden_facts["nested"]["alarms"].append("horn")

    assert state.hidden_facts["nested"]["alarms"] == ["bell"]
    assert updated.hidden_facts["nested"]["alarms"] == ["bell", "horn"]
    assert updated.phase is EncounterPhase.COMBAT
