"""Unit tests for npc_presence domain models."""

from __future__ import annotations

import pytest
from campaignnarrator.domain.models import (
    NpcPresence,
    NpcPresenceStatus,
)


def test_npc_presence_stores_fields() -> None:
    presence = NpcPresence(
        actor_id="npc:innkeeper-001",
        display_name="Mira",
        description="the innkeeper",
        name_known=False,
        status=NpcPresenceStatus.PRESENT,
    )
    assert presence.actor_id == "npc:innkeeper-001"
    assert presence.display_name == "Mira"
    assert presence.description == "the innkeeper"
    assert not presence.name_known
    assert presence.status is NpcPresenceStatus.PRESENT


def test_npc_presence_round_trips_to_dict() -> None:
    presence = NpcPresence(
        actor_id="npc:innkeeper-001",
        display_name="Mira",
        description="the innkeeper",
        name_known=True,
        status=NpcPresenceStatus.PRESENT,
    )
    assert NpcPresence.from_dict(presence.to_dict()) == presence


def test_npc_presence_from_dict_raises_on_missing_fields() -> None:
    with pytest.raises(TypeError):
        NpcPresence.from_dict({"actor_id": "npc:x"})


def test_npc_presence_defaults_to_present() -> None:
    presence = NpcPresence(
        actor_id="npc:goblin-001",
        display_name="Goblin Scout",
        description="the goblin",
        name_known=False,
    )
    assert presence.status is NpcPresenceStatus.PRESENT


def test_npc_presence_round_trips_concealed() -> None:
    presence = NpcPresence(
        actor_id="npc:rogue-001",
        display_name="Shadow",
        description="a cloaked figure",
        name_known=False,
        status=NpcPresenceStatus.CONCEALED,
    )
    assert NpcPresence.from_dict(presence.to_dict()) == presence


def test_npc_presence_round_trips_departed() -> None:
    presence = NpcPresence(
        actor_id="npc:goblin-001",
        display_name="Goblin Scout",
        description="the goblin",
        name_known=True,
        status=NpcPresenceStatus.DEPARTED,
    )
    result = NpcPresence.from_dict(presence.to_dict())
    assert result.status is NpcPresenceStatus.DEPARTED


def test_npc_presence_from_dict_backward_compat_visible_true() -> None:
    """Old save format uses visible: True — maps to PRESENT."""
    old_data = {
        "actor_id": "npc:innkeeper-001",
        "display_name": "Mira",
        "description": "the innkeeper",
        "name_known": True,
        "visible": True,
    }
    presence = NpcPresence.from_dict(old_data)
    assert presence.status is NpcPresenceStatus.PRESENT


def test_npc_presence_from_dict_backward_compat_visible_false() -> None:
    """Old save format uses visible: False — maps to CONCEALED."""
    old_data = {
        "actor_id": "npc:innkeeper-001",
        "display_name": "Mira",
        "description": "the innkeeper",
        "name_known": True,
        "visible": False,
    }
    presence = NpcPresence.from_dict(old_data)
    assert presence.status is NpcPresenceStatus.CONCEALED


def test_npc_presence_from_dict_raises_on_invalid_status() -> None:
    with pytest.raises(TypeError, match="invalid status"):
        NpcPresence.from_dict(
            {
                "actor_id": "npc:x",
                "display_name": "X",
                "description": "d",
                "name_known": False,
                "status": "gone",
            }
        )


def test_npc_presence_from_dict_status_takes_priority_over_visible() -> None:
    data = {
        "actor_id": "npc:x",
        "display_name": "X",
        "description": "d",
        "name_known": False,
        "status": "departed",
        "visible": True,
    }
    presence = NpcPresence.from_dict(data)
    assert presence.status is NpcPresenceStatus.DEPARTED
