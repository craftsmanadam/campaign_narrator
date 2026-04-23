"""File-backed memory repository with optional LanceDB vector store."""

from __future__ import annotations

import contextlib
import json
import logging
import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import lancedb
import pyarrow as pa

from campaignnarrator.domain.models import GameState
from campaignnarrator.repositories.state_repository import StateRepository

if TYPE_CHECKING:
    from campaignnarrator.adapters.embedding_adapter import EmbeddingAdapter

_logger = logging.getLogger(__name__)


def _build_schema(dimensions: int) -> pa.Schema:
    return pa.schema(
        [
            pa.field("id", pa.string()),
            pa.field("text", pa.string()),
            pa.field("event_type", pa.string()),
            pa.field("campaign_id", pa.string()),
            pa.field("module_id", pa.string()),
            pa.field("encounter_id", pa.string()),
            pa.field("timestamp", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), dimensions)),
        ]
    )


# max number of exchange items (player+narrator) retained per session
_MAX_EXCHANGES = 10


@dataclass
class _SessionCache:
    """In-memory session state. Only persist() writes this to disk."""

    game_state: GameState | None = None
    exchange_buffer: tuple[str, ...] = ()
    # element shape: (text, metadata)
    staged_narrations: list[tuple[str, dict[str, str]]] = field(default_factory=list)
    combat_round_logs: list[str] = field(default_factory=list)


