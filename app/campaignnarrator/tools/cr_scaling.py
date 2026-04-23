"""CR scaling utility: trim NPC lists to fit a per-level encounter budget."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from campaignnarrator.domain.models import EncounterNpc

_log = logging.getLogger(__name__)


def scale_encounter_npcs(
    npcs: Sequence[EncounterNpc],
    player_level: int,
) -> tuple[EncounterNpc, ...]:
    """Return a trimmed copy of *npcs* that fits within the CR budget.

    Budget formula: ``target_cr = player_level / 4``; ``budget = target_cr + 0.25``.
    If the total CR already fits, the original tuple is returned unchanged.
    At least one NPC is always kept even when the single NPC exceeds the budget.
    Lowest-CR NPCs are removed first.
    """
    if not npcs:
        return tuple(npcs)

    target_cr = player_level / 4
    budget = target_cr + 0.25

    remaining = list(npcs)
    total_cr = sum(npc.cr for npc in remaining)

    if total_cr <= budget:
        return tuple(npcs)

    # Sort ascending by CR so we pop cheapest first; use original indices to
    # preserve relative order among survivors.
    while total_cr > budget and len(remaining) > 1:
        # Find index of the NPC with the lowest CR (first occurrence on tie).
        min_idx = min(range(len(remaining)), key=lambda i: remaining[i].cr)
        removed = remaining.pop(min_idx)
        total_cr -= removed.cr

    _log.warning(
        "Encounter trimmed to %d NPC(s) (total CR %.2f) for level %d (budget %.2f)",
        len(remaining),
        total_cr,
        player_level,
        budget,
    )
    return tuple(remaining)
