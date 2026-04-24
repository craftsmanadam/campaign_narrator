"""Encounter persistence repository."""

from __future__ import annotations

import json
from pathlib import Path

from campaignnarrator.domain.models import EncounterState


class EncounterRepository:
    """Persist and load the single active encounter to/from a JSON file."""

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)
        self._encounter_path = self._root / "encounters" / "active.json"

    def load_active(self) -> EncounterState | None:
        """Load the active encounter. Returns None if no file exists."""
        if not self._encounter_path.exists():
            return None
        return EncounterState.from_dict(json.loads(self._encounter_path.read_text()))

    def save(self, state: EncounterState) -> None:
        """Persist the active encounter to disk."""
        self._encounter_path.parent.mkdir(parents=True, exist_ok=True)
        self._encounter_path.write_text(
            json.dumps(state.to_dict(), indent=2, sort_keys=True) + "\n"
        )

    def clear(self) -> None:
        """Delete the active encounter file."""
        if self._encounter_path.exists():
            self._encounter_path.unlink()
