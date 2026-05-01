"""Unit tests for actor_state domain models."""

from __future__ import annotations

from dataclasses import replace

import pytest
from campaignnarrator.domain.models import (
    ActorState,
    ActorType,
    FeatState,
    InventoryItem,
    RecoveryPeriod,
    ResourceState,
    TurnResources,
)

from tests.fixtures.fighter_talia import TALIA
from tests.fixtures.goblin_scout import make_goblin_scout


def test_actor_type_has_expected_string_values() -> None:
    assert ActorType.PC == "pc"
    assert ActorType.NPC == "npc"
    assert ActorType.ALLY == "ally"


def test_actor_state_minimal_construction() -> None:
    """ActorState requires identity, HP/AC, ability scores, and action economy."""
    actor = ActorState(
        actor_id="pc:test",
        name="Test",
        actor_type=ActorType.PC,
        hp_max=10,
        hp_current=10,
        armor_class=12,
        strength=10,
        dexterity=10,
        constitution=10,
        intelligence=10,
        wisdom=10,
        charisma=10,
        proficiency_bonus=2,
        initiative_bonus=0,
        speed=30,
        attacks_per_action=1,
        action_options=("Attack",),
        ac_breakdown=(),
    )
    assert actor.actor_type == ActorType.PC
    assert actor.conditions == ()
    assert actor.feats == ()
    assert actor.equipped_weapons == ()
    assert actor.damage_resistances == ()
    assert actor.hp_temp == 0
    assert actor.death_save_successes == 0
    assert actor.is_visible is True
    assert actor.personality is None


def test_actor_state_replace_preserves_unchanged_fields() -> None:
    """dataclasses.replace() on a frozen ActorState only changes the named field."""
    actor = ActorState(
        actor_id="pc:talia",
        name="Talia",
        actor_type=ActorType.PC,
        hp_max=44,
        hp_current=44,
        armor_class=20,
        strength=10,
        dexterity=10,
        constitution=10,
        intelligence=10,
        wisdom=10,
        charisma=10,
        proficiency_bonus=2,
        initiative_bonus=0,
        speed=30,
        attacks_per_action=1,
        action_options=("Attack",),
        ac_breakdown=(),
    )
    wounded = replace(actor, hp_current=10)
    assert wounded.hp_current == 10  # noqa: PLR2004
    assert wounded.hp_max == 44  # noqa: PLR2004
    assert wounded.actor_id == "pc:talia"
    assert wounded.actor_type == ActorType.PC


def test_actor_state_resources_are_resource_state_objects() -> None:
    """resources tuple holds ResourceState objects with current/max/recovery data."""
    actor = ActorState(
        actor_id="pc:talia",
        name="Talia",
        actor_type=ActorType.PC,
        hp_max=44,
        hp_current=44,
        armor_class=20,
        strength=10,
        dexterity=10,
        constitution=10,
        intelligence=10,
        wisdom=10,
        charisma=10,
        proficiency_bonus=2,
        initiative_bonus=0,
        speed=30,
        attacks_per_action=1,
        action_options=("Attack",),
        ac_breakdown=(),
        resources=(
            ResourceState(
                resource="second_wind",
                current=1,
                max=1,
                recovers_after=RecoveryPeriod.SHORT_REST,
            ),
            ResourceState(
                resource="savage_attacker",
                current=1,
                max=1,
                recovers_after=RecoveryPeriod.TURN,
            ),
        ),
    )
    assert actor.resources[0].resource == "second_wind"
    assert actor.resources[0].recovers_after == RecoveryPeriod.SHORT_REST
    assert actor.resources[1].resource == "savage_attacker"
    assert actor.resources[1].recovers_after == RecoveryPeriod.TURN


def test_actor_state_inventory_holds_items() -> None:
    """inventory tuple holds InventoryItem objects."""
    actor = ActorState(
        actor_id="pc:talia",
        name="Talia",
        actor_type=ActorType.PC,
        hp_max=44,
        hp_current=44,
        armor_class=20,
        strength=10,
        dexterity=10,
        constitution=10,
        intelligence=10,
        wisdom=10,
        charisma=10,
        proficiency_bonus=2,
        initiative_bonus=0,
        speed=30,
        attacks_per_action=1,
        action_options=("Attack",),
        ac_breakdown=(),
        inventory=(
            InventoryItem(item_id="potion-1", item="Potion of Healing", count=2),
        ),
    )
    assert actor.inventory[0].item == "Potion of Healing"
    assert actor.inventory[0].count == 2  # noqa: PLR2004
    assert actor.inventory[0].charges is None


