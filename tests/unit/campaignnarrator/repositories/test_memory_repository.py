"""Unit tests for the memory repository."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import lancedb
import pytest
from campaignnarrator.adapters.embedding_adapter import StubEmbeddingAdapter
from campaignnarrator.repositories.memory_repository import MemoryRepository


def test_memory_repository_appends_and_loads_event_log(tmp_path: Path) -> None:
    """The repository should persist events in newline-delimited JSON."""

    memory_root = tmp_path / "memory"
    memory_root.mkdir(parents=True)
    (memory_root / "event_log.jsonl").write_text(
        '{"event_id": "evt-001", "type": "seed"}\n'
    )

    repository = MemoryRepository(memory_root, state_repo=MagicMock())

    repository.append_event({"event_id": "evt-002", "type": "state_updated"})

    assert repository.load_event_log() == [
        {"event_id": "evt-001", "type": "seed"},
        {"event_id": "evt-002", "type": "state_updated"},
    ]


def _make_repo(tmp: str) -> MemoryRepository:
    return MemoryRepository(tmp, state_repo=MagicMock())


def test_store_narrative_creates_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(tmp)
        repo.store_narrative(
            "The docks reeked of salt and death.",
            {"event_type": "encounter_summary", "campaign_id": "c-1"},
        )
        narrative_path = Path(tmp) / "narrative_memory.jsonl"
        assert narrative_path.exists()


def test_store_narrative_writes_jsonl_record() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(tmp)
        repo.store_narrative(
            "Aldric confronted a robed figure.",
            {
                "event_type": "encounter_summary",
                "campaign_id": "c-1",
                "encounter_id": "module-001-enc-001",
            },
        )
        narrative_path = Path(tmp) / "narrative_memory.jsonl"
        line = narrative_path.read_text().strip()
        record = json.loads(line)
        assert record["text"] == "Aldric confronted a robed figure."
        assert record["metadata"]["event_type"] == "encounter_summary"
        assert record["metadata"]["encounter_id"] == "module-001-enc-001"


def test_store_narrative_appends_multiple_records() -> None:
    expected_record_count = 2
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(tmp)
        repo.store_narrative("First summary.", {"event_type": "encounter_summary"})
        repo.store_narrative("Second summary.", {"event_type": "encounter_summary"})
        narrative_path = Path(tmp) / "narrative_memory.jsonl"
        lines = [
            line for line in narrative_path.read_text().splitlines() if line.strip()
        ]
        assert len(lines) == expected_record_count



def _make_lancedb_repo(tmp: str) -> MemoryRepository:
    """MemoryRepository in LanceDB mode using StubEmbeddingAdapter."""
    adapter = StubEmbeddingAdapter()
    lancedb_path = Path(tmp) / "lancedb"
    return MemoryRepository(
        tmp,
        state_repo=MagicMock(),
        embedding_adapter=adapter,
        lancedb_path=lancedb_path,
    )


def test_lancedb_mode_creates_lancedb_directory(tmp_path: Path) -> None:
    _make_lancedb_repo(str(tmp_path))
    lancedb_dir = tmp_path / "lancedb"
    assert lancedb_dir.exists()


def test_lancedb_mode_creates_narrative_memory_table(tmp_path: Path) -> None:
    _make_lancedb_repo(str(tmp_path))
    db = lancedb.connect(str(tmp_path / "lancedb"))
    assert "narrative_memory" in db.list_tables().tables


def test_lancedb_mode_table_starts_empty(tmp_path: Path) -> None:
    _make_lancedb_repo(str(tmp_path))
    db = lancedb.connect(str(tmp_path / "lancedb"))
    table = db.open_table("narrative_memory")
    assert table.count_rows() == 0


def test_lancedb_mode_opens_existing_table_on_reconnect(tmp_path: Path) -> None:
    """Second construction reuses the existing table rather than failing."""
    _make_lancedb_repo(str(tmp_path))
    _make_lancedb_repo(str(tmp_path))
    db = lancedb.connect(str(tmp_path / "lancedb"))
    assert "narrative_memory" in db.list_tables().tables


def test_no_adapter_does_not_create_lancedb_directory(tmp_path: Path) -> None:
    """JSONL-only mode: no LanceDB directory created."""
    MemoryRepository(str(tmp_path), state_repo=MagicMock())
    assert not (tmp_path / "lancedb").exists()


def test_store_narrative_lancedb_inserts_record(tmp_path: Path) -> None:
    repo = _make_lancedb_repo(str(tmp_path))
    repo.store_narrative(
        "Malachar stood at the docks.",
        {"event_type": "encounter_summary", "campaign_id": "c-1"},
    )
    db = lancedb.connect(str(tmp_path / "lancedb"))
    table = db.open_table("narrative_memory")
    assert table.count_rows() == 1


def test_store_narrative_lancedb_stores_text_field(tmp_path: Path) -> None:
    repo = _make_lancedb_repo(str(tmp_path))
    repo.store_narrative(
        "Malachar stood at the docks.",
        {"event_type": "encounter_summary", "campaign_id": "c-1"},
    )
    db = lancedb.connect(str(tmp_path / "lancedb"))
    rows = db.open_table("narrative_memory").search([0.0] * 768).limit(1).to_list()
    assert rows[0]["text"] == "Malachar stood at the docks."


def test_store_narrative_lancedb_stores_metadata_fields(tmp_path: Path) -> None:
    repo = _make_lancedb_repo(str(tmp_path))
    repo.store_narrative(
        "Campaign: The Sunken City. Setting: coastal noir.",
        {
            "event_type": "campaign_setting",
            "campaign_id": "c-1",
            "module_id": "m-1",
            "encounter_id": "e-1",
        },
    )
    db = lancedb.connect(str(tmp_path / "lancedb"))
    rows = db.open_table("narrative_memory").search([0.0] * 768).limit(1).to_list()
    row = rows[0]
    assert row["event_type"] == "campaign_setting"
    assert row["campaign_id"] == "c-1"
    assert row["module_id"] == "m-1"
    assert row["encounter_id"] == "e-1"


def test_store_narrative_lancedb_also_writes_jsonl_audit_log(tmp_path: Path) -> None:
    """JSONL file is always written regardless of LanceDB mode."""
    repo = _make_lancedb_repo(str(tmp_path))
    repo.store_narrative(
        "Malachar stood at the docks.",
        {"event_type": "encounter_summary", "campaign_id": "c-1"},
    )
    narrative_path = tmp_path / "narrative_memory.jsonl"
    assert narrative_path.exists()
    record = json.loads(narrative_path.read_text().strip())
    assert record["text"] == "Malachar stood at the docks."


def test_store_narrative_lancedb_multiple_records(tmp_path: Path) -> None:
    expected_count = 2
    meta = {"event_type": "encounter_summary", "campaign_id": "c-1"}
    repo = _make_lancedb_repo(str(tmp_path))
    repo.store_narrative("First.", meta)
    repo.store_narrative("Second.", meta)
    db = lancedb.connect(str(tmp_path / "lancedb"))
    assert db.open_table("narrative_memory").count_rows() == expected_count


def test_retrieve_relevant_lancedb_finds_by_keyword(tmp_path: Path) -> None:
    repo = _make_lancedb_repo(str(tmp_path))
    repo.store_narrative(
        "Malachar stood at the docks.",
        {"event_type": "encounter_summary", "campaign_id": "c-1"},
    )
    repo.store_narrative(
        "The barmaid served ale.",
        {"event_type": "encounter_summary", "campaign_id": "c-1"},
    )
    results = repo.retrieve_relevant("Malachar")
    assert len(results) >= 1
    assert any("Malachar" in r for r in results)


def test_retrieve_relevant_lancedb_returns_plain_strings(tmp_path: Path) -> None:
    repo = _make_lancedb_repo(str(tmp_path))
    repo.store_narrative(
        "Malachar stood at the docks.",
        {"event_type": "encounter_summary", "campaign_id": "c-1"},
    )
    results = repo.retrieve_relevant("Malachar")
    assert all(isinstance(r, str) for r in results)


def test_retrieve_relevant_lancedb_respects_limit(tmp_path: Path) -> None:
    entry_count = 10
    result_limit = 3
    repo = _make_lancedb_repo(str(tmp_path))
    for i in range(entry_count):
        repo.store_narrative(
            f"Entry {i} about the docks.",
            {"event_type": "encounter_summary", "campaign_id": "c-1"},
        )
    results = repo.retrieve_relevant("docks", limit=result_limit)
    assert len(results) <= result_limit


def test_retrieve_relevant_lancedb_empty_store_returns_empty(tmp_path: Path) -> None:
    repo = _make_lancedb_repo(str(tmp_path))
    assert repo.retrieve_relevant("anything") == []



_MALACHAR_JSONL = (
    '{"text": "Malachar stood at the docks.", '
    '"metadata": {"event_type": "encounter_summary", "campaign_id": "c-1"}}\n'
)
_FIRST_ENTRY_JSONL = (
    '{"text": "First entry.", '
    '"metadata": {"event_type": "encounter_summary", "campaign_id": "c-1"}}\n'
)
_SECOND_ENTRY_JSONL = (
    '{"text": "Second entry.", '
    '"metadata": {"event_type": "encounter_summary", "campaign_id": "c-1"}}\n'
)


def test_migration_imports_existing_jsonl_into_lancedb(tmp_path: Path) -> None:
    """Existing JSONL entries are migrated into LanceDB on first construction."""
    narrative_path = tmp_path / "narrative_memory.jsonl"
    narrative_path.write_text(_MALACHAR_JSONL)
    _make_lancedb_repo(str(tmp_path))
    db = lancedb.connect(str(tmp_path / "lancedb"))
    assert db.open_table("narrative_memory").count_rows() == 1


def test_migration_skipped_when_table_already_has_rows(tmp_path: Path) -> None:
    """Migration does not run if the LanceDB table already has rows (idempotent)."""
    narrative_path = tmp_path / "narrative_memory.jsonl"
    narrative_path.write_text(_FIRST_ENTRY_JSONL)
    # First construction: migrates the 1 JSONL entry
    _make_lancedb_repo(str(tmp_path))
    # Add another JSONL entry manually (simulating out-of-band write)
    with narrative_path.open("a") as f:
        f.write(_SECOND_ENTRY_JSONL)
    # Second construction: table already has 1 row, so migration is skipped
    _make_lancedb_repo(str(tmp_path))
    db = lancedb.connect(str(tmp_path / "lancedb"))
    # Only the original migrated row; second entry was not re-migrated
    assert db.open_table("narrative_memory").count_rows() == 1


def test_migration_skipped_when_no_jsonl_file(tmp_path: Path) -> None:
    """No migration attempted when narrative_memory.jsonl does not exist."""
    _make_lancedb_repo(str(tmp_path))
    db = lancedb.connect(str(tmp_path / "lancedb"))
    assert db.open_table("narrative_memory").count_rows() == 0


def test_migration_migrated_records_are_retrievable(tmp_path: Path) -> None:
    """Migrated JSONL records are retrievable via retrieve_relevant."""
    narrative_path = tmp_path / "narrative_memory.jsonl"
    narrative_path.write_text(_MALACHAR_JSONL)
    repo = _make_lancedb_repo(str(tmp_path))
    results = repo.retrieve_relevant("Malachar")
    assert len(results) >= 1
    assert any("Malachar" in r for r in results)


def test_update_game_state_does_not_write_disk(tmp_path: Path) -> None:
    """update_game_state() caches only — no file written immediately."""
    mock_state_repo = MagicMock()
    repo = MemoryRepository(str(tmp_path), state_repo=mock_state_repo)
    repo.update_game_state(MagicMock())
    mock_state_repo.save.assert_not_called()


def test_load_game_state_delegates_to_state_repo_when_cache_empty(
    tmp_path: Path,
) -> None:
    """load_game_state() reads from StateRepository when no game state is cached."""
    mock_state_repo = MagicMock()
    repo = MemoryRepository(str(tmp_path), state_repo=mock_state_repo)
    result = repo.load_game_state()
    mock_state_repo.load.assert_called_once()
    assert result is mock_state_repo.load.return_value


def test_load_game_state_returns_cached_state_when_staged(tmp_path: Path) -> None:
    """load_game_state() returns staged cache without hitting disk once staged."""
    mock_state_repo = MagicMock()
    repo = MemoryRepository(str(tmp_path), state_repo=mock_state_repo)
    staged = MagicMock()
    repo.update_game_state(staged)
    result = repo.load_game_state()
    assert result is staged
    mock_state_repo.load.assert_not_called()


def test_update_exchange_appends_two_items(tmp_path: Path) -> None:
    """update_exchange() adds player input + narrator output to the buffer."""
    repo = MemoryRepository(str(tmp_path), state_repo=MagicMock())
    repo.update_exchange("Hello", "Welcome to the docks.")
    assert repo.get_exchange_buffer() == ("Hello", "Welcome to the docks.")


def test_update_exchange_caps_at_max_exchanges(tmp_path: Path) -> None:
    """After 6 calls (12 items), buffer holds only the last 10 items."""
    call_count = 6
    expected_buffer_size = 10
    repo = MemoryRepository(str(tmp_path), state_repo=MagicMock())
    for i in range(call_count):
        repo.update_exchange(f"in{i}", f"out{i}")
    buf = repo.get_exchange_buffer()
    assert len(buf) == expected_buffer_size
    assert buf[0] == "in1"  # first two items (in0, out0) dropped


def test_stage_narration_does_not_write_disk(tmp_path: Path) -> None:
    """stage_narration() queues the entry — no JSONL write yet."""
    repo = MemoryRepository(str(tmp_path), state_repo=MagicMock())
    repo.stage_narration("A summary.", {"event_type": "encounter_partial_summary"})
    assert not (tmp_path / "narrative_memory.jsonl").exists()


def test_log_combat_round_does_not_write_disk(tmp_path: Path) -> None:
    """log_combat_round() is ephemeral — no file written."""
    repo = MemoryRepository(str(tmp_path), state_repo=MagicMock())
    repo.log_combat_round("Talia strikes the goblin.")
    assert not (tmp_path / "combat_log.jsonl").exists()


# ---------------------------------------------------------------------------
# persist()
# ---------------------------------------------------------------------------


class TestPersist:
    def test_persist_saves_game_state_via_state_repo(self, tmp_path: Path) -> None:
        """persist() flushes staged game_state to state_repo.save()."""
        state_repo = MagicMock()
        repo = MemoryRepository(tmp_path, state_repo=state_repo)
        gs = MagicMock()
        repo.update_game_state(gs)
        repo.persist()
        state_repo.save.assert_called_once_with(gs)

    def test_persist_skips_state_repo_when_no_game_state(self, tmp_path: Path) -> None:
        """persist() must not call state_repo.save() when game_state was never updated."""
        state_repo = MagicMock()
        repo = MemoryRepository(tmp_path, state_repo=state_repo)
        repo.persist()
        state_repo.save.assert_not_called()

    def test_persist_stores_staged_narrations(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """persist() must call store_narrative for each staged narration."""
        expected_calls = [
            ("Hello world", {"source": "narrator"}),
            ("Second narration", {"source": "narrator"}),
        ]
        repo = MemoryRepository(tmp_path, state_repo=MagicMock())
        calls: list[tuple[str, dict[str, str]]] = []
        monkeypatch.setattr(
            repo, "store_narrative", lambda text, meta: calls.append((text, meta))
        )
        repo.stage_narration("Hello world", {"source": "narrator"})
        repo.stage_narration("Second narration", {"source": "narrator"})
        repo.persist()
        assert calls == expected_calls
        # Second persist should not re-flush (cache was reset)
        repo.persist()
        assert len(calls) == len(expected_calls)

    def test_persist_writes_exchange_buffer_to_disk(self, tmp_path: Path) -> None:
        """persist() must write exchange_buffer to exchange_buffer.json."""
        repo = MemoryRepository(tmp_path, state_repo=MagicMock())
        repo.update_exchange("player says hi", "narrator replies")
        repo.persist()
        exchange_path = tmp_path / "exchange_buffer.json"
        assert exchange_path.exists()
        data = json.loads(exchange_path.read_text(encoding="utf-8"))
        assert data == ["player says hi", "narrator replies"]

    def test_persist_resets_cache_except_exchange_buffer(self, tmp_path: Path) -> None:
        """After persist(), game_state and staged_narrations are cleared; exchange_buffer persists."""
        state_repo = MagicMock()
        repo = MemoryRepository(tmp_path, state_repo=state_repo)
        gs = MagicMock()
        repo.update_game_state(gs)
        repo.stage_narration("text", {"source": "narrator"})
        repo.update_exchange("p", "n")
        repo.persist()
        # Calling persist again must not re-save game_state
        repo.persist()
        assert state_repo.save.call_count == 1
        # Exchange buffer survives reset
        assert repo.get_exchange_buffer() == ("p", "n")


# ---------------------------------------------------------------------------
# clear_combat_memory() / clear_encounter_memory()
# ---------------------------------------------------------------------------


class TestClearCombatMemory:
    def test_clear_combat_memory_removes_combat_round_logs(
        self, tmp_path: Path
    ) -> None:
        """clear_combat_memory() must clear combat_round_logs while preserving other cache fields."""
        state_repo = MagicMock()
        repo = MemoryRepository(tmp_path, state_repo=state_repo)
        gs = MagicMock()
        repo.update_game_state(gs)
        repo.log_combat_round("round 1")
        repo.update_exchange("a", "b")
        repo.clear_combat_memory()
        # Exchange buffer must be unaffected
        assert repo.get_exchange_buffer() == ("a", "b")
        # game_state must be unaffected — persist should still save it
        repo.persist()
        state_repo.save.assert_called_once_with(gs)
        # Calling clear_combat_memory() again on an already-cleared cache must be idempotent
        repo.log_combat_round("new round")
        repo.clear_combat_memory()
        repo.persist()
        # game_state was reset by previous persist(), so save should not be called again
        assert state_repo.save.call_count == 1


class TestClearEncounterMemory:
    def test_clear_encounter_memory_resets_cache_except_exchange_buffer(
        self, tmp_path: Path
    ) -> None:
        """clear_encounter_memory() must reset game_state, staged_narrations, combat_round_logs
        while preserving exchange_buffer."""
        state_repo = MagicMock()
        repo = MemoryRepository(tmp_path, state_repo=state_repo)
        gs = MagicMock()
        repo.update_game_state(gs)
        repo.stage_narration("text", {"source": "narrator"})
        repo.log_combat_round("round 1")
        repo.update_exchange("p", "n")
        repo.clear_encounter_memory()
        # Exchange buffer preserved
        assert repo.get_exchange_buffer() == ("p", "n")
        # Game state cleared — persist() should not call save
        repo.persist()
        state_repo.save.assert_not_called()


# ---------------------------------------------------------------------------
# _restore_exchange_buffer()
# ---------------------------------------------------------------------------


class TestRestoreExchangeBuffer:
    def test_restore_reads_exchange_buffer_from_disk_on_init(
        self, tmp_path: Path
    ) -> None:
        """MemoryRepository reads existing exchange_buffer.json on __init__."""
        exchange_path = tmp_path / "exchange_buffer.json"
        exchange_path.write_text(
            json.dumps(["prior player input", "prior narrator output"]),
            encoding="utf-8",
        )
        repo = MemoryRepository(tmp_path, state_repo=MagicMock())
        assert repo.get_exchange_buffer() == (
            "prior player input",
            "prior narrator output",
        )

    def test_restore_ignores_missing_exchange_buffer_file(self, tmp_path: Path) -> None:
        """MemoryRepository starts with empty exchange_buffer if file does not exist."""
        repo = MemoryRepository(tmp_path, state_repo=MagicMock())
        assert repo.get_exchange_buffer() == ()

    def test_restore_ignores_corrupt_exchange_buffer_file(self, tmp_path: Path) -> None:
        """MemoryRepository starts with empty exchange_buffer if file is corrupt."""
        exchange_path = tmp_path / "exchange_buffer.json"
        exchange_path.write_text("not valid json", encoding="utf-8")
        repo = MemoryRepository(tmp_path, state_repo=MagicMock())
        assert repo.get_exchange_buffer() == ()
