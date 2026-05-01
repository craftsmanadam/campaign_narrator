"""Unit tests for encounter_state domain models."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest
from campaignnarrator.domain.models import (
    ActorRegistry,
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
    get_player,
    public_actor_summaries,
    visible_actor_names,
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

    talia_actor = ActorState(
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
    )
    goblin_actor = ActorState(
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
    )
    hidden_facts = {"alarm_level": "high"}
    state = EncounterState(
        encounter_id="encounter:goblin-camp",
        phase=EncounterPhase.SOCIAL,
        setting="Goblin camp outskirts",
        actor_ids=("pc:talia", "npc:goblin-scout"),
        player_actor_id="pc:talia",
        public_events=("Talia approaches the camp.",),
        hidden_facts=hidden_facts,
    )
    registry = ActorRegistry(
        actors={"pc:talia": talia_actor, "npc:goblin-scout": goblin_actor}
    )

    hidden_facts["alarm_level"] = "low"

    assert state.player_actor_id == "pc:talia"
    assert registry.actors["pc:talia"].name == "Talia"
    assert state.hidden_facts["alarm_level"] == "high"
    assert state.public_events == ("Talia approaches the camp.",)
    assert visible_actor_names(state, registry) == ("Talia", "Goblin Scout")


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
        combat_turns=turns,
    )
    assert state.combat_turns[0].actor_id == "pc:talia"
    assert state.combat_turns[1].initiative_roll == 14  # noqa: PLR2004


def test_encounter_state_combat_turns_defaults_to_empty() -> None:
    state = EncounterState(
        encounter_id="test",
        phase=EncounterPhase.SOCIAL,
        setting="Forest",
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
    registry = ActorRegistry().with_actor(actor)
    game_state = GameState(actor_registry=registry)
    assert game_state.encounter is None
    assert actor.actor_id in game_state.actor_registry.actors


def test_game_state_is_frozen() -> None:
    game_state = GameState()
    with pytest.raises(FrozenInstanceError):
        game_state.encounter = None  # type: ignore[misc]


def test_encounter_state_defaults_scene_tone_to_none() -> None:
    state = EncounterState(
        encounter_id="x",
        phase=EncounterPhase.SOCIAL,
        setting="Forest",
        actor_ids=("pc:talia",),
        player_actor_id="pc:talia",
    )
    assert state.scene_tone is None


def test_encounter_state_accepts_scene_tone() -> None:
    state = EncounterState(
        encounter_id="x",
        phase=EncounterPhase.SOCIAL,
        setting="Forest",
        actor_ids=("pc:talia",),
        player_actor_id="pc:talia",
        scene_tone="tense and foreboding",
    )
    assert state.scene_tone == "tense and foreboding"


def test_encounter_state_npc_presences_defaults_to_empty() -> None:
    enc = EncounterState(
        encounter_id="enc-001",
        phase=EncounterPhase.SOCIAL,
        setting="A dimly lit tavern.",
        actor_ids=("pc:fighter",),
        player_actor_id="pc:fighter",
    )
    assert enc.npc_presences == ()


def test_encounter_state_accepts_npc_presences() -> None:
    enc = EncounterState(
        encounter_id="enc-001",
        phase=EncounterPhase.SOCIAL,
        setting="A dimly lit tavern.",
        actor_ids=("pc:fighter",),
        player_actor_id="pc:fighter",
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
        actor_ids=("pc:talia", "npc:goblin-scout"),
        player_actor_id="pc:talia",
        npc_presences=(),
    )
    registry = ActorRegistry(actors={"pc:talia": TALIA, "npc:goblin-scout": goblin})
    summaries = public_actor_summaries(state, registry)
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
        actor_ids=("pc:talia", "npc:goblin-scout"),
        player_actor_id="pc:talia",
        npc_presences=(departed,),
    )
    registry = ActorRegistry(actors={"pc:talia": TALIA, "npc:goblin-scout": goblin})
    summaries = public_actor_summaries(state, registry)
    assert any("Talia" in s for s in summaries)
    assert not any("Goblin" in s for s in summaries)


def test_encounter_state_public_actor_summaries_pc_always_included() -> None:
    """PCs always appear in summaries regardless of npc_presences."""
    state = EncounterState(
        encounter_id="test",
        phase=EncounterPhase.SOCIAL,
        setting="A camp.",
        actor_ids=("pc:talia",),
        player_actor_id="pc:talia",
        npc_presences=(),
    )
    registry = ActorRegistry(actors={"pc:talia": TALIA})
    summaries = public_actor_summaries(state, registry)
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
        actor_ids=("pc:talia", "npc:goblin-scout"),
        player_actor_id="pc:talia",
        npc_presences=(concealed,),
    )
    registry = ActorRegistry(actors={"pc:talia": TALIA, "npc:goblin-scout": goblin})
    summaries = public_actor_summaries(state, registry)
    assert any("Goblin" in s for s in summaries)


def test_game_state_includes_campaign_and_module() -> None:
    campaign = _make_campaign_state_for_game_state()
    module = _make_module()
    state = GameState(campaign=campaign, module=module)  # type: ignore[arg-type]
    assert state.campaign is campaign
    assert state.module is module
    assert state.encounter is None


def test_encounter_ready_carries_encounter_state_and_module() -> None:
    enc = EncounterState(
        encounter_id="module-001-enc-001",
        phase=EncounterPhase.SOCIAL,
        setting="The docks.",
    )
    mod = _make_module()
    ready = EncounterReady(encounter_state=enc, module=mod)
    assert ready.encounter_state.encounter_id == "module-001-enc-001"
    assert ready.module is mod


def test_encounter_ready_is_frozen() -> None:
    enc = EncounterState(encounter_id="x", phase=EncounterPhase.SOCIAL, setting="y")
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
        actor_ids=("pc:talia",),
        player_actor_id="pc:talia",
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
    assert "pc:talia" in result.actor_ids


def test_public_actor_summaries_excludes_mentioned_npcs() -> None:
    """MENTIONED NPCs must not appear in actor summaries even if they have actor entries."""
    elder = make_goblin_scout("npc:elder", "Elder Rovan")
    state = EncounterState(
        encounter_id="enc-1",
        phase=EncounterPhase.SOCIAL,
        setting="village square",
        actor_ids=("pc:talia", "npc:elder"),
        player_actor_id="pc:talia",
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
    registry = ActorRegistry(actors={"pc:talia": TALIA, "npc:elder": elder})
    summaries = public_actor_summaries(state, registry)
    assert not any("Elder" in s for s in summaries)
    assert any("pc:talia" in s or "talia" in s.lower() for s in summaries)


def test_encounter_state_traveling_actor_ids_defaults_to_empty() -> None:
    state = EncounterState(
        encounter_id="enc-001",
        phase=EncounterPhase.SOCIAL,
        setting="A forest clearing.",
        actor_ids=("pc:talia",),
        player_actor_id="pc:talia",
    )
    assert state.traveling_actor_ids == ()


def test_encounter_state_next_location_hint_defaults_to_none() -> None:
    state = EncounterState(
        encounter_id="enc-001",
        phase=EncounterPhase.SOCIAL,
        setting="A forest clearing.",
        actor_ids=("pc:talia",),
        player_actor_id="pc:talia",
    )
    assert state.next_location_hint is None


def test_encounter_state_to_dict_includes_traveling_fields() -> None:
    state = EncounterState(
        encounter_id="enc-001",
        phase=EncounterPhase.SOCIAL,
        setting="A forest clearing.",
        actor_ids=("pc:talia",),
        player_actor_id="pc:talia",
        traveling_actor_ids=("npc:elara",),
        next_location_hint="The cave entrance",
    )
    data = state.to_dict()
    assert data["traveling_actor_ids"] == ["npc:elara"]
    assert data["next_location_hint"] == "The cave entrance"


def test_encounter_state_from_dict_round_trips_traveling_fields() -> None:
    state = EncounterState(
        encounter_id="enc-001",
        phase=EncounterPhase.SOCIAL,
        setting="A forest clearing.",
        actor_ids=("pc:talia",),
        player_actor_id="pc:talia",
        traveling_actor_ids=("npc:elara",),
        next_location_hint="The cave entrance",
    )
    restored = EncounterState.from_dict(state.to_dict())
    assert restored.traveling_actor_ids == ("npc:elara",)
    assert restored.next_location_hint == "The cave entrance"


def test_encounter_state_from_dict_backward_compat_missing_traveling_fields() -> None:
    """Old saves without traveling_actor_ids/next_location_hint load cleanly."""
    data = {
        "encounter_id": "enc-001",
        "phase": "social",
        "setting": "A forest clearing.",
        "actors": {},
    }
    state = EncounterState.from_dict(data)
    assert state.traveling_actor_ids == ()
    assert state.next_location_hint is None


def test_encounter_state_from_dict_round_trips_actor_level_fields() -> None:
    """actor_ids round-trips through to_dict/from_dict cleanly."""
    state = EncounterState(
        encounter_id="enc-level",
        phase=EncounterPhase.SOCIAL,
        setting="A camp.",
        actor_ids=("pc:talia",),
        player_actor_id="pc:talia",
    )
    result = EncounterState.from_dict(state.to_dict())
    assert "pc:talia" in result.actor_ids
    assert result.player_actor_id == "pc:talia"


def test_game_state_actor_registry_defaults_to_empty() -> None:
    state = GameState()
    assert len(state.actor_registry.actors) == 0


def test_game_state_accepts_actor_registry() -> None:
    registry = ActorRegistry().with_actor(TALIA)
    state = GameState(actor_registry=registry)
    assert TALIA.actor_id in state.actor_registry.actors


def test_get_player_returns_actor_from_registry() -> None:
    """get_player looks up the player by actor_id from the registry."""
    registry = ActorRegistry().with_actor(TALIA)
    result = get_player(registry, TALIA.actor_id)
    assert result is TALIA


def test_get_player_raises_runtime_error_when_absent() -> None:
    """get_player raises RuntimeError with a readable message when player not in registry."""
    registry = ActorRegistry()
    with pytest.raises(RuntimeError, match="pc:talia"):
        get_player(registry, "pc:talia")


def test_encounter_state_actor_ids_field() -> None:
    """actor_ids is a stored tuple, not derived from actors dict."""
    state = EncounterState(
        encounter_id="x",
        phase=EncounterPhase.SOCIAL,
        setting="Forest",
        actor_ids=("pc:talia", "npc:goblin-1"),
        player_actor_id="pc:talia",
    )
    assert state.actor_ids == ("pc:talia", "npc:goblin-1")
    assert state.player_actor_id == "pc:talia"


def test_encounter_state_actor_ids_defaults_to_empty() -> None:
    """actor_ids defaults to empty tuple when not provided."""
    state = EncounterState(
        encounter_id="x",
        phase=EncounterPhase.SOCIAL,
        setting="Forest",
    )
    assert state.actor_ids == ()
    assert state.player_actor_id == ""


def test_visible_actor_names_module_level_function() -> None:
    """visible_actor_names() is now a module-level function taking registry."""
    talia = ActorState(
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
    state = EncounterState(
        encounter_id="x",
        phase=EncounterPhase.SOCIAL,
        setting="Forest",
        actor_ids=("pc:talia",),
        player_actor_id="pc:talia",
    )
    registry = ActorRegistry(actors={"pc:talia": talia})
    assert visible_actor_names(state, registry) == ("Talia",)


def test_public_actor_summaries_module_level_function() -> None:
    """public_actor_summaries() is now a module-level function taking registry."""
    talia = ActorState(
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
    state = EncounterState(
        encounter_id="x",
        phase=EncounterPhase.SOCIAL,
        setting="Forest",
        actor_ids=("pc:talia",),
        player_actor_id="pc:talia",
    )
    registry = ActorRegistry(actors={"pc:talia": talia})
    summaries = public_actor_summaries(state, registry)
    assert len(summaries) == 1
    assert "Talia" in summaries[0]


def test_public_actor_summaries_filters_by_npc_presences() -> None:
    """When npc_presences is populated, only PCs and active NPCs are included."""
    talia = ActorState(
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
    goblin = ActorState(
        actor_id="npc:goblin-1",
        name="Goblin",
        actor_type=ActorType.NPC,
        hp_current=7,
        hp_max=7,
        armor_class=13,
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
    departed = ActorState(
        actor_id="npc:departed",
        name="Departed Npc",
        actor_type=ActorType.NPC,
        hp_current=7,
        hp_max=7,
        armor_class=13,
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
    state = EncounterState(
        encounter_id="x",
        phase=EncounterPhase.SOCIAL,
        setting="Forest",
        actor_ids=("pc:talia", "npc:goblin-1", "npc:departed"),
        player_actor_id="pc:talia",
        npc_presences=(
            NpcPresence(
                actor_id="npc:goblin-1",
                display_name="Goblin",
                description="the goblin",
                name_known=True,
                status=NpcPresenceStatus.PRESENT,
            ),
            NpcPresence(
                actor_id="npc:departed",
                display_name="Departed Npc",
                description="the departed npc",
                name_known=True,
                status=NpcPresenceStatus.DEPARTED,
            ),
        ),
    )
    registry = ActorRegistry(
        actors={
            "pc:talia": talia,
            "npc:goblin-1": goblin,
            "npc:departed": departed,
        }
    )
    _expected_present_count = 2  # Talia (PC) + Goblin (PRESENT)
    summaries = public_actor_summaries(state, registry)
    ids_in_summaries = [s for s in summaries if "Departed" in s]
    assert len(ids_in_summaries) == 0
    assert len(summaries) == _expected_present_count


def test_encounter_state_from_dict_backward_compat_actors_dict() -> None:
    """from_dict with old 'actors' key extracts actor_ids and derives player_actor_id."""
    old_data = {
        "encounter_id": "old-enc",
        "phase": "social",
        "setting": "A road.",
        "actors": {
            "pc:talia": {
                "actor_id": "pc:talia",
                "name": "Talia",
                "actor_type": "pc",
                "hp_current": 12,
                "hp_max": 12,
                "armor_class": 15,
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
            },
            "npc:goblin": {
                "actor_id": "npc:goblin",
                "name": "Goblin",
                "actor_type": "npc",
                "hp_current": 5,
                "hp_max": 5,
                "armor_class": 13,
                "strength": 8,
                "dexterity": 14,
                "constitution": 10,
                "intelligence": 10,
                "wisdom": 8,
                "charisma": 8,
                "proficiency_bonus": 2,
                "initiative_bonus": 2,
                "speed": 30,
                "attacks_per_action": 1,
                "action_options": [],
                "ac_breakdown": [],
            },
        },
    }
    state = EncounterState.from_dict(old_data)
    assert "pc:talia" in state.actor_ids
    assert "npc:goblin" in state.actor_ids
    assert state.player_actor_id == "pc:talia"


def test_encounter_state_to_dict_writes_actor_ids_not_actors() -> None:
    """to_dict() writes actor_ids list, not actors dict."""
    state = EncounterState(
        encounter_id="x",
        phase=EncounterPhase.SOCIAL,
        setting="Forest",
        actor_ids=("pc:talia", "npc:goblin-1"),
        player_actor_id="pc:talia",
    )
    d = state.to_dict()
    assert "actor_ids" in d
    assert "actors" not in d
    assert d["actor_ids"] == ["pc:talia", "npc:goblin-1"]
    assert d["player_actor_id"] == "pc:talia"


def _make_enc(**overrides: object) -> EncounterState:
    defaults: dict[str, object] = {
        "encounter_id": "enc-001",
        "phase": EncounterPhase.SOCIAL,
        "setting": "The docks.",
        "actor_ids": ("pc:talia",),
        "player_actor_id": "pc:talia",
    }
    defaults.update(overrides)
    return EncounterState(**defaults)  # type: ignore[arg-type]


# --- EncounterState.append_public_event ---


def test_append_public_event_adds_event() -> None:
    state = _make_enc(public_events=("First event.",))
    result = state.append_public_event("Second event.")
    assert result.public_events == ("First event.", "Second event.")


def test_append_public_event_on_empty_events() -> None:
    state = _make_enc()
    result = state.append_public_event("Something happened.")
    assert result.public_events == ("Something happened.",)


def test_append_public_event_does_not_mutate_original() -> None:
    state = _make_enc(public_events=())
    _ = state.append_public_event("Event.")
    assert state.public_events == ()


# --- EncounterState.with_outcome ---


def test_with_outcome_sets_outcome() -> None:
    state = _make_enc()
    result = state.with_outcome("The player fled.")
    assert result.outcome == "The player fled."


def test_with_outcome_does_not_mutate_original() -> None:
    state = _make_enc()
    _ = state.with_outcome("Done.")
    assert state.outcome is None


# --- EncounterState.with_npc_status ---


def test_with_npc_status_updates_matching_presence() -> None:
    presence = NpcPresence(
        actor_id="npc:mira",
        display_name="Mira",
        description="the innkeeper",
        name_known=True,
        status=NpcPresenceStatus.PRESENT,
    )
    state = _make_enc(npc_presences=(presence,))
    result = state.with_npc_status("npc:mira", NpcPresenceStatus.DEPARTED)
    assert result.npc_presences[0].status == NpcPresenceStatus.DEPARTED


def test_with_npc_status_leaves_other_presences_unchanged() -> None:
    mira = NpcPresence(
        actor_id="npc:mira",
        display_name="Mira",
        description="the innkeeper",
        name_known=True,
        status=NpcPresenceStatus.PRESENT,
    )
    guard = NpcPresence(
        actor_id="npc:guard",
        display_name="Guard",
        description="a city guard",
        name_known=False,
        status=NpcPresenceStatus.PRESENT,
    )
    state = _make_enc(npc_presences=(mira, guard))
    result = state.with_npc_status("npc:mira", NpcPresenceStatus.DEPARTED)
    assert result.npc_presences[0].status == NpcPresenceStatus.DEPARTED
    assert result.npc_presences[1].status == NpcPresenceStatus.PRESENT


def test_with_npc_status_no_op_when_actor_not_found() -> None:
    state = _make_enc(npc_presences=())
    result = state.with_npc_status("npc:nobody", NpcPresenceStatus.DEPARTED)
    assert result.npc_presences == ()


def test_with_npc_status_does_not_mutate_original() -> None:
    presence = NpcPresence(
        actor_id="npc:mira",
        display_name="Mira",
        description="the innkeeper",
        name_known=True,
        status=NpcPresenceStatus.PRESENT,
    )
    state = _make_enc(npc_presences=(presence,))
    _ = state.with_npc_status("npc:mira", NpcPresenceStatus.DEPARTED)
    assert state.npc_presences[0].status == NpcPresenceStatus.PRESENT


# --- EncounterState.with_current_location ---


def test_with_current_location_sets_location() -> None:
    state = _make_enc()
    result = state.with_current_location("The harbour warehouse")
    assert result.current_location == "The harbour warehouse"


def test_with_current_location_does_not_mutate_original() -> None:
    state = _make_enc(setting="The docks.")
    _ = state.with_current_location("Somewhere else")
    assert state.current_location == "The docks."


# --- EncounterState.with_traveling_actor_ids ---


def test_with_traveling_actor_ids_sets_ids() -> None:
    state = _make_enc()
    result = state.with_traveling_actor_ids(("npc:elara", "npc:boris"))
    assert result.traveling_actor_ids == ("npc:elara", "npc:boris")


def test_with_traveling_actor_ids_does_not_mutate_original() -> None:
    state = _make_enc()
    _ = state.with_traveling_actor_ids(("npc:elara",))
    assert state.traveling_actor_ids == ()


# --- EncounterState.with_next_location_hint ---


def test_with_next_location_hint_sets_hint() -> None:
    state = _make_enc()
    result = state.with_next_location_hint("The ruined keep to the north")
    assert result.next_location_hint == "The ruined keep to the north"


def test_with_next_location_hint_accepts_none() -> None:
    state = _make_enc(next_location_hint="Old hint")
    result = state.with_next_location_hint(None)
    assert result.next_location_hint is None


def test_with_next_location_hint_does_not_mutate_original() -> None:
    state = _make_enc()
    _ = state.with_next_location_hint("Somewhere")
    assert state.next_location_hint is None