def test_actor_state_saving_throws_round_trip_via_dict() -> None:
    """saving_throws tuple-of-tuples converts to dict for caller convenience."""
    actor = ActorState(
        actor_id="pc:talia",
        name="Talia",
        actor_type=ActorType.PC,
        hp_max=44,
        hp_current=44,
        armor_class=20,
        strength=10,
        dexterity=10,
        constitution=10,
        intelligence=10,
        wisdom=10,
        charisma=10,
        proficiency_bonus=2,
        initiative_bonus=0,
        speed=30,
        attacks_per_action=1,
        action_options=("Attack",),
        ac_breakdown=(),
        saving_throws=(("strength", 7), ("constitution", 6), ("dexterity", 2)),
    )
    as_dict = dict(actor.saving_throws)
    assert as_dict["strength"] == 7  # noqa: PLR2004
    assert as_dict["constitution"] == 6  # noqa: PLR2004


def test_actor_state_feats_carry_effect_summary() -> None:
    alert = FeatState(
        name="Alert",
        effect_summary="Add proficiency bonus to initiative.",
        reference=None,
        per_turn_uses=None,
    )
    actor = ActorState(
        actor_id="pc:talia",
        name="Talia",
        actor_type=ActorType.PC,
        hp_max=44,
        hp_current=44,
        armor_class=20,
        strength=10,
        dexterity=10,
        constitution=10,
        intelligence=10,
        wisdom=10,
        charisma=10,
        proficiency_bonus=2,
        initiative_bonus=0,
        speed=30,
        attacks_per_action=1,
        action_options=("Attack",),
        ac_breakdown=(),
        feats=(alert,),
    )
    assert actor.feats[0].name == "Alert"
    assert "proficiency" in actor.feats[0].effect_summary


def test_actor_state_npc_carries_personality() -> None:
    actor = ActorState(
        actor_id="npc:goblin-1",
        name="Goblin Scout",
        actor_type=ActorType.NPC,
        hp_max=7,
        hp_current=7,
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
        action_options=("Attack",),
        ac_breakdown=(),
        personality="Cowardly and opportunistic.",
    )
    assert actor.actor_type == ActorType.NPC
    assert actor.personality == "Cowardly and opportunistic."


def test_actor_state_references_defaults_to_empty_tuple() -> None:
    actor = ActorState(
        actor_id="pc:talia",
        name="Talia",
        actor_type=ActorType.PC,
        hp_current=12,
        hp_max=12,
        armor_class=15,
        strength=10,
        dexterity=10,
        constitution=10,
        intelligence=10,
        wisdom=10,
        charisma=10,
        proficiency_bonus=2,
        initiative_bonus=0,
        speed=30,
        attacks_per_action=1,
        action_options=(),
        ac_breakdown=(),
    )
    assert actor.references == ()


def test_actor_state_compendium_text_defaults_to_none() -> None:
    actor = ActorState(
        actor_id="npc:goblin",
        name="Goblin",
        actor_type=ActorType.NPC,
        hp_max=7,
        hp_current=7,
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
        action_options=("Attack",),
        ac_breakdown=("leather armor", "shield"),
    )
    assert actor.compendium_text is None


def test_actor_state_accepts_compendium_text() -> None:
    actor = ActorState(
        actor_id="npc:goblin",
        name="Goblin",
        actor_type=ActorType.NPC,
        hp_max=7,
        hp_current=7,
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
        action_options=("Attack",),
        ac_breakdown=("leather armor", "shield"),
        compendium_text="## Goblin\n*Small humanoid*",
    )
    assert actor.compendium_text == "## Goblin\n*Small humanoid*"


