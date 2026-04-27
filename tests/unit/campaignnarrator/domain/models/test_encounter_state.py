"""Unit tests for encounter_state domain models."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest
from campaignnarrator.domain.models import (
    ActorState,
    ActorType,
    CampaignState,
    EncounterPhase,
    EncounterReady,
    EncounterState,
    GameState,
    InitiativeTurn,
    Milestone,
    MilestoneAchieved,
    ModuleState,
    NpcPresence,
    NpcPresenceStatus,
)

from tests.fixtures.fighter_talia import TALIA
from tests.fixtures.goblin_scout import make_goblin_scout


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


def _make_campaign_state_for_game_state() -> object:
    return CampaignState(
        campaign_id="c1",
        name="The Cursed Coast",
        setting="A dark coastal city.",
        narrator_personality="Grim and dramatic.",
        hidden_goal="Awaken the sea god.",
        bbeg_name="Malachar",
        bbeg_description="A lich who walks the tides.",
        milestones=(
            Milestone(
                milestone_id="m1", title="First Blood", description="Enter the city."
            ),
        ),
        current_milestone_index=0,
        starting_level=1,
        target_level=5,
        player_brief="I want dark coastal horror.",
        player_actor_id="pc:player",
    )


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


def test_initiative_turn_holds_actor_id_and_roll() -> None:
    turn = InitiativeTurn(actor_id="pc:talia", initiative_roll=22)
    assert turn.actor_id == "pc:talia"
    assert turn.initiative_roll == 22  # noqa: PLR2004


def test_initiative_turn_is_immutable() -> None:
    turn = InitiativeTurn(actor_id="pc:talia", initiative_roll=22)
    with pytest.raises(FrozenInstanceError):
        turn.initiative_roll = 99  # type: ignore[misc]


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
        status=NpcPresenceStatus.PRESENT,
    )
    enc_with_npc = replace(enc, npc_presences=(presence,))
    assert len(enc_with_npc.npc_presences) == 1
    assert enc_with_npc.npc_presences[0].display_name == "Mira"


_EXPECTED_PUBLIC_ACTOR_COUNT = 2


def test_encounter_state_public_actor_summaries_no_presences_includes_all() -> None:
    """When npc_presences is empty, all actors are included (backward compat)."""
    goblin = make_goblin_scout("npc:goblin-scout", "Goblin Scout")
    state = EncounterState(
        encounter_id="test",
        phase=EncounterPhase.SOCIAL,
        setting="A camp.",
        actors={"pc:talia": TALIA, "npc:goblin-scout": goblin},
        npc_presences=(),
    )
    summaries = state.public_actor_summaries()
    assert len(summaries) == _EXPECTED_PUBLIC_ACTOR_COUNT


def test_encounter_state_public_actor_summaries_excludes_departed() -> None:
    """DEPARTED NPCs are excluded from public summaries."""
    goblin = make_goblin_scout("npc:goblin-scout", "Goblin Scout")
    departed = NpcPresence(
        actor_id="npc:goblin-scout",
        display_name="Goblin Scout",
        description="the goblin scout",
        name_known=True,
        status=NpcPresenceStatus.DEPARTED,
    )
    state = EncounterState(
        encounter_id="test",
        phase=EncounterPhase.SOCIAL,
        setting="A camp.",
        actors={"pc:talia": TALIA, "npc:goblin-scout": goblin},
        npc_presences=(departed,),
    )
    summaries = state.public_actor_summaries()
    assert any("Talia" in s for s in summaries)
    assert not any("Goblin" in s for s in summaries)


def test_encounter_state_public_actor_summaries_pc_always_included() -> None:
    """PCs always appear in summaries regardless of npc_presences."""
    state = EncounterState(
        encounter_id="test",
        phase=EncounterPhase.SOCIAL,
        setting="A camp.",
        actors={"pc:talia": TALIA},
        npc_presences=(),
    )
    summaries = state.public_actor_summaries()
    assert any("Talia" in s for s in summaries)


def test_encounter_state_public_actor_summaries_includes_concealed() -> None:
    """CONCEALED NPCs remain in summaries — they are present in the scene."""
    goblin = make_goblin_scout("npc:goblin-scout", "Goblin Scout")
    concealed = NpcPresence(
        actor_id="npc:goblin-scout",
        display_name="Goblin Scout",
        description="the goblin scout",
        name_known=True,
        status=NpcPresenceStatus.CONCEALED,
    )
    state = EncounterState(
        encounter_id="test",
        phase=EncounterPhase.SOCIAL,
        setting="A camp.",
        actors={"pc:talia": TALIA, "npc:goblin-scout": goblin},
        npc_presences=(concealed,),
    )
    summaries = state.public_actor_summaries()
    assert any("Goblin" in s for s in summaries)


def test_game_state_includes_campaign_and_module() -> None:
    campaign = _make_campaign_state_for_game_state()
    module = _make_module()
    state = GameState(player=TALIA, campaign=campaign, module=module)  # type: ignore[arg-type]
    assert state.campaign is campaign
    assert state.module is module
    assert state.encounter is None


def test_encounter_ready_carries_encounter_state_and_module() -> None:
    enc = EncounterState(
        encounter_id="module-001-enc-001",
        phase=EncounterPhase.SOCIAL,
        setting="The docks.",
        actors={},
    )
    mod = _make_module()
    ready = EncounterReady(encounter_state=enc, module=mod)
    assert ready.encounter_state.encounter_id == "module-001-enc-001"
    assert ready.module is mod


def test_encounter_ready_is_frozen() -> None:
    enc = EncounterState(
        encounter_id="x", phase=EncounterPhase.SOCIAL, setting="y", actors={}
    )
    ready = EncounterReady(encounter_state=enc, module=_make_module())
    with pytest.raises(FrozenInstanceError):
        ready.encounter_state = enc  # type: ignore[misc]


def test_milestone_achieved_is_frozen() -> None:
    ma = MilestoneAchieved()
    with pytest.raises(FrozenInstanceError):
        ma.__setattr__("x", 1)  # type: ignore[misc]


def test_initiative_turn_round_trips_to_dict() -> None:
    turn = InitiativeTurn(actor_id="pc:talia", initiative_roll=18)
    assert InitiativeTurn.from_dict(turn.to_dict()) == turn


def test_initiative_turn_from_dict_raises_on_bad_actor_id() -> None:
    with pytest.raises(TypeError):
        InitiativeTurn.from_dict({"actor_id": 123, "initiative_roll": 10})


def test_initiative_turn_from_dict_raises_on_bad_roll() -> None:
    with pytest.raises(TypeError):
        InitiativeTurn.from_dict({"actor_id": "pc:talia", "initiative_roll": "ten"})


def test_encounter_state_round_trips_to_dict() -> None:
    state = EncounterState(
        encounter_id="enc-001",
        phase=EncounterPhase.SOCIAL,
        setting="The Rusty Anchor tavern",
        actors={"pc:talia": TALIA},
        public_events=("Talia entered the tavern.",),
        hidden_facts={"alarm_level": "low"},
        combat_turns=(InitiativeTurn(actor_id="pc:talia", initiative_roll=18),),
        npc_presences=(
            NpcPresence(
                actor_id="npc:innkeeper",
                display_name="Mira",
                description="the innkeeper",
                name_known=True,
                status=NpcPresenceStatus.PRESENT,
            ),
        ),
        outcome=None,
        scene_tone="warm and welcoming",
    )
    result = EncounterState.from_dict(state.to_dict())
    assert result.encounter_id == state.encounter_id
    assert result.phase is state.phase
    assert result.setting == state.setting
    assert result.public_events == state.public_events
    assert result.hidden_facts == dict(state.hidden_facts)
    assert result.combat_turns[0].actor_id == "pc:talia"
    assert (
        result.combat_turns[0].initiative_roll == state.combat_turns[0].initiative_roll
    )
    assert result.npc_presences[0].display_name == "Mira"
    assert result.scene_tone == "warm and welcoming"
    assert result.outcome is None
    assert result.actors["pc:talia"].actor_id == "pc:talia"


def test_public_actor_summaries_excludes_mentioned_npcs() -> None:
    """MENTIONED NPCs must not appear in actor summaries even if they have actor entries."""
    elder = make_goblin_scout("npc:elder", "Elder Rovan")
    state = EncounterState(
        encounter_id="enc-1",
        phase=EncounterPhase.SOCIAL,
        setting="village square",
        actors={"pc:talia": TALIA, "npc:elder": elder},
        npc_presences=(
            NpcPresence(
                actor_id="npc:elder",
                display_name="Elder Rovan",
                description="the village elder",
                name_known=True,
                status=NpcPresenceStatus.MENTIONED,
            ),
        ),
    )
    summaries = state.public_actor_summaries()
    assert not any("Elder" in s for s in summaries)
    assert any("pc:talia" in s or "talia" in s.lower() for s in summaries)


def test_encounter_state_from_dict_round_trips_actor_level_fields() -> None:
    """Fields missing from old encounter serialization (level, class_levels, xp) use defaults."""
    _level = 5
    _xp = 6500
    actor = replace(TALIA, level=_level, class_levels=(("Fighter", _level),), xp=_xp)
    state = EncounterState(
        encounter_id="enc-level",
        phase=EncounterPhase.SOCIAL,
        setting="A camp.",
        actors={"pc:talia": actor},
    )
    result = EncounterState.from_dict(state.to_dict())
    loaded_actor = result.actors["pc:talia"]
    assert loaded_actor.level == _level
    assert loaded_actor.class_levels == (("Fighter", _level),)
    assert loaded_actor.xp == _xp
