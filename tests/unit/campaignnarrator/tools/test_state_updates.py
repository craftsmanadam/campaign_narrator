"""Unit tests for state update helpers."""

from __future__ import annotations

import logging
from dataclasses import replace

import pytest
from campaignnarrator.domain.models import (
    ActorRegistry,
    ActorState,
    ActorType,
    EncounterPhase,
    EncounterState,
    InventoryItem,
    NpcPresence,
    NpcPresenceStatus,
    StateEffect,
)
from campaignnarrator.tools.state_updates import apply_state_effects, require_int


def _make_talia() -> ActorState:
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
        action_options=(),
        ac_breakdown=(),
    )


def _make_goblin() -> ActorState:
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
        action_options=(),
        ac_breakdown=(),
    )


def _default_encounter(
    hidden_facts: dict[str, object] | None = None,
) -> tuple[EncounterState, ActorRegistry]:
    talia = _make_talia()
    goblin = _make_goblin()
    state = EncounterState(
        encounter_id="goblin-camp",
        phase=EncounterPhase.SCENE_OPENING,
        setting="A ruined roadside camp.",
        actor_ids=("pc:talia", "npc:goblin-scout"),
        player_actor_id="pc:talia",
        hidden_facts=hidden_facts or {},
    )
    registry = ActorRegistry(actors={"pc:talia": talia, "npc:goblin-scout": goblin})
    return state, registry


def _state_with_inventory(
    *items: InventoryItem,
) -> tuple[EncounterState, ActorRegistry]:
    actor = ActorState(
        actor_id="pc:talia",
        name="Talia",
        actor_type=ActorType.PC,
        hp_current=44,
        hp_max=44,
        armor_class=20,
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
        action_options=(),
        ac_breakdown=(),
        inventory=items,
    )
    state = EncounterState(
        encounter_id="test-inv",
        phase=EncounterPhase.COMBAT,
        setting="Forest",
        actor_ids=("pc:talia",),
        player_actor_id="pc:talia",
    )
    registry = ActorRegistry(actors={"pc:talia": actor})
    return state, registry


def test_apply_state_effects_updates_phase_and_public_events() -> None:
    """Structured effects should update encounter phase and public narration."""
    state, registry = _default_encounter()

    updated, _registry = apply_state_effects(
        state,
        registry,
        (
            StateEffect(
                effect_type="set_phase",
                target="encounter:goblin-camp",
                value=EncounterPhase.COMBAT,
            ),
            StateEffect(
                effect_type="append_public_event",
                target="encounter:goblin-camp",
                value="Initiative begins.",
            ),
        ),
    )

    assert updated.phase is EncounterPhase.COMBAT
    assert updated.public_events[-1] == "Initiative begins."


def test_change_hp_clamps_to_zero() -> None:
    """Damage effects should not drive hit points below zero."""
    state, registry = _default_encounter()

    _updated_state, updated_registry = apply_state_effects(
        state,
        registry,
        (StateEffect(effect_type="change_hp", target="pc:talia", value=-99),),
    )

    assert updated_registry.actors["pc:talia"].hp_current == 0


def test_change_hp_clamps_above_hp_max() -> None:
    """Healing effects should not exceed the actor's maximum hit points."""
    state, registry = _default_encounter()

    _updated_state, updated_registry = apply_state_effects(
        state,
        registry,
        (StateEffect(effect_type="change_hp", target="npc:goblin-scout", value=99),),
    )

    assert (
        updated_registry.actors["npc:goblin-scout"].hp_current
        == registry.actors["npc:goblin-scout"].hp_max
    )


def test_set_encounter_outcome_sets_state_outcome() -> None:
    """Encounter outcome effects should set the canonical outcome field."""
    state, registry = _default_encounter()

    updated, _registry = apply_state_effects(
        state,
        registry,
        (
            StateEffect(
                effect_type="set_encounter_outcome",
                target="encounter:goblin-camp",
                value="victory",
            ),
        ),
    )

    assert updated.outcome == "victory"


def test_apply_state_effects_rejects_unknown_actor() -> None:
    """Unknown actors should be rejected with a stable error message."""
    state, registry = _default_encounter()

    with pytest.raises(ValueError, match=r"unknown actor: npc:missing"):
        apply_state_effects(
            state,
            registry,
            (StateEffect(effect_type="change_hp", target="npc:missing", value=-1),),
        )


