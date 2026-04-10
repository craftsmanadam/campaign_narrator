"""State update helpers for campaign character changes."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

_POTION_IDENTIFIERS = {"potion-of-healing", "potion of healing"}


def apply_potion_of_healing(
    player_character: dict[str, Any],
    healing_amount: int,
) -> dict[str, Any]:
    """Consume one potion of healing and clamp HP to the maximum."""

    updated_character = deepcopy(player_character)
    inventory = list(updated_character.get("inventory", []))
    potion_index = next(
        (
            index
            for index, item in enumerate(inventory)
            if isinstance(item, str) and item.lower() in _POTION_IDENTIFIERS
        ),
        None,
    )
    if potion_index is None:
        raise ValueError

    del inventory[potion_index]

    hp = dict(updated_character.get("hp", {}))
    current_hp = int(hp["current"])
    max_hp = int(hp["max"])
    hp["current"] = min(max_hp, current_hp + healing_amount)

    updated_character["inventory"] = inventory
    updated_character["hp"] = hp
    return updated_character
