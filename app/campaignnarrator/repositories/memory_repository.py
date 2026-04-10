"""File-backed memory repository."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class MemoryRepository:
    """Append and read newline-delimited JSON memory events."""

    def __init__(self, root: Path | str) -> None:
        self._event_log_path = Path(root) / "event_log.jsonl"

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