def test_apply_state_effects_skips_unknown_effect_type(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unknown effect types must be skipped with a warning, not crash."""
    state, registry = _default_encounter()
    with caplog.at_level(logging.WARNING, logger="campaignnarrator"):
        result, _registry = apply_state_effects(
            state,
            registry,
            (
                StateEffect(
                    effect_type="state_change",
                    target="encounter:goblin-camp",
                    value="some_value",
                ),
            ),
        )
    assert result == state
    assert any("state_change" in msg for msg in caplog.messages)


def test_apply_state_effects_skips_unknown_and_applies_known(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When a batch has both unknown and known effects, known ones still apply."""
    state, registry = _default_encounter()
    with caplog.at_level(logging.WARNING, logger="campaignnarrator"):
        result, _registry = apply_state_effects(
            state,
            registry,
            (
                StateEffect(
                    effect_type="state_change",
                    target="encounter:goblin-camp",
                    value="ignored",
                ),
                StateEffect(
                    effect_type="append_public_event",
                    target="encounter:goblin-camp",
                    value="A wolf howls in the distance.",
                ),
            ),
        )
    assert "A wolf howls in the distance." in result.public_events
    assert any("state_change" in msg for msg in caplog.messages)


def test_apply_state_effects_rejects_wrong_encounter_target() -> None:
    """Encounter effects should enforce the exact encounter target."""
    state, registry = _default_encounter()

    with pytest.raises(
        ValueError,
        match=r"state effect target mismatch: encounter:other-camp",
    ):
        apply_state_effects(
            state,
            registry,
            (
                StateEffect(
                    effect_type="set_phase",
                    target="encounter:other-camp",
                    value=EncounterPhase.COMBAT,
                ),
            ),
        )


def test_apply_state_effects_warns_and_applies_malformed_encounter_target(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Malformed targets (not 'encounter:*' format) log a warning and still apply."""
    state, registry = _default_encounter()
    with caplog.at_level(logging.WARNING, logger="campaignnarrator"):
        result, _registry = apply_state_effects(
            state,
            registry,
            (
                StateEffect(
                    effect_type="set_phase",
                    target="combat",
                    value=EncounterPhase.COMBAT,
                ),
            ),
        )
    assert result.phase is EncounterPhase.COMBAT
    assert any("Malformed encounter target" in msg for msg in caplog.messages)


def test_apply_state_effects_never_mutates_input_state() -> None:
    """Effect application should return a fresh state and leave input untouched."""
    state, registry = _default_encounter()
    original_public_events = state.public_events
    original_hp = registry.actors["pc:talia"].hp_current

    updated_state, _updated_registry = apply_state_effects(
        state,
        registry,
        (
            StateEffect(
                effect_type="append_public_event",
                target="encounter:goblin-camp",
                value="Alarm bells!",
            ),
            StateEffect(effect_type="change_hp", target="pc:talia", value=-3),
        ),
    )

    assert state.public_events == original_public_events
    assert registry.actors["pc:talia"].hp_current == original_hp
    assert updated_state is not state


def test_apply_state_effects_deep_copies_nested_hidden_facts_on_set_phase() -> None:
    """Nested hidden facts should not alias when a phase change is applied."""
    state, registry = _default_encounter(hidden_facts={"nested": {"alarms": ["bell"]}})

    updated, _registry = apply_state_effects(
        state,
        registry,
        (
            StateEffect(
                effect_type="set_phase",
                target="encounter:goblin-camp",
                value=EncounterPhase.COMBAT,
            ),
        ),
    )

    updated.hidden_facts["nested"]["alarms"].append("horn")

    assert state.hidden_facts["nested"]["alarms"] == ["bell"]
    assert updated.hidden_facts["nested"]["alarms"] == ["bell", "horn"]
    assert updated.phase is EncounterPhase.COMBAT


def test_scene_tone_preserved_through_append_public_event() -> None:
    """scene_tone must survive an append_public_event state effect."""
    state, registry = _default_encounter()
    state = replace(state, scene_tone="tense and foreboding")
    effect = StateEffect(
        effect_type="append_public_event",
        target="encounter:goblin-camp",
        value="A goblin screams.",
    )

    result, _registry = apply_state_effects(state, registry, (effect,))

    assert result.scene_tone == "tense and foreboding"


def test_scene_tone_preserved_through_set_encounter_outcome() -> None:
    """scene_tone must survive a set_encounter_outcome state effect."""
    state, registry = _default_encounter()
    state = replace(state, scene_tone="warm and inviting")
    effect = StateEffect(
        effect_type="set_encounter_outcome",
        target="encounter:goblin-camp",
        value="peaceful",
    )

    result, _registry = apply_state_effects(state, registry, (effect,))

    assert result.scene_tone == "warm and inviting"


def test_require_int_returns_value_for_valid_integer() -> None:
    """require_int must return the value unchanged when given an integer."""
    valid_hp_delta = 5
    negative_hp_delta = -3
    assert require_int(valid_hp_delta, "hp delta") == valid_hp_delta
    assert require_int(negative_hp_delta, "hp delta") == negative_hp_delta
    assert require_int(0, "movement feet") == 0


def test_require_int_raises_type_error_for_non_integer() -> None:
    """require_int must raise TypeError when given a non-integer value."""
    with pytest.raises(TypeError, match=r"invalid hp delta: 3\.0"):
        require_int(3.0, "hp delta")
    with pytest.raises(TypeError, match=r"invalid movement feet: ten"):
        require_int("ten", "movement feet")


def test_change_hp_via_apply_state_effects_applies_correct_delta() -> None:
    """apply_state_effects with change_hp must apply the integer delta correctly."""
    state, registry = _default_encounter()
    initial_hp = registry.actors["pc:talia"].hp_current

    _updated_state, updated_registry = apply_state_effects(
        state,
        registry,
        (StateEffect(effect_type="change_hp", target="pc:talia", value=-3),),
    )

    assert updated_registry.actors["pc:talia"].hp_current == initial_hp - 3


def test_change_hp_via_apply_state_effects_rejects_non_integer_value() -> None:
    """apply_state_effects with change_hp must raise TypeError for non-integer values."""
    state, registry = _default_encounter()

    with pytest.raises(TypeError, match=r"invalid hp delta"):
        apply_state_effects(
            state,
            registry,
            (StateEffect(effect_type="change_hp", target="pc:talia", value="five"),),
        )


def test_inventory_spent_decrements_count_from_two_to_one() -> None:
    state, registry = _state_with_inventory(
        InventoryItem(item_id="potion-1", item="healing potion", count=2),
    )
    effect = StateEffect(
        effect_type="inventory_spent", target="pc:talia", value="potion-1"
    )
    _updated_state, updated_registry = apply_state_effects(state, registry, (effect,))
    remaining = updated_registry.actors["pc:talia"].inventory
    assert len(remaining) == 1
    assert remaining[0].item == "healing potion"
    assert remaining[0].count == 1


def test_inventory_spent_removes_item_entirely_when_count_was_one() -> None:
    state, registry = _state_with_inventory(
        InventoryItem(item_id="potion-1", item="healing potion", count=1),
        InventoryItem(item_id="rope-1", item="rope", count=1),
    )
    effect = StateEffect(
        effect_type="inventory_spent", target="pc:talia", value="potion-1"
    )
    _updated_state, updated_registry = apply_state_effects(state, registry, (effect,))
    remaining = updated_registry.actors["pc:talia"].inventory
    assert len(remaining) == 1
    assert remaining[0].item == "rope"


def test_inventory_spent_raises_value_error_for_unknown_item() -> None:
    state, registry = _state_with_inventory(
        InventoryItem(item_id="rope-1", item="rope", count=1),
    )
    effect = StateEffect(
        effect_type="inventory_spent", target="pc:talia", value="lantern"
    )
    with pytest.raises(ValueError, match=r"does not have item with item_id: lantern"):
        apply_state_effects(state, registry, (effect,))


def test_add_condition_appends_condition_to_actor() -> None:
    state, registry = _default_encounter()
    effect = StateEffect(effect_type="add_condition", target="pc:talia", value="hidden")
    _updated_state, updated_registry = apply_state_effects(state, registry, (effect,))
    assert "hidden" in updated_registry.actors["pc:talia"].conditions


def test_add_condition_is_idempotent_when_already_present() -> None:
    state, registry = _default_encounter()
    effect = StateEffect(effect_type="add_condition", target="pc:talia", value="hidden")
    once_state, once_registry = apply_state_effects(state, registry, (effect,))
    _twice_state, twice_registry = apply_state_effects(
        once_state, once_registry, (effect,)
    )
    assert twice_registry.actors["pc:talia"].conditions.count("hidden") == 1


def test_remove_condition_removes_existing_condition() -> None:
    state, registry = _default_encounter()
    add = StateEffect(effect_type="add_condition", target="pc:talia", value="hidden")
    state_with_condition, registry_with_condition = apply_state_effects(
        state, registry, (add,)
    )
    remove = StateEffect(
        effect_type="remove_condition", target="pc:talia", value="hidden"
    )
    _updated_state, updated_registry = apply_state_effects(
        state_with_condition, registry_with_condition, (remove,)
    )
    assert "hidden" not in updated_registry.actors["pc:talia"].conditions


def test_remove_condition_is_safe_when_condition_absent() -> None:
    state, registry = _default_encounter()
    effect = StateEffect(
        effect_type="remove_condition", target="pc:talia", value="hidden"
    )
    _updated_state, updated_registry = apply_state_effects(state, registry, (effect,))
    assert (
        updated_registry.actors["pc:talia"].conditions
        == registry.actors["pc:talia"].conditions
    )


def test_set_npc_status_marks_npc_departed() -> None:
    state, registry = _default_encounter()
    presence = NpcPresence(
        actor_id="npc:goblin-scout",
        display_name="Goblin Scout",
        description="the goblin",
        name_known=True,
        status=NpcPresenceStatus.PRESENT,
    )
    state = replace(state, npc_presences=(presence,))
    effect = StateEffect(
        effect_type="set_npc_status",
        target="npc:goblin-scout",
        value="departed",
    )
    result, _registry = apply_state_effects(state, registry, (effect,))
    assert result.npc_presences[0].status is NpcPresenceStatus.DEPARTED


def test_set_npc_status_unknown_actor_is_ignored(
    caplog: pytest.LogCaptureFixture,
) -> None:
    state, registry = _default_encounter()
    effect = StateEffect(
        effect_type="set_npc_status",
        target="npc:nonexistent",
        value="departed",
    )
    with caplog.at_level(logging.WARNING):
        result, _registry = apply_state_effects(state, registry, (effect,))
    assert result == state
    assert "no NpcPresence found" in caplog.text


def test_set_npc_status_invalid_value_raises() -> None:
    state, registry = _default_encounter()
    presence = NpcPresence(
        actor_id="npc:goblin-scout",
        display_name="Goblin Scout",
        description="the goblin",
        name_known=True,
    )
    state = replace(state, npc_presences=(presence,))
    effect = StateEffect(
        effect_type="set_npc_status",
        target="npc:goblin-scout",
        value="gone",
    )
    with pytest.raises(TypeError, match="invalid status"):
        apply_state_effects(state, registry, (effect,))


def test_change_hp_updates_registry() -> None:
    """change_hp must update the actor in the registry."""
    state, registry = _default_encounter()
    initial_hp = registry.actors["pc:talia"].hp_current

    _updated_state, updated_registry = apply_state_effects(
        state,
        registry,
        (StateEffect(effect_type="change_hp", target="pc:talia", value=-3),),
    )

    assert updated_registry.actors["pc:talia"].hp_current == initial_hp - 3


def test_add_condition_updates_registry() -> None:
    """add_condition must reflect the new condition in the registry."""
    state, registry = _default_encounter()

    _updated_state, updated_registry = apply_state_effects(
        state,
        registry,
        (StateEffect(effect_type="add_condition", target="pc:talia", value="hidden"),),
    )

    assert "hidden" in updated_registry.actors["pc:talia"].conditions


def test_remove_condition_updates_registry() -> None:
    """remove_condition must remove the condition from the registry actor."""
    state, registry = _default_encounter()
    add_effect = StateEffect(
        effect_type="add_condition", target="pc:talia", value="hidden"
    )
    state_with_cond, registry_with_cond = apply_state_effects(
        state, registry, (add_effect,)
    )

    remove_effect = StateEffect(
        effect_type="remove_condition", target="pc:talia", value="hidden"
    )
    _updated_state, updated_registry = apply_state_effects(
        state_with_cond, registry_with_cond, (remove_effect,)
    )

    assert "hidden" not in updated_registry.actors["pc:talia"].conditions


def test_inventory_spent_updates_registry() -> None:
    """inventory_spent must remove the item from the registry actor."""
    state, registry = _state_with_inventory(
        InventoryItem(item_id="potion-1", item="healing potion", count=1),
    )
    effect = StateEffect(
        effect_type="inventory_spent", target="pc:talia", value="potion-1"
    )
    _updated_state, updated_registry = apply_state_effects(state, registry, (effect,))

    remaining = updated_registry.actors["pc:talia"].inventory
    assert len(remaining) == 0


def test_encounter_effects_do_not_modify_registry() -> None:
    """set_phase and append_public_event must return the registry object unchanged."""
    state, registry = _default_encounter()

    _updated_state, returned_registry = apply_state_effects(
        state,
        registry,
        (
            StateEffect(
                effect_type="set_phase",
                target="encounter:goblin-camp",
                value=EncounterPhase.COMBAT,
            ),
            StateEffect(
                effect_type="append_public_event",
                target="encounter:goblin-camp",
                value="A goblin shouts.",
            ),
        ),
    )

    assert returned_registry is registry
