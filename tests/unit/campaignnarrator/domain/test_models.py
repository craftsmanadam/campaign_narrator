"""Unit tests for the generic campaign narrator domain models."""

from __future__ import annotations

import dataclasses
import tempfile
from dataclasses import FrozenInstanceError, replace

import pytest
from campaignnarrator.domain import models
from campaignnarrator.domain.models import (
    ActorState,
    ActorType,
    CampaignEvent,
    CampaignState,
    CombatAssessment,
    CombatIntent,
    CombatOutcome,
    CombatResult,
    CombatStatus,
    CritReview,
    EncounterPhase,
    EncounterState,
    FeatState,
    GameState,
    InitiativeTurn,
    InventoryItem,
    Milestone,
    ModuleState,
    Narration,
    NarrationFrame,
    NextEncounterPlan,
    NpcPresence,
    NpcPresenceResult,
    OrchestrationDecision,
    PlayerInput,
    PlayerIO,
    RecoveryPeriod,
    ResourceState,
    RollRequest,
    RollVisibility,
    RulesAdjudication,
    RulesAdjudicationRequest,
    SceneOpeningResponse,
    StateEffect,
    TurnResources,
    WeaponState,
)
from campaignnarrator.repositories.campaign_repository import CampaignRepository
from campaignnarrator.repositories.module_repository import ModuleRepository
from pydantic import ValidationError

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
    assert len(frame.npc_presences) == 1
    assert frame.npc_presences[0].display_name == "Mira"
    assert not hasattr(frame, "visible_npc_summaries")


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
    item = InventoryItem(item_id="potion-1", item="Potion of Healing", count=2)
    assert item.item_id == "potion-1"
    assert item.item == "Potion of Healing"
    assert item.count == 2  # noqa: PLR2004
    assert item.charges is None
    assert item.max_charges is None
    assert item.recovers_after is None
    assert item.reference is None


