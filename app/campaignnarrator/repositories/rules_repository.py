"""File-backed rule repository."""

from __future__ import annotations

import json
from pathlib import Path


class RulesRepository:
    """Load rule index data and markdown topics from a repository root."""

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)
        self._resolved_root = self._root.resolve()
        self._missing_context_marker = "Missing rules context:"

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

    def load_context_for_topics(self, topics: tuple[str, ...]) -> tuple[str, ...]:
        """Return loaded markdown context for the requested rule topics."""

        rule_index = self._load_rule_index_or_empty()
        contexts: list[str] = []
        for topic in topics:
            contexts.append(self._load_topic_context(topic, rule_index))
        return tuple(contexts)

    def _load_rule_index_or_empty(self) -> dict[str, list[str]]:
        try:
            return self.load_rule_index()
        except FileNotFoundError:
            return {}

    def _load_topic_context(
        self,
        topic: str,
        rule_index: dict[str, list[str]],
    ) -> str:
        relative_paths = rule_index.get(topic)
        if not relative_paths:
            return f"{self._missing_context_marker} {topic}"

        topic_markdown: list[str] = []
        for relative_path in relative_paths:
            try:
                topic_markdown.append(self.load_topic_markdown(relative_path))
            except FileNotFoundError, ValueError:
                return f"{self._missing_context_marker} {topic}"
        return "\n\n".join(topic_markdown)
