"""Repository for loading pre-built Level 1 character class templates."""

from __future__ import annotations

import json
from pathlib import Path

from campaignnarrator.domain.models import ActorState
from campaignnarrator.repositories.player_repository import player_template_from_seed


class CharacterTemplateRepository:
    """Load character class templates from JSON files.

    Each template is a complete ActorState seed with name/race/description/
    background set to null. Character creation stamps those fields in before
    persisting the final actor.
    """

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)

    def load(self, class_name: str) -> ActorState:
        """Load a class template by name (e.g. 'fighter', 'rogue').

        The returned ActorState has name=""; callers must set it before use.
        Raises FileNotFoundError if the template does not exist.
        """
        path = self._root / f"{class_name}.json"
        if not path.exists():
            raise FileNotFoundError(  # noqa: TRY003
                f"character template not found: {class_name!r}"
            )
        seed = json.loads(path.read_text())
        # Templates use null for name; replace with empty string so
        # player_template_from_seed can parse it (name is required in the domain).
        if seed.get("name") is None:
            seed["name"] = ""
        return player_template_from_seed(seed)

    def available_classes(self) -> list[str]:
        """Return class names for all available templates, sorted."""
        return sorted(p.stem for p in self._root.glob("*.json"))
