"""Unit tests for ActorRegistry and EncounterTransition models."""

from __future__ import annotations

from dataclasses import replace
from types import MappingProxyType

import pytest
from campaignnarrator.domain.models import (
    ActorRegistry,
    EncounterTransition,
    NpcPresence,
    NpcPresenceStatus,
)

from tests.fixtures.fighter_talia import TALIA
from tests.fixtures.goblin_scout import make_goblin_scout

_GOBLIN = make_goblin_scout("npc:goblin", "Goblin Scout")


def test_actor_registry_starts_empty() -> None:
    assert len(ActorRegistry().actors) == 0


def test_actor_registry_with_actor_adds_actor() -> None:
    registry = ActorRegistry().with_actor(TALIA)
    assert TALIA.actor_id in registry.actors
    assert registry.actors[TALIA.actor_id].name == TALIA.name


def test_actor_registry_with_actor_is_immutable_original_unchanged() -> None:
    original = ActorRegistry()
    original.with_actor(TALIA)
    assert TALIA.actor_id not in original.actors


def test_actor_registry_with_actors_merges() -> None:
    registry = ActorRegistry().with_actor(TALIA)
    updated = registry.with_actors({_GOBLIN.actor_id: _GOBLIN})
    assert TALIA.actor_id in updated.actors
    assert _GOBLIN.actor_id in updated.actors


def test_actor_registry_with_actors_later_entries_win() -> None:
    registry = ActorRegistry(actors={TALIA.actor_id: TALIA})
    wounded = replace(TALIA, hp_current=1)
    overwritten = registry.with_actors({TALIA.actor_id: wounded})
    assert overwritten.actors[TALIA.actor_id].hp_current == 1


def test_actor_registry_actors_is_mapping_proxy() -> None:
    registry = ActorRegistry(actors={TALIA.actor_id: TALIA})
    assert isinstance(registry.actors, MappingProxyType)


def test_actor_registry_actors_mapping_proxy_is_immutable() -> None:
    registry = ActorRegistry(actors={TALIA.actor_id: TALIA})
    with pytest.raises(TypeError):
        registry.actors["new_key"] = TALIA  # type: ignore[index]


def test_actor_registry_to_dict_round_trips() -> None:
    registry = ActorRegistry().with_actor(TALIA)
    data = registry.to_dict()
    restored = ActorRegistry.from_dict(data)
    assert TALIA.actor_id in restored.actors
    assert restored.actors[TALIA.actor_id].name == TALIA.name


def test_actor_registry_from_dict_empty_data_returns_empty() -> None:
    assert len(ActorRegistry.from_dict({}).actors) == 0


def test_actor_registry_from_dict_invalid_actors_value_returns_empty() -> None:
    assert len(ActorRegistry.from_dict({"actors": "not-a-mapping"}).actors) == 0


def test_encounter_transition_constructs() -> None:
    presence = NpcPresence(
        actor_id="npc:elara",
        display_name="Elara",
        description="the herbalist",
        name_known=True,
        status=NpcPresenceStatus.INTERACTED,
    )
    transition = EncounterTransition(
        from_encounter_id="enc-001",
        next_location_hint="The cave entrance",
        traveling_actor_ids=("npc:elara",),
        traveling_actors={"npc:elara": TALIA},
        traveling_presences=(presence,),
    )
    assert transition.from_encounter_id == "enc-001"
    assert transition.next_location_hint == "The cave entrance"
    assert transition.traveling_actor_ids == ("npc:elara",)
    assert len(transition.traveling_presences) == 1


def test_encounter_transition_next_location_hint_can_be_none() -> None:
    transition = EncounterTransition(
        from_encounter_id="enc-001",
        next_location_hint=None,
        traveling_actor_ids=(),
        traveling_actors={},
        traveling_presences=(),
    )
    assert transition.next_location_hint is None


def test_encounter_transition_traveling_actors_is_mapping_proxy() -> None:
    transition = EncounterTransition(
        from_encounter_id="enc-001",
        next_location_hint=None,
        traveling_actor_ids=("npc:elara",),
        traveling_actors={"npc:elara": TALIA},
        traveling_presences=(),
    )
    assert isinstance(transition.traveling_actors, MappingProxyType)
