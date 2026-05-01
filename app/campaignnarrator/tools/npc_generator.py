"""NPC actor construction from encounter template definitions."""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path

from campaignnarrator.domain.models import ActorState, ActorType, EncounterNpc
from campaignnarrator.tools.monster_loader import load_by_name as _load_monster

_log = logging.getLogger(__name__)

_SIMPLE_NPC_HP = 1
_SIMPLE_NPC_AC = 10


def build_npc_actor(
    npc: EncounterNpc,
    actor_id: str,
    index_path: Path | None,
) -> ActorState:
    """Build an ActorState from an EncounterNpc planning-time definition.

    Uses compendium stats when stat_source='monster_compendium' and
    index_path is valid. Falls back to simple placeholder stats on any
    lookup failure.
    """
    if (
        npc.stat_source == "monster_compendium"
        and npc.monster_name
        and index_path is not None
        and index_path.exists()
    ):
        try:
            actor = _load_monster(npc.monster_name, index_path=index_path)
            return replace(actor, actor_id=actor_id, name=npc.display_name)
        except KeyError:
            _log.warning(
                "Monster %r not found in compendium; using simple NPC stats",
                npc.monster_name,
            )
        except FileNotFoundError:
            _log.warning(
                "Monster %r not found in compendium; using simple NPC stats",
                npc.monster_name,
            )
    return ActorState(
        actor_id=actor_id,
        name=npc.display_name,
        actor_type=ActorType.NPC,
        hp_max=_SIMPLE_NPC_HP,
        hp_current=_SIMPLE_NPC_HP,
        armor_class=_SIMPLE_NPC_AC,
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
        action_options=("Talk",),
        ac_breakdown=(),
    )
