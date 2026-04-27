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


def test_npc_presence_defaults_to_available() -> None:
    presence = NpcPresence(
        actor_id="npc:goblin-001",
        display_name="Goblin Scout",
        description="the goblin",
        name_known=False,
    )
    assert presence.status is NpcPresenceStatus.AVAILABLE


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


def test_npc_presence_status_has_available() -> None:
    assert NpcPresenceStatus.AVAILABLE == "available"


def test_npc_presence_status_has_interacted() -> None:
    assert NpcPresenceStatus.INTERACTED == "interacted"


def test_npc_presence_status_has_mentioned() -> None:
    assert NpcPresenceStatus.MENTIONED == "mentioned"


def test_npc_presence_status_present_is_legacy_alias() -> None:
    assert NpcPresenceStatus.PRESENT == "present"


def test_npc_presence_default_status_is_available() -> None:
    presence = NpcPresence(
        actor_id="npc:elder",
        display_name="Elder Rovan",
        description="the village elder",
        name_known=True,
    )
    assert presence.status is NpcPresenceStatus.AVAILABLE


def test_npc_presence_has_empty_interaction_summaries_by_default() -> None:
    presence = NpcPresence(
        actor_id="npc:elder",
        display_name="Elder Rovan",
        description="the village elder",
        name_known=True,
    )
    assert presence.interaction_summaries == ()


def test_npc_presence_interaction_summaries_stored() -> None:
    presence = NpcPresence(
        actor_id="npc:elder",
        display_name="Elder Rovan",
        description="the village elder",
        name_known=True,
        status=NpcPresenceStatus.INTERACTED,
        interaction_summaries=("Player asked about children; Elder denied knowledge.",),
    )
    assert len(presence.interaction_summaries) == 1


def test_npc_presence_to_dict_omits_summaries_when_empty() -> None:
    presence = NpcPresence(
        actor_id="npc:elder",
        display_name="Elder Rovan",
        description="the village elder",
        name_known=True,
    )
    d = presence.to_dict()
    assert "interaction_summaries" not in d


def test_npc_presence_to_dict_includes_summaries_when_present() -> None:
    presence = NpcPresence(
        actor_id="npc:elder",
        display_name="Elder Rovan",
        description="the village elder",
        name_known=True,
        status=NpcPresenceStatus.INTERACTED,
        interaction_summaries=("Player asked about children; Elder denied knowledge.",),
    )
    d = presence.to_dict()
    assert d["interaction_summaries"] == [
        "Player asked about children; Elder denied knowledge."
    ]


def test_npc_presence_from_dict_defaults_summaries_to_empty_tuple() -> None:
    data = {
        "actor_id": "npc:elder",
        "display_name": "Elder Rovan",
        "description": "the village elder",
        "name_known": True,
        "status": "available",
    }
    presence = NpcPresence.from_dict(data)
    assert presence.interaction_summaries == ()


def test_npc_presence_from_dict_restores_summaries() -> None:
    data = {
        "actor_id": "npc:elder",
        "display_name": "Elder Rovan",
        "description": "the village elder",
        "name_known": True,
        "status": "interacted",
        "interaction_summaries": [
            "Player asked about children; Elder denied knowledge."
        ],
    }
    presence = NpcPresence.from_dict(data)
    assert presence.interaction_summaries == (
        "Player asked about children; Elder denied knowledge.",
    )


def test_npc_presence_roundtrip_with_summaries() -> None:
    presence = NpcPresence(
        actor_id="npc:elder",
        display_name="Elder Rovan",
        description="the village elder",
        name_known=True,
        status=NpcPresenceStatus.INTERACTED,
        interaction_summaries=("First exchange.", "Second exchange."),
    )
    assert NpcPresence.from_dict(presence.to_dict()) == presence


def test_npc_presence_from_dict_handles_available_status() -> None:
    data = {
        "actor_id": "npc:x",
        "display_name": "X",
        "description": "desc",
        "name_known": False,
        "status": "available",
    }
    presence = NpcPresence.from_dict(data)
    assert presence.status is NpcPresenceStatus.AVAILABLE


def test_npc_presence_from_dict_handles_mentioned_status() -> None:
    data = {
        "actor_id": "npc:x",
        "display_name": "X",
        "description": "desc",
        "name_known": False,
        "status": "mentioned",
    }
    presence = NpcPresence.from_dict(data)
    assert presence.status is NpcPresenceStatus.MENTIONED