def test_inventory_item_with_charges() -> None:
    item = InventoryItem(
        item_id="wand-1",
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
    item = InventoryItem(item_id="torch-1", item="Torch", count=5)
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


# ---------------------------------------------------------------------------
# PlayerIO
# ---------------------------------------------------------------------------


def test_player_io_protocol_has_prompt_and_display() -> None:
    assert callable(getattr(PlayerIO, "prompt", None)) or hasattr(
        PlayerIO, "__protocol_attrs__"
    )


# ---------------------------------------------------------------------------
# CombatStatus
# ---------------------------------------------------------------------------


def test_combat_status_has_expected_values() -> None:
    assert CombatStatus.COMPLETE == "complete"
    assert CombatStatus.PLAYER_DOWN_NO_ALLIES == "player_down_no_allies"


# ---------------------------------------------------------------------------
# TurnResources
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# CombatResult
# ---------------------------------------------------------------------------


def test_combat_result_carries_final_state_and_status() -> None:
    actor = ActorState(
        actor_id="pc:talia",
        name="Talia",
        actor_type=ActorType.PC,
        hp_max=44,
        hp_current=44,
        armor_class=20,
        strength=16,
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
    state = EncounterState(
        encounter_id="test",
        phase=EncounterPhase.COMBAT,
        setting="Forest",
        actors={"pc:talia": actor},
    )
    result = CombatResult(
        status=CombatStatus.COMPLETE,
        final_state=state,
        death_saves_remaining=None,
    )
    assert result.status == CombatStatus.COMPLETE
    assert result.death_saves_remaining is None


def test_encounter_state_defaults_scene_tone_to_none() -> None:
    state = EncounterState(
        encounter_id="x",
        phase=EncounterPhase.SOCIAL,
        setting="Forest",
        actors={"pc:talia": TALIA},
    )
    assert state.scene_tone is None


def test_encounter_state_accepts_scene_tone() -> None:
    state = EncounterState(
        encounter_id="x",
        phase=EncounterPhase.SOCIAL,
        setting="Forest",
        actors={"pc:talia": TALIA},
        scene_tone="tense and foreboding",
    )
    assert state.scene_tone == "tense and foreboding"


def test_narration_defaults_scene_tone_to_none() -> None:
    n = Narration(text="hello")
    assert n.scene_tone is None


def test_narration_accepts_scene_tone() -> None:
    n = Narration(text="hello", scene_tone="warm and welcoming")
    assert n.scene_tone == "warm and welcoming"


def test_combat_result_player_down_carries_death_saves() -> None:
    actor = ActorState(
        actor_id="pc:talia",
        name="Talia",
        actor_type=ActorType.PC,
        hp_max=44,
        hp_current=0,
        armor_class=20,
        strength=16,
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
    state = EncounterState(
        encounter_id="test",
        phase=EncounterPhase.COMBAT,
        setting="Forest",
        actors={"pc:talia": actor},
    )
    result = CombatResult(
        status=CombatStatus.PLAYER_DOWN_NO_ALLIES,
        final_state=state,
        death_saves_remaining=2,
    )
    assert result.death_saves_remaining == 2  # noqa: PLR2004


# ---------------------------------------------------------------------------
# BaseModel LLM output model tests
# ---------------------------------------------------------------------------


def test_roll_request_rejects_invalid_dice_expression() -> None:
    with pytest.raises(ValidationError, match="invalid dice expression"):
        RollRequest(owner="player", visibility=RollVisibility.PUBLIC, expression="bad")


def test_roll_request_accepts_valid_dice_expressions() -> None:
    vis = RollVisibility.PUBLIC
    for expr in ("1d20", "2d6+3", "4d6kh3", "1d4-1"):
        req = RollRequest(owner="player", visibility=vis, expression=expr)
        assert req.expression == expr


def test_rules_adjudication_defaults_to_empty_tuples() -> None:
    adj = RulesAdjudication(is_legal=True, action_type="attack", summary="ok")
    assert adj.roll_requests == ()
    assert adj.state_effects == ()
    assert adj.rule_references == ()
    assert adj.reasoning_summary == ""


def test_rules_adjudication_accepts_nested_models() -> None:
    adj = RulesAdjudication(
        is_legal=True,
        action_type="attack",
        summary="ok",
        roll_requests=(
            RollRequest(
                owner="player", visibility=RollVisibility.PUBLIC, expression="1d20"
            ),
        ),
        state_effects=(
            StateEffect(effect_type="damage", target="npc:goblin-1", value=-5),
        ),
        rule_references=("PHB p.192",),
    )
    assert len(adj.roll_requests) == 1
    assert len(adj.state_effects) == 1


def test_combat_intent_accepts_valid_literals() -> None:
    for val in ("end_turn", "query_status", "exit_session", "combat_action"):
        assert CombatIntent(intent=val).intent == val


def test_combat_intent_rejects_invalid_literal() -> None:
    with pytest.raises(ValidationError):
        CombatIntent(intent="fly_away")


def test_scene_opening_response_stores_text_and_tone() -> None:
    r = SceneOpeningResponse(text="The ruins loom.", scene_tone="eerie and quiet")
    assert r.text == "The ruins loom."
    assert r.scene_tone == "eerie and quiet"


def test_orchestration_decision_stores_fields() -> None:
    d = OrchestrationDecision(
        next_step="adjudicate_action",
        next_actor=None,
        requires_rules_resolution=True,
        recommended_check="Persuasion",
        phase_transition=None,
        player_prompt=None,
        reason_summary="Player attempts to reason with the goblins.",
    )
    assert d.next_step == "adjudicate_action"
    assert d.requires_rules_resolution is True


# ---------------------------------------------------------------------------
# CombatOutcome, CombatAssessment, CritReview
# ---------------------------------------------------------------------------


def test_combat_outcome_stores_short_and_full_description() -> None:
    outcome = CombatOutcome(
        short_description="Goblins defeated",
        full_description=(
            "With a final blow, Talia drives the last goblin back into the forest."
        ),
    )
    assert outcome.short_description == "Goblins defeated"
    assert outcome.full_description == (
        "With a final blow, Talia drives the last goblin back into the forest."
    )


def test_combat_assessment_active_has_no_outcome() -> None:
    assessment = CombatAssessment(combat_active=True, outcome=None)
    assert assessment.combat_active is True
    assert assessment.outcome is None


def test_combat_assessment_inactive_has_populated_outcome() -> None:
    outcome = CombatOutcome(
        short_description="Victory",
        full_description="The goblins flee in terror.",
    )
    assessment = CombatAssessment(combat_active=False, outcome=outcome)
    assert assessment.combat_active is False
    assert assessment.outcome is not None
    assert assessment.outcome.short_description == "Victory"


def test_crit_review_defaults_reason_to_none() -> None:
    review = CritReview(approved=True)
    assert review.approved is True
    assert review.reason is None


def test_crit_review_stores_approved_and_reason() -> None:
    review = CritReview(approved=False, reason="Would be anti-climactic here.")
    assert review.approved is False
    assert review.reason == "Would be anti-climactic here."


# ---------------------------------------------------------------------------
# Milestone
# ---------------------------------------------------------------------------


def test_milestone_is_frozen() -> None:
    m = Milestone(milestone_id="m1", title="The Awakening", description="Evil stirs.")
    with pytest.raises(FrozenInstanceError):
        m.milestone_id = "x"  # type: ignore[misc]


def test_milestone_default_not_completed() -> None:
    m = Milestone(milestone_id="m1", title="T", description="D")
    assert m.completed is False


# ---------------------------------------------------------------------------
# CampaignState
# ---------------------------------------------------------------------------


def test_campaign_state_is_frozen() -> None:
    campaign = _make_campaign()
    with pytest.raises(FrozenInstanceError):
        campaign.name = "other"  # type: ignore[misc]


def test_campaign_state_bbeg_actor_id_defaults_none() -> None:
    assert _make_campaign().bbeg_actor_id is None


# ---------------------------------------------------------------------------
# ModuleState
# ---------------------------------------------------------------------------


def test_module_state_is_frozen() -> None:
    mod = _make_module()
    with pytest.raises(FrozenInstanceError):
        mod.module_id = "x"  # type: ignore[misc]


def test_module_state_completed_defaults_false() -> None:
    assert _make_module().completed is False


# ---------------------------------------------------------------------------
# CampaignEvent
# ---------------------------------------------------------------------------


def test_campaign_event_is_frozen() -> None:
    evt = CampaignEvent(
        campaign_id="c1",
        event_type="encounter_completed",
        summary="The goblins were defeated.",
        timestamp="2026-04-18T12:00:00Z",
    )
    with pytest.raises(FrozenInstanceError):
        evt.campaign_id = "x"  # type: ignore[misc]


def test_campaign_event_optional_fields_default_none() -> None:
    evt = CampaignEvent(
        campaign_id="c1",
        event_type="encounter_completed",
        summary="Done.",
        timestamp="2026-04-18T12:00:00Z",
    )
    assert evt.module_id is None
    assert evt.encounter_id is None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_campaign(**overrides: object) -> CampaignState:
    defaults: dict[str, object] = {
        "campaign_id": "c1",
        "name": "The Cursed Coast",
        "setting": "A dark coastal city.",
        "narrator_personality": "Grim and dramatic.",
        "hidden_goal": "Awaken the sea god.",
        "bbeg_name": "Malachar",
        "bbeg_description": "A lich who walks the tides.",
        "milestones": (
            Milestone(
                milestone_id="m1", title="First Blood", description="Enter the city."
            ),
        ),
        "current_milestone_index": 0,
        "starting_level": 1,
        "target_level": 5,
        "player_brief": "I want dark coastal horror.",
        "player_actor_id": "pc:player",
    }
    defaults.update(overrides)
    return CampaignState(**defaults)  # type: ignore[arg-type]


def _make_module(**overrides: object) -> ModuleState:
    defaults: dict[str, object] = {
        "module_id": "module-001",
        "campaign_id": "c1",
        "title": "The Dockside Murders",
        "summary": "Bodies wash ashore nightly.",
        "guiding_milestone_id": "m1",
    }
    defaults.update(overrides)
    return ModuleState(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# ActorState — new character creation fields
# ---------------------------------------------------------------------------


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


def test_game_state_includes_campaign_and_module() -> None:
    campaign = _make_campaign()
    module = _make_module()
    state = GameState(player=TALIA, campaign=campaign, module=module)
    assert state.campaign is campaign
    assert state.module is module
    assert state.encounter is None


# ---------------------------------------------------------------------------
# CampaignState and ModuleState — module tracking fields
# ---------------------------------------------------------------------------


def test_campaign_state_default_module_id_is_none() -> None:
    campaign = _make_campaign()
    assert campaign.current_module_id is None


def test_campaign_state_accepts_module_id() -> None:
    campaign = _make_campaign(current_module_id="module-001")
    assert campaign.current_module_id == "module-001"


def test_campaign_repository_round_trips_current_module_id() -> None:
    campaign = _make_campaign(current_module_id="module-002")
    with tempfile.TemporaryDirectory() as tmp:
        repo = CampaignRepository(tmp)
        repo.save(campaign)
        loaded = repo.load()
    assert loaded is not None
    assert loaded.current_module_id == "module-002"


def test_campaign_repository_round_trips_null_module_id() -> None:
    campaign = _make_campaign()
    with tempfile.TemporaryDirectory() as tmp:
        repo = CampaignRepository(tmp)
        repo.save(campaign)
        loaded = repo.load()
    assert loaded is not None
    assert loaded.current_module_id is None


def test_module_state_default_log_fields_are_empty() -> None:
    module = _make_module()
    assert module.completed_encounter_ids == ()
    assert module.completed_encounter_summaries == ()
    assert module.next_encounter_seed is None


def test_module_state_accepts_completed_encounters() -> None:
    module = _make_module(
        completed_encounter_ids=("module-001-enc-001",),
        completed_encounter_summaries=("The player fought a goblin at the docks.",),
        next_encounter_seed="A shadowy figure waits near the warehouse.",
    )
    assert len(module.completed_encounter_ids) == 1
    assert module.next_encounter_seed == "A shadowy figure waits near the warehouse."


def test_module_state_has_no_encounters_field() -> None:
    field_names = {f.name for f in dataclasses.fields(ModuleState)}
    assert "encounters" not in field_names
    assert "current_encounter_index" not in field_names


def test_module_repository_round_trips_new_fields() -> None:
    module = _make_module(
        completed_encounter_ids=("module-001-enc-001",),
        completed_encounter_summaries=("The goblin fell at the docks.",),
        next_encounter_seed="Shadows move near the warehouse.",
        completed=False,
    )
    with tempfile.TemporaryDirectory() as tmp:
        repo = ModuleRepository(tmp)
        repo.save(module)
        loaded = repo.load("module-001")
    assert loaded is not None
    assert loaded.completed_encounter_ids == ("module-001-enc-001",)
    assert loaded.completed_encounter_summaries == ("The goblin fell at the docks.",)
    assert loaded.next_encounter_seed == "Shadows move near the warehouse."


def test_module_repository_round_trips_empty_log() -> None:
    module = _make_module()
    with tempfile.TemporaryDirectory() as tmp:
        repo = ModuleRepository(tmp)
        repo.save(module)
        loaded = repo.load("module-001")
    assert loaded is not None
    assert loaded.completed_encounter_ids == ()
    assert loaded.next_encounter_seed is None


def test_next_encounter_plan_fields() -> None:
    plan = NextEncounterPlan(seed="The docks at midnight.", milestone_achieved=False)
    assert plan.seed == "The docks at midnight."
    assert plan.milestone_achieved is False


def test_next_encounter_plan_milestone_achieved() -> None:
    plan = NextEncounterPlan(seed="", milestone_achieved=True)
    assert plan.milestone_achieved is True


# ---------------------------------------------------------------------------
# NpcPresence
# ---------------------------------------------------------------------------


def test_npc_presence_stores_fields() -> None:
    presence = NpcPresence(
        actor_id="npc:innkeeper-001",
        display_name="Mira",
        description="the innkeeper",
        name_known=False,
        visible=True,
    )
    assert presence.actor_id == "npc:innkeeper-001"
    assert presence.display_name == "Mira"
    assert presence.description == "the innkeeper"
    assert not presence.name_known
    assert presence.visible


def test_encounter_state_npc_presences_defaults_to_empty() -> None:
    actor = ActorState(
        actor_id="pc:fighter",
        name="Fighter",
        actor_type=ActorType.PC,
        hp_max=12,
        hp_current=12,
        armor_class=16,
        strength=16,
        dexterity=12,
        constitution=14,
        intelligence=10,
        wisdom=10,
        charisma=10,
        proficiency_bonus=2,
        initiative_bonus=1,
        speed=30,
        attacks_per_action=1,
        action_options=("Attack",),
        ac_breakdown=("chain mail",),
    )
    enc = EncounterState(
        encounter_id="enc-001",
        phase=EncounterPhase.SOCIAL,
        setting="A dimly lit tavern.",
        actors={"pc:fighter": actor},
    )
    assert enc.npc_presences == ()


def test_encounter_state_accepts_npc_presences() -> None:
    actor = ActorState(
        actor_id="pc:fighter",
        name="Fighter",
        actor_type=ActorType.PC,
        hp_max=12,
        hp_current=12,
        armor_class=16,
        strength=16,
        dexterity=12,
        constitution=14,
        intelligence=10,
        wisdom=10,
        charisma=10,
        proficiency_bonus=2,
        initiative_bonus=1,
        speed=30,
        attacks_per_action=1,
        action_options=("Attack",),
        ac_breakdown=("chain mail",),
    )
    enc = EncounterState(
        encounter_id="enc-001",
        phase=EncounterPhase.SOCIAL,
        setting="A dimly lit tavern.",
        actors={"pc:fighter": actor},
    )
    presence = NpcPresence(
        actor_id="npc:innkeeper-001",
        display_name="Mira",
        description="the innkeeper",
        name_known=True,
        visible=True,
    )
    enc_with_npc = replace(enc, npc_presences=(presence,))
    assert len(enc_with_npc.npc_presences) == 1
    assert enc_with_npc.npc_presences[0].display_name == "Mira"


# ---------------------------------------------------------------------------
# NpcPresenceResult
# ---------------------------------------------------------------------------


def test_npc_presence_result_stores_fields() -> None:
    result = NpcPresenceResult(
        display_name="Mira",
        description="the innkeeper",
        name_known=True,
        stat_source="simple_npc",
    )
    assert result.display_name == "Mira"
    assert result.monster_name is None


def test_npc_presence_result_with_monster() -> None:
    result = NpcPresenceResult(
        display_name="Grax",
        description="a snarling goblin",
        name_known=False,
        stat_source="monster_compendium",
        monster_name="Goblin",
    )
    assert result.monster_name == "Goblin"


def test_scene_opening_response_introduced_npcs_defaults_empty() -> None:
    response = SceneOpeningResponse(text="The tavern is dimly lit.", scene_tone="tense")
    assert response.introduced_npcs == []


def test_scene_opening_response_accepts_npcs() -> None:
    npc = NpcPresenceResult(
        display_name="Mira",
        description="the innkeeper",
        name_known=False,
        stat_source="simple_npc",
    )
    response = SceneOpeningResponse(
        text="The tavern is dimly lit.",
        scene_tone="tense",
        introduced_npcs=[npc],
    )
    assert len(response.introduced_npcs) == 1
    assert response.introduced_npcs[0].display_name == "Mira"


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


def test_roll_request_accepts_token_placeholder_expression() -> None:
    """RollRequest must accept expressions with {token} placeholders."""
    req = RollRequest(
        owner="pc:talia",
        visibility=RollVisibility.PUBLIC,
        expression="1d20+{wisdom_mod}+{proficiency_bonus}",
    )
    assert req.expression == "1d20+{wisdom_mod}+{proficiency_bonus}"


def test_roll_request_rejects_symbolic_without_braces() -> None:
    """Bare symbolic names without braces must still be rejected."""
    with pytest.raises(ValidationError):
        RollRequest(
            owner="pc:talia",
            visibility=RollVisibility.PUBLIC,
            expression="d20 + wisdom_modifier",
        )