def test_actor_state_new_fields_default_none() -> None:
    """race, description, background are optional and default to None."""
    actor = ActorState(
        actor_id="pc:player",
        name="Aldric",
        actor_type=ActorType.PC,
        hp_max=12,
        hp_current=12,
        armor_class=16,
        strength=17,
        dexterity=14,
        constitution=14,
        intelligence=8,
        wisdom=10,
        charisma=12,
        proficiency_bonus=2,
        initiative_bonus=2,
        speed=30,
        attacks_per_action=1,
        action_options=("Attack", "Dodge", "Dash"),
        ac_breakdown=("Chain Mail: 16",),
    )
    assert actor.race is None
    assert actor.description is None
    assert actor.background is None


def test_actor_state_new_fields_can_be_set() -> None:
    actor = ActorState(
        actor_id="pc:player",
        name="Aldric",
        actor_type=ActorType.PC,
        hp_max=12,
        hp_current=12,
        armor_class=16,
        strength=17,
        dexterity=14,
        constitution=14,
        intelligence=8,
        wisdom=10,
        charisma=12,
        proficiency_bonus=2,
        initiative_bonus=2,
        speed=30,
        attacks_per_action=1,
        action_options=("Attack", "Dodge", "Dash"),
        ac_breakdown=("Chain Mail: 16",),
        race="Human",
        description="Broad-shouldered with a scar across the jaw.",
        background="Served the king's guard for six years.",
    )
    assert actor.race == "Human"
    assert actor.description == "Broad-shouldered with a scar across the jaw."
    assert actor.background == "Served the king's guard for six years."


def test_actor_state_has_level_field() -> None:
    """ActorState must carry a total character level, defaulting to 1."""
    actor = ActorState(
        actor_id="pc:test",
        name="Test",
        actor_type=ActorType.PC,
        hp_max=10,
        hp_current=10,
        armor_class=12,
        strength=10,
        dexterity=10,
        constitution=10,
        intelligence=10,
        wisdom=10,
        charisma=10,
        proficiency_bonus=2,
        initiative_bonus=0,
        speed=30,
        attacks_per_action=1,
        action_options=("Attack",),
        ac_breakdown=(),
    )
    assert actor.level == 1
    assert actor.class_levels == ()
    assert actor.xp == 0


def test_actor_state_class_levels_stores_multiclass() -> None:
    """class_levels must store per-class breakdown as (name, level) tuples."""
    expected_level = 18
    expected_xp = 85000
    actor = ActorState(
        actor_id="pc:multi",
        name="Multi",
        actor_type=ActorType.PC,
        hp_max=20,
        hp_current=20,
        armor_class=14,
        strength=10,
        dexterity=10,
        constitution=10,
        intelligence=10,
        wisdom=10,
        charisma=10,
        proficiency_bonus=4,
        initiative_bonus=0,
        speed=30,
        attacks_per_action=2,
        action_options=("Attack",),
        ac_breakdown=(),
        level=expected_level,
        class_levels=(("Fighter", 9), ("Wizard", 9)),
        xp=expected_xp,
    )
    assert actor.level == expected_level
    assert ("Fighter", 9) in actor.class_levels
    assert ("Wizard", 9) in actor.class_levels
    assert actor.xp == expected_xp


def test_fighter_fixture_initiative_bonus_includes_alert() -> None:
    """Alert adds proficiency bonus (+3 at level 5) to DEX mod (+2) = +5."""
    assert TALIA.initiative_bonus == 5  # noqa: PLR2004


def test_fighter_fixture_attacks_per_action_is_two() -> None:
    """Level 5 Fighter has Extra Attack: 2 attacks per action."""
    assert TALIA.attacks_per_action == 2  # noqa: PLR2004


def test_fighter_fixture_feats_contain_alert_and_savage_attacker() -> None:
    feat_names = {f.name for f in TALIA.feats}
    assert "Alert" in feat_names
    assert "Savage Attacker" in feat_names


def test_fighter_fixture_savage_attacker_is_per_turn_resource() -> None:
    savage = next(f for f in TALIA.feats if f.name == "Savage Attacker")
    assert savage.per_turn_uses == 1


def test_fighter_fixture_alert_is_passive() -> None:
    alert = next(f for f in TALIA.feats if f.name == "Alert")
    assert alert.per_turn_uses is None


