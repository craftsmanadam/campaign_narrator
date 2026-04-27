"""Unit tests for actor_components domain models."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from campaignnarrator.domain.models import (
    FeatState,
    InventoryItem,
    RecoveryPeriod,
    ResourceState,
    WeaponState,
)


def test_recovery_period_has_expected_string_values() -> None:
    assert RecoveryPeriod.TURN == "turn"
    assert RecoveryPeriod.SHORT_REST == "short_rest"
    assert RecoveryPeriod.LONG_REST == "long_rest"
    assert RecoveryPeriod.DAY == "day"


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


def test_feat_state_round_trips_to_dict() -> None:
    feat = FeatState(
        name="Alert",
        effect_summary="Add proficiency bonus to initiative.",
        reference="DND.SRD/Feats.md#Alert",
        per_turn_uses=None,
    )
    assert FeatState.from_dict(feat.to_dict()) == feat


def test_feat_state_round_trips_with_per_turn_uses() -> None:
    feat = FeatState(
        name="Savage Attacker",
        effect_summary="Reroll damage once per turn.",
        reference=None,
        per_turn_uses=1,
    )
    result = FeatState.from_dict(feat.to_dict())
    assert result.per_turn_uses == 1
    assert result.reference is None


def test_weapon_state_round_trips_to_dict() -> None:
    weapon = WeaponState(
        name="Longsword",
        attack_bonus=7,
        damage_dice="1d8",
        damage_bonus=4,
        damage_type="slashing",
        properties=("versatile (1d10)", "finesse"),
    )
    result = WeaponState.from_dict(weapon.to_dict())
    assert result == weapon


def test_resource_state_round_trips_to_dict() -> None:
    r = ResourceState(
        resource="second_wind",
        current=1,
        max=1,
        recovers_after=RecoveryPeriod.SHORT_REST,
        reference="class_features.json#second-wind",
    )
    assert ResourceState.from_dict(r.to_dict()) == r


def test_resource_state_round_trips_without_reference() -> None:
    r = ResourceState(
        resource="action_surge",
        current=0,
        max=1,
        recovers_after=RecoveryPeriod.SHORT_REST,
    )
    result = ResourceState.from_dict(r.to_dict())
    assert result.reference is None


def test_inventory_item_round_trips_to_dict_minimal() -> None:
    item = InventoryItem(item_id="potion-1", item="Potion of Healing", count=2)
    assert InventoryItem.from_dict(item.to_dict()) == item


def test_inventory_item_round_trips_to_dict_with_charges() -> None:
    item = InventoryItem(
        item_id="wand-1",
        item="Wand of Magic Missiles",
        count=1,
        charges=5,
        max_charges=7,
        recovers_after=RecoveryPeriod.DAY,
        reference="magic_items/wands.json#wand-of-magic-missiles",
    )
    result = InventoryItem.from_dict(item.to_dict())
    assert result == item