class MemoryRepository:
    """Append and read newline-delimited JSON memory events.

    When constructed with both embedding_adapter and lancedb_path, narrative
    records are embedded and stored in LanceDB for semantic retrieval.
    When either is absent, the existing JSONL-only behaviour is preserved.
    """

    def __init__(
        self,
        root: Path | str,
        *,
        state_repo: StateRepository,
        embedding_adapter: EmbeddingAdapter | None = None,
        lancedb_path: Path | str | None = None,
    ) -> None:
        self._root = Path(root)
        self._event_log_path = self._root / "event_log.jsonl"
        self._narrative_path = self._root / "narrative_memory.jsonl"
        self._embedding_adapter = embedding_adapter
        self._lancedb_table: object | None = None

        if embedding_adapter is not None and lancedb_path is not None:
            self._lancedb_table = self._init_lancedb(
                Path(lancedb_path), embedding_adapter
            )

        self._state_repo = state_repo
        self._cache = _SessionCache()
        self._restore_exchange_buffer()

    def _restore_exchange_buffer(self) -> None:
        """Load exchange buffer from disk on startup."""
        path = self._root / "exchange_buffer.json"
        if path.exists():
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                self._cache = replace(
                    self._cache,
                    exchange_buffer=tuple(json.loads(path.read_text(encoding="utf-8"))),
                )

    def _init_lancedb(
        self,
        lancedb_path: Path,
        embedding_adapter: EmbeddingAdapter,
    ) -> object:
        lancedb_path.mkdir(parents=True, exist_ok=True)
        db = lancedb.connect(str(lancedb_path))
        schema = _build_schema(embedding_adapter.dimensions)
        if "narrative_memory" in db.list_tables().tables:
            table = db.open_table("narrative_memory")
        else:
            table = db.create_table("narrative_memory", schema=schema)
            table.create_fts_index("text")
        self._migrate_jsonl_to_lancedb(table, embedding_adapter)
        return table

    def _migrate_jsonl_to_lancedb(
        self,
        table: object,
        embedding_adapter: EmbeddingAdapter,
    ) -> None:
        """Migrate narrative_memory.jsonl into LanceDB if table is empty.

        Idempotent: skips entirely if the table already has rows, or if the
        JSONL file does not exist. The JSONL file is never modified or deleted.
        """
        if not self._narrative_path.exists():
            return
        if table.count_rows() > 0:  # type: ignore[union-attr]
            return
        records = []
        for line in self._narrative_path.read_text().splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            text: str = entry.get("text", "")
            metadata: dict[str, str] = entry.get("metadata", {})
            records.append(
                {
                    "id": str(uuid.uuid4()),
                    "text": text,
                    "event_type": metadata.get("event_type", ""),
                    "campaign_id": metadata.get("campaign_id", ""),
                    "module_id": metadata.get("module_id", ""),
                    "encounter_id": metadata.get("encounter_id", ""),
                    "timestamp": datetime.now(UTC).isoformat(),
                    "vector": embedding_adapter.embed(text),
                }
            )
        if records:
            table.add(records)  # type: ignore[union-attr]

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
        """Append a narrative record to narrative_memory.jsonl (always) and
        to LanceDB (when embedding_adapter and lancedb_path were provided).

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

        if self._lancedb_table is not None and self._embedding_adapter is not None:
            vector = self._embedding_adapter.embed(text)
            self._lancedb_table.add(
                [
                    {  # type: ignore[union-attr]
                        "id": str(uuid.uuid4()),
                        "text": text,
                        "event_type": metadata.get("event_type", ""),
                        "campaign_id": metadata.get("campaign_id", ""),
                        "module_id": metadata.get("module_id", ""),
                        "encounter_id": metadata.get("encounter_id", ""),
                        "timestamp": datetime.now(UTC).isoformat(),
                        "vector": vector,
                    }
                ]
            )

    def retrieve_relevant(self, query: str, *, limit: int = 5) -> list[str]:
        """Return up to `limit` text entries whose content matches `query`.

        LanceDB mode: runs FTS (keyword) search and vector (semantic) search
        separately, merges results deduped by id — FTS hits prioritised first
        (exact name/entity matches), then vector hits fill remaining slots.

        JSONL fallback: case-insensitive substring scan (original behaviour),
        used when no embedding_adapter or lancedb_path was provided.
        """
        if self._lancedb_table is not None and self._embedding_adapter is not None:
            return self._retrieve_from_lancedb(query, limit=limit)

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

    # ── Session cache ──────────────────────────────────────────────────────────

    def update_game_state(self, game_state: GameState) -> None:
        """Stage game state. No disk write — only persist() flushes."""
        self._cache = replace(self._cache, game_state=game_state)

    def load_game_state(self) -> GameState:
        """Read game state from disk via private StateRepository."""
        return self._state_repo.load()

    def update_exchange(self, player_input: str, narrator_output: str) -> None:
        """Append player + narrator pair to rolling exchange buffer."""
        new_buffer = (*self._cache.exchange_buffer, player_input, narrator_output)
        if len(new_buffer) > _MAX_EXCHANGES:
            new_buffer = new_buffer[-_MAX_EXCHANGES:]
        self._cache = replace(self._cache, exchange_buffer=new_buffer)

    def get_exchange_buffer(self) -> tuple[str, ...]:
        """Return the current in-memory exchange buffer."""
        return self._cache.exchange_buffer

    def stage_narration(self, text: str, metadata: dict[str, str]) -> None:
        """Queue a narration entry for the next persist() call."""
        self._cache.staged_narrations.append((text, metadata))

    def log_combat_round(self, entry: str) -> None:
        """Append an ephemeral combat round log. Never persisted to disk."""
        self._cache.combat_round_logs.append(entry)

    def persist(self) -> None:
        """Flush all staged session state to disk.

        Only caller: _LazyGameOrchestrator.save_state().
        """
        if self._cache.game_state is not None:
            self._state_repo.save(self._cache.game_state)
        for text, metadata in self._cache.staged_narrations:
            self.store_narrative(text, metadata)
        exchange_path = self._root / "exchange_buffer.json"
        exchange_path.parent.mkdir(parents=True, exist_ok=True)
        exchange_path.write_text(
            json.dumps(list(self._cache.exchange_buffer)), encoding="utf-8"
        )
        self._cache = _SessionCache(exchange_buffer=self._cache.exchange_buffer)

    def clear_combat_memory(self) -> None:
        """Clear only combat_round_logs from the session cache."""
        self._cache = replace(self._cache, combat_round_logs=[])

    def clear_encounter_memory(self) -> None:
        """Reset game_state, staged_narrations, and combat_round_logs.

        Preserves exchange_buffer.
        """
        self._cache = _SessionCache(exchange_buffer=self._cache.exchange_buffer)

    def _retrieve_from_lancedb(self, query: str, *, limit: int) -> list[str]:
        """Hybrid retrieval: FTS keyword search + vector similarity search, merged."""
        fetch = limit * 3

        try:
            fts_rows = (
                self._lancedb_table.search(query, query_type="fts")  # type: ignore[union-attr]
                .limit(fetch)
                .to_list()
            )
        except Exception as exc:  # LanceDB FTS may fail if no index exists yet
            _logger.warning("FTS search failed, falling back to vector-only: %s", exc)
            fts_rows = []

        query_vector = self._embedding_adapter.embed(query)  # type: ignore[union-attr]
        vector_rows = (
            self._lancedb_table.search(query_vector)  # type: ignore[union-attr]
            .limit(fetch)
            .to_list()
        )

        seen_ids: set[str] = set()
        merged: list[str] = []
        for row in fts_rows + vector_rows:
            row_id: str = row["id"]
            if row_id not in seen_ids and len(merged) < limit:
                seen_ids.add(row_id)
                merged.append(row["text"])
        return merged