def test_fighter_fixture_resources_include_combat_resources() -> None:
    resource_map = {r.resource: r for r in TALIA.resources}
    assert "second_wind" in resource_map
    assert resource_map["second_wind"].recovers_after == RecoveryPeriod.SHORT_REST
    assert "action_surge" in resource_map
    assert resource_map["action_surge"].recovers_after == RecoveryPeriod.SHORT_REST
    assert "savage_attacker" in resource_map
    assert resource_map["savage_attacker"].recovers_after == RecoveryPeriod.TURN


def test_fighter_fixture_inventory_includes_potions() -> None:
    potion = next((i for i in TALIA.inventory if "Healing" in i.item), None)
    assert potion is not None
    assert potion.count == 2  # noqa: PLR2004


def test_fighter_fixture_actor_type_is_pc() -> None:
    assert TALIA.actor_type == ActorType.PC


def test_fighter_fixture_hp_and_ac() -> None:
    assert TALIA.hp_max == 44  # noqa: PLR2004
    assert TALIA.armor_class == 20  # noqa: PLR2004


def test_goblin_fixture_actor_type_is_npc() -> None:
    goblin = make_goblin_scout("npc:goblin-1", "Goblin Scout 1")
    assert goblin.actor_type == ActorType.NPC


def test_goblin_fixture_personality_is_set() -> None:
    goblin = make_goblin_scout("npc:goblin-1", "Goblin Scout 1")
    assert goblin.personality is not None
    assert len(goblin.personality) > 0


def test_goblin_fixture_has_scimitar_and_shortbow() -> None:
    goblin = make_goblin_scout("npc:goblin-1", "Goblin Scout 1")
    weapon_names = {w.name for w in goblin.equipped_weapons}
    assert "Scimitar" in weapon_names
    assert "Shortbow" in weapon_names


def test_goblin_fixture_different_ids_produce_distinct_actors() -> None:
    g1 = make_goblin_scout("npc:goblin-1", "Goblin Scout 1")
    g2 = make_goblin_scout("npc:goblin-2", "Goblin Scout 2")
    assert g1.actor_id != g2.actor_id
    assert g1.name != g2.name
    assert g1.hp_max == g2.hp_max  # same stats, different identity


def test_turn_resources_defaults_to_all_available_no_movement() -> None:
    resources = TurnResources()
    assert resources.action_available is True
    assert resources.bonus_action_available is True
    assert resources.reaction_available is True
    assert resources.movement_remaining == 0


def test_turn_resources_initialized_with_actor_speed() -> None:
    resources = TurnResources(movement_remaining=30)
    assert resources.movement_remaining == 30  # noqa: PLR2004


def test_turn_resources_replace_marks_action_used() -> None:
    resources = TurnResources(movement_remaining=30)
    spent = replace(resources, action_available=False)
    assert spent.action_available is False
    assert spent.movement_remaining == 30  # noqa: PLR2004


def test_actor_state_round_trips_talia_fixture() -> None:
    result = ActorState.from_dict(TALIA.to_dict())
    assert result.actor_id == TALIA.actor_id
    assert result.name == TALIA.name
    assert result.actor_type == TALIA.actor_type
    assert result.hp_max == TALIA.hp_max
    assert result.armor_class == TALIA.armor_class
    assert result.level == TALIA.level
    assert result.class_levels == TALIA.class_levels
    assert result.saving_throws == TALIA.saving_throws
    assert len(result.equipped_weapons) == len(TALIA.equipped_weapons)
    assert result.equipped_weapons[0].name == TALIA.equipped_weapons[0].name
    assert len(result.feats) == len(TALIA.feats)
    assert result.feats[0].name == TALIA.feats[0].name
    assert len(result.resources) == len(TALIA.resources)
    assert result.resources[0].resource == TALIA.resources[0].resource
    assert len(result.inventory) == len(TALIA.inventory)
    assert result.inventory[0].item == TALIA.inventory[0].item


def test_actor_state_to_dict_excludes_transient_fields() -> None:
    actor = replace(TALIA, references=("some/ref.md",), compendium_text="## Stats")
    d = actor.to_dict()
    assert "references" not in d
    assert "compendium_text" not in d


