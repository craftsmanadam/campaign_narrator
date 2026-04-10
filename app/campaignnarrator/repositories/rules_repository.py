"""File-backed rule repository."""

from __future__ import annotations

import json
from pathlib import Path


class RulesRepository:
    """Load rule index data and markdown topics from a repository root."""

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)
        self._resolved_root = self._root.resolve()

    def load_rule_index(self) -> dict[str, list[str]]:
        """Return the generated rule index."""

        path = self._root / "generated" / "rule_index.json"
        return json.loads(path.read_text())

    def load_topic_markdown(self, relative_path: str | Path) -> str:
        """Return the raw markdown for a rule topic."""

        candidate = (self._root / Path(relative_path)).resolve()
        if self._resolved_root not in candidate.parents and (
            candidate != self._resolved_root
        ):
            raise ValueError
        return candidate.read_text()
