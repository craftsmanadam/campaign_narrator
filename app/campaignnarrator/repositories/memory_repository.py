"""File-backed memory repository."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class MemoryRepository:
    """Append and read newline-delimited JSON memory events."""

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)
        self._event_log_path = self._root / "event_log.jsonl"
        self._narrative_path = self._root / "narrative_memory.jsonl"

    def load_event_log(self) -> list[dict[str, Any]]:
        """Return all stored events in order."""

        if not self._event_log_path.exists():
            return []
        return [
            json.loads(line)
            for line in self._event_log_path.read_text().splitlines()
            if line.strip()
        ]

    def append_event(self, event: dict[str, Any]) -> None:
        """Append a JSON event line to the log."""

        self._event_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._event_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, separators=(",", ":")) + "\n")

    def store_narrative(self, text: str, metadata: dict[str, str]) -> None:
        """Append a narrative record to narrative_memory.jsonl.

        Metadata keys used across the codebase:
            event_type:   "encounter_summary" | "campaign_setting" | "player_background"
            campaign_id:  str
            module_id:    str  (optional)
            encounter_id: str  (optional)
        """
        self._root.mkdir(parents=True, exist_ok=True)
        record = {"text": text, "metadata": metadata}
        with self._narrative_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")

    def retrieve_relevant(self, query: str, *, limit: int = 5) -> list[str]:
        """Return up to `limit` text entries whose content matches `query`.

        Current implementation: case-insensitive substring scan on all records in
        narrative_memory.jsonl. Returns plain text strings, not metadata.

        LanceDB upgrade (backlog item 22): replaces scan with hybrid vector + keyword
        search using nomic-embed-text embeddings. Return type and signature unchanged.
        """
        if not self._narrative_path.exists():
            return []
        query_lower = query.lower()
        matches: list[str] = []
        for line in self._narrative_path.read_text().splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            text: str = record.get("text", "")
            if query_lower in text.lower():
                matches.append(text)
                if len(matches) >= limit:
                    break
        return matches