def test_actor_state_from_dict_defaults_optional_fields_when_missing() -> None:
    minimal = {
        "actor_id": "pc:test",
        "name": "Test",
        "actor_type": "pc",
        "hp_max": 10,
        "hp_current": 10,
        "armor_class": 12,
        "strength": 10,
        "dexterity": 10,
        "constitution": 10,
        "intelligence": 10,
        "wisdom": 10,
        "charisma": 10,
        "proficiency_bonus": 2,
        "initiative_bonus": 0,
        "speed": 30,
        "attacks_per_action": 1,
        "action_options": [],
        "ac_breakdown": [],
    }
    actor = ActorState.from_dict(minimal)
    assert actor.level == 1
    assert actor.class_levels == ()
    assert actor.xp == 0
    assert actor.race is None
    assert actor.description is None
    assert actor.background is None
    assert actor.conditions == ()
    assert actor.is_visible is True


def test_has_condition_returns_true_when_present() -> None:
    actor = replace(TALIA, conditions=("hidden", "poisoned"))
    assert actor.has_condition("hidden") is True
    assert actor.has_condition("poisoned") is True


def test_has_condition_returns_false_when_absent() -> None:
    actor = replace(TALIA, conditions=("poisoned",))
    assert actor.has_condition("hidden") is False


def test_has_condition_false_on_empty_conditions() -> None:
    actor = replace(TALIA, conditions=())
    assert actor.has_condition("hidden") is False


def test_with_condition_adds_condition() -> None:
    actor = replace(TALIA, conditions=())
    result = actor.with_condition("hidden")
    assert result.has_condition("hidden") is True
    assert "hidden" in result.conditions


def test_with_condition_is_idempotent() -> None:
    actor = replace(TALIA, conditions=("hidden",))
    result = actor.with_condition("hidden")
    assert result is actor
    assert result.conditions == ("hidden",)


def test_with_condition_preserves_existing_conditions() -> None:
    actor = replace(TALIA, conditions=("poisoned",))
    result = actor.with_condition("hidden")
    assert result.has_condition("poisoned") is True
    assert result.has_condition("hidden") is True


def test_without_condition_removes_condition() -> None:
    actor = replace(TALIA, conditions=("hidden", "poisoned"))
    result = actor.without_condition("hidden")
    assert result.has_condition("hidden") is False
    assert result.has_condition("poisoned") is True


def test_without_condition_is_idempotent() -> None:
    actor = replace(TALIA, conditions=("poisoned",))
    result = actor.without_condition("hidden")
    assert result is actor
    assert result.conditions == ("poisoned",)


def test_without_condition_on_empty_conditions_is_idempotent() -> None:
    actor = replace(TALIA, conditions=())
    result = actor.without_condition("hidden")
    assert result is actor


def test_condition_methods_compose_correctly() -> None:
    actor = replace(TALIA, conditions=())
    actor = actor.with_condition("hidden").with_condition("poisoned")
    assert actor.has_condition("hidden") is True
    assert actor.has_condition("poisoned") is True
    actor = actor.without_condition("hidden")
    assert actor.has_condition("hidden") is False
    assert actor.has_condition("poisoned") is True


def test_actor_state_narrative_summary_uninjured() -> None:
    actor = replace(TALIA, hp_current=TALIA.hp_max)
    assert "uninjured" in actor.narrative_summary()
    assert str(TALIA.hp_max) not in actor.narrative_summary()


def test_actor_state_narrative_summary_pc_includes_player_tag() -> None:
    actor = replace(TALIA, hp_current=TALIA.hp_max)
    summary = actor.narrative_summary()
    assert "player" in summary
    assert TALIA.name in summary


def test_actor_state_narrative_summary_defeated() -> None:
    actor = replace(TALIA, hp_current=0)
    assert "defeated" in actor.narrative_summary()


def test_actor_state_narrative_summary_includes_description() -> None:
    actor = replace(TALIA, description="a tall human fighter", hp_current=TALIA.hp_max)
    summary = actor.narrative_summary()
    assert "a tall human fighter" in summary


