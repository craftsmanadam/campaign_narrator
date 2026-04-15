"""Unit tests for the generic campaign narrator domain models."""

from dataclasses import FrozenInstanceError, replace

import pytest
from campaignnarrator.domain import models
from campaignnarrator.domain.models import (
    ActorState,
    ActorType,
    EncounterPhase,
    EncounterState,
    FeatState,
    GameState,
    InitiativeTurn,
    InventoryItem,
    Narration,
    NarrationFrame,
    OrchestrationDecision,
    PlayerInput,
    RecoveryPeriod,
    ResourceState,
    RollRequest,
    RollVisibility,
    RulesAdjudication,
    RulesAdjudicationRequest,
    StateEffect,
    WeaponState,
)

from tests.fixtures.fighter_talia import TALIA
from tests.fixtures.goblin_scout import make_goblin_scout


def test_encounter_state_tracks_public_and_hidden_state() -> None:
    """Encounter state should preserve actor order and public/private data."""

    actors = {
        "pc:talia": ActorState(
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
            action_options=("Attack",),
            ac_breakdown=(),
        ),
        "npc:goblin-scout": ActorState(
            actor_id="npc:goblin-scout",
            name="Goblin Scout",
            actor_type=ActorType.NPC,
            hp_current=5,
            hp_max=5,
            armor_class=13,
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
        actor_type=ActorType.PC,
        hp_current=1,
        hp_max=12,
        armor_class=10,
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
        check_hints=("social_check",),
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
    assert request.check_hints == ("social_check",)
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
                "second_wind",
                current=1,
                max=1,
                recovers_after=RecoveryPeriod.SHORT_REST,
            ),
            ResourceState(
                "savage_attacker",
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
        inventory=(InventoryItem(item="Potion of Healing", count=2),),
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


def test_narration_frame_compendium_context_defaults_to_empty() -> None:
    frame = NarrationFrame(
        purpose="test",
        phase=EncounterPhase.SOCIAL,
        setting="A forest.",
        public_actor_summaries=(),
        visible_npc_summaries=(),
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
        visible_npc_summaries=(),
        recent_public_events=(),
        resolved_outcomes=(),
        allowed_disclosures=("public encounter state",),
        compendium_context=("Rogue class text...",),
    )
    assert frame.compendium_context == ("Rogue class text...",)


def test_actor_type_has_expected_string_values() -> None:
    assert ActorType.PC == "pc"
    assert ActorType.NPC == "npc"
    assert ActorType.ALLY == "ally"


def test_feat_state_is_immutable() -> None:
    feat = FeatState(
        name="Alert",
        effect_summary="Add proficiency bonus to initiative.",
        reference=None,
        per_turn_uses=None,
    )
    with pytest.raises(FrozenInstanceError):
        feat.name = "changed"  # type: ignore[misc]


def test_feat_state_per_turn_uses_none_means_passive() -> None:
    feat = FeatState(
        name="Alert",
        effect_summary="Add proficiency bonus to initiative.",
        reference="DND.SRD.Wiki-0.5.2/Feats.md#Alert",
        per_turn_uses=None,
    )
    assert feat.per_turn_uses is None
    assert feat.reference == "DND.SRD.Wiki-0.5.2/Feats.md#Alert"


def test_feat_state_per_turn_uses_int_tracks_resource() -> None:
    feat = FeatState(
        name="Savage Attacker",
        effect_summary="Once per turn reroll damage dice.",
        reference=None,
        per_turn_uses=1,
    )
    assert feat.per_turn_uses == 1


def test_weapon_state_stores_precomputed_attack_bonus() -> None:
    weapon = WeaponState(
        name="Longsword",
        attack_bonus=7,
        damage_dice="1d8",
        damage_bonus=4,
        damage_type="slashing",
        properties=("versatile (1d10)",),
    )
    assert weapon.attack_bonus == 7  # noqa: PLR2004
    assert weapon.damage_dice == "1d8"
    assert weapon.properties == ("versatile (1d10)",)


def test_initiative_turn_holds_actor_id_and_roll() -> None:
    turn = InitiativeTurn(actor_id="pc:talia", initiative_roll=22)
    assert turn.actor_id == "pc:talia"
    assert turn.initiative_roll == 22  # noqa: PLR2004


def test_initiative_turn_is_immutable() -> None:
    turn = InitiativeTurn(actor_id="pc:talia", initiative_roll=22)
    with pytest.raises(FrozenInstanceError):
        turn.initiative_roll = 99  # type: ignore[misc]


def test_recovery_period_has_expected_string_values() -> None:
    assert RecoveryPeriod.TURN == "turn"
    assert RecoveryPeriod.SHORT_REST == "short_rest"
    assert RecoveryPeriod.LONG_REST == "long_rest"
    assert RecoveryPeriod.DAY == "day"


def test_resource_state_stores_current_max_and_recovery() -> None:
    r = ResourceState(
        resource="second_wind",
        current=1,
        max=1,
        recovers_after=RecoveryPeriod.SHORT_REST,
        reference="character_options/class_features.json#second-wind",
    )
    assert r.resource == "second_wind"
    assert r.current == 1
    assert r.max == 1
    assert r.recovers_after == RecoveryPeriod.SHORT_REST
    assert r.reference == "character_options/class_features.json#second-wind"


def test_resource_state_reference_is_optional() -> None:
    r = ResourceState(
        resource="savage_attacker",
        current=1,
        max=1,
        recovers_after=RecoveryPeriod.TURN,
    )
    assert r.reference is None


def test_resource_state_is_immutable() -> None:
    r = ResourceState(
        resource="action_surge",
        current=1,
        max=1,
        recovers_after=RecoveryPeriod.SHORT_REST,
    )
    with pytest.raises(FrozenInstanceError):
        r.current = 0  # type: ignore[misc]


def test_inventory_item_minimal_construction() -> None:
    item = InventoryItem(item="Potion of Healing", count=2)
    assert item.item == "Potion of Healing"
    assert item.count == 2  # noqa: PLR2004
    assert item.charges is None
    assert item.max_charges is None
    assert item.recovers_after is None
    assert item.reference is None


def test_inventory_item_with_charges() -> None:
    item = InventoryItem(
        item="Wand of Magic Missiles",
        count=1,
        charges=7,
        max_charges=7,
        recovers_after=RecoveryPeriod.DAY,
        reference="magic_items/wands.json#wand-of-magic-missiles",
    )
    assert item.charges == 7  # noqa: PLR2004
    assert item.recovers_after == RecoveryPeriod.DAY


def test_inventory_item_is_immutable() -> None:
    item = InventoryItem(item="Torch", count=5)
    with pytest.raises(FrozenInstanceError):
        item.count = 4  # type: ignore[misc]


def test_encounter_state_combat_turns_preserves_initiative_order() -> None:
    turns = (
        InitiativeTurn(actor_id="pc:talia", initiative_roll=22),
        InitiativeTurn(actor_id="npc:goblin-1", initiative_roll=14),
    )
    state = EncounterState(
        encounter_id="test-combat",
        phase=EncounterPhase.COMBAT,
        setting="Forest",
        actors={},
        combat_turns=turns,
    )
    assert state.combat_turns[0].actor_id == "pc:talia"
    assert state.combat_turns[1].initiative_roll == 14  # noqa: PLR2004


def test_encounter_state_combat_turns_defaults_to_empty() -> None:
    state = EncounterState(
        encounter_id="test",
        phase=EncounterPhase.SOCIAL,
        setting="Forest",
        actors={},
    )
    assert state.combat_turns == ()


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


def test_game_state_holds_player_with_no_encounter() -> None:
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
    game_state = GameState(player=actor)
    assert game_state.encounter is None
    assert game_state.player is actor


def test_game_state_is_frozen() -> None:
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
    game_state = GameState(player=actor)
    with pytest.raises(FrozenInstanceError):
        game_state.encounter = None  # type: ignore[misc]


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
