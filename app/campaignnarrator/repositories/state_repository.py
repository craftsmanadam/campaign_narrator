"""File-backed campaign state repository."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class StateRepository:
    """Load and save the player character state."""

    def __init__(self, root: Path | str) -> None:
        self._player_character_path = Path(root) / "player_character.json"

    def load_player_character(self) -> dict[str, Any]:
        """Read the current player character snapshot."""

        return json.loads(self._player_character_path.read_text())

    def save_player_character(self, player_character: dict[str, Any]) -> None:
        """Persist the player character snapshot."""

        self._player_character_path.write_text(
            json.dumps(player_character, indent=2, sort_keys=True) + "\n"
        )