def test_actor_state_as_modifiers_basic_values() -> None:
    """as_modifiers returns correct ability mods, proficiency, and level."""
    proficiency = 3
    char_level = 5
    actor = replace(
        TALIA,
        strength=14,
        dexterity=10,
        constitution=12,
        intelligence=8,
        wisdom=16,
        charisma=6,
        proficiency_bonus=proficiency,
        level=char_level,
    )
    result = actor.as_modifiers()
    expected_strength_mod = 2  # (14-10)//2
    expected_dexterity_mod = 0  # (10-10)//2
    expected_constitution_mod = 1  # (12-10)//2
    expected_intelligence_mod = -1  # (8-10)//2
    expected_wisdom_mod = 3  # (16-10)//2
    expected_charisma_mod = -2  # (6-10)//2
    assert result["strength_mod"] == expected_strength_mod
    assert result["dexterity_mod"] == expected_dexterity_mod
    assert result["constitution_mod"] == expected_constitution_mod
    assert result["intelligence_mod"] == expected_intelligence_mod
    assert result["wisdom_mod"] == expected_wisdom_mod
    assert result["charisma_mod"] == expected_charisma_mod
    assert result["proficiency_bonus"] == proficiency
    assert result["level"] == char_level


def test_actor_state_as_modifiers_with_class_levels() -> None:
    """as_modifiers adds per-class-level entries when class_levels is set."""
    class_level = 9
    actor = replace(
        TALIA,
        level=18,
        class_levels=(("Fighter", class_level), ("Wizard", class_level)),
    )
    result = actor.as_modifiers()
    assert result["fighter_level"] == class_level
    assert result["wizard_level"] == class_level
    assert result["proficiency_bonus"] == TALIA.proficiency_bonus


def test_actor_state_as_modifiers_negative_modifier() -> None:
    """Strength 8 produces strength_mod of -1."""
    expected_mod = -1
    actor = replace(TALIA, strength=8)
    result = actor.as_modifiers()
    assert result["strength_mod"] == expected_mod


# --- apply_change_hp ---


def test_apply_change_hp_increases_hp() -> None:
    actor = replace(TALIA, hp_current=20, hp_max=44)
    result = actor.apply_change_hp(10)
    assert result.hp_current == 30  # noqa: PLR2004


def test_apply_change_hp_decreases_hp() -> None:
    actor = replace(TALIA, hp_current=20, hp_max=44)
    result = actor.apply_change_hp(-5)
    assert result.hp_current == 15  # noqa: PLR2004


def test_apply_change_hp_clamps_to_zero() -> None:
    actor = replace(TALIA, hp_current=3, hp_max=44)
    result = actor.apply_change_hp(-100)
    assert result.hp_current == 0


def test_apply_change_hp_clamps_to_hp_max() -> None:
    actor = replace(TALIA, hp_current=40, hp_max=44)
    result = actor.apply_change_hp(100)
    assert result.hp_current == 44  # noqa: PLR2004


def test_apply_change_hp_does_not_mutate_original() -> None:
    actor = replace(TALIA, hp_current=20, hp_max=44)
    _ = actor.apply_change_hp(-5)
    assert actor.hp_current == 20  # noqa: PLR2004


# --- apply_inventory_spent ---


def test_apply_inventory_spent_removes_single_count_item() -> None:
    item = InventoryItem(item_id="torch-1", item="Torch", count=1)
    actor = replace(TALIA, inventory=(item,))
    result = actor.apply_inventory_spent("torch-1")
    assert len(result.inventory) == 0


def test_apply_inventory_spent_decrements_multi_count_item() -> None:
    item = InventoryItem(item_id="arrow-bundle", item="Arrows", count=20)
    actor = replace(TALIA, inventory=(item,))
    result = actor.apply_inventory_spent("arrow-bundle")
    assert len(result.inventory) == 1
    assert result.inventory[0].count == 19  # noqa: PLR2004


def test_apply_inventory_spent_raises_when_item_not_found() -> None:
    actor = replace(TALIA, inventory=())
    with pytest.raises(ValueError, match="item_id: missing-item"):
        actor.apply_inventory_spent("missing-item")


def test_apply_inventory_spent_does_not_mutate_original() -> None:
    item = InventoryItem(item_id="potion-1", item="Healing Potion", count=2)
    actor = replace(TALIA, inventory=(item,))
    _ = actor.apply_inventory_spent("potion-1")
    assert actor.inventory[0].count == 2  # noqa: PLR2004
