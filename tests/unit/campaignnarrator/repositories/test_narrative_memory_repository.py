"""Unit tests for NarrativeMemoryRepository."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import lancedb
import pytest
from campaignnarrator.adapters.embedding_adapter import StubEmbeddingAdapter
from campaignnarrator.repositories.narrative_memory_repository import (
    NarrativeMemoryRepository,
)


def _make_repo(tmp: str) -> NarrativeMemoryRepository:
    return NarrativeMemoryRepository(tmp)


def _make_lancedb_repo(tmp: str) -> NarrativeMemoryRepository:
    adapter = StubEmbeddingAdapter()
    lancedb_path = Path(tmp) / "lancedb"
    return NarrativeMemoryRepository(
        tmp,
        embedding_adapter=adapter,
        lancedb_path=lancedb_path,
    )


# ---------------------------------------------------------------------------
# store_narrative / retrieve_relevant
# ---------------------------------------------------------------------------


def test_store_narrative_creates_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(tmp)
        repo.store_narrative(
            "The docks reeked of salt and death.",
            {"event_type": "encounter_summary", "campaign_id": "c-1"},
        )
        assert (Path(tmp) / "narrative_memory.jsonl").exists()


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
        line = (Path(tmp) / "narrative_memory.jsonl").read_text().strip()
        record = json.loads(line)
        assert record["text"] == "Aldric confronted a robed figure."
        assert record["metadata"]["event_type"] == "encounter_summary"
        assert record["metadata"]["encounter_id"] == "module-001-enc-001"


def test_store_narrative_appends_multiple_records() -> None:
    expected_count = 2
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(tmp)
        repo.store_narrative("First.", {"event_type": "encounter_summary"})
        repo.store_narrative("Second.", {"event_type": "encounter_summary"})
        lines = [
            ln
            for ln in (Path(tmp) / "narrative_memory.jsonl").read_text().splitlines()
            if ln.strip()
        ]
        assert len(lines) == expected_count


# ---------------------------------------------------------------------------
# LanceDB mode
# ---------------------------------------------------------------------------


def test_lancedb_mode_creates_lancedb_directory(tmp_path: Path) -> None:
    _make_lancedb_repo(str(tmp_path))
    assert (tmp_path / "lancedb").exists()


def test_lancedb_mode_creates_narrative_memory_table(tmp_path: Path) -> None:
    _make_lancedb_repo(str(tmp_path))
    db = lancedb.connect(str(tmp_path / "lancedb"))
    assert "narrative_memory" in db.list_tables().tables


def test_lancedb_mode_table_starts_empty(tmp_path: Path) -> None:
    _make_lancedb_repo(str(tmp_path))
    db = lancedb.connect(str(tmp_path / "lancedb"))
    assert db.open_table("narrative_memory").count_rows() == 0


def test_lancedb_mode_opens_existing_table_on_reconnect(tmp_path: Path) -> None:
    _make_lancedb_repo(str(tmp_path))
    _make_lancedb_repo(str(tmp_path))
    db = lancedb.connect(str(tmp_path / "lancedb"))
    assert "narrative_memory" in db.list_tables().tables


def test_no_adapter_does_not_create_lancedb_directory(tmp_path: Path) -> None:
    NarrativeMemoryRepository(str(tmp_path))
    assert not (tmp_path / "lancedb").exists()


def test_store_narrative_lancedb_inserts_record(tmp_path: Path) -> None:
    repo = _make_lancedb_repo(str(tmp_path))
    repo.store_narrative(
        "Malachar stood at the docks.",
        {"event_type": "encounter_summary", "campaign_id": "c-1"},
    )
    db = lancedb.connect(str(tmp_path / "lancedb"))
    assert db.open_table("narrative_memory").count_rows() == 1


def test_store_narrative_lancedb_also_writes_jsonl_audit_log(tmp_path: Path) -> None:
    repo = _make_lancedb_repo(str(tmp_path))
    repo.store_narrative(
        "Malachar stood at the docks.",
        {"event_type": "encounter_summary", "campaign_id": "c-1"},
    )
    record = json.loads((tmp_path / "narrative_memory.jsonl").read_text().strip())
    assert record["text"] == "Malachar stood at the docks."


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
    results = repo.retrieve_relevant("Malachar", campaign_id="c-1")
    assert len(results) >= 1
    assert any("Malachar" in r for r in results)


def test_retrieve_relevant_lancedb_returns_plain_strings(tmp_path: Path) -> None:
    repo = _make_lancedb_repo(str(tmp_path))
    repo.store_narrative(
        "Malachar stood at the docks.",
        {"event_type": "encounter_summary", "campaign_id": "c-1"},
    )
    results = repo.retrieve_relevant("Malachar", campaign_id="c-1")
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
    results = repo.retrieve_relevant("docks", campaign_id="c-1", limit=result_limit)
    assert len(results) <= result_limit


def test_retrieve_relevant_lancedb_empty_store_returns_empty(tmp_path: Path) -> None:
    repo = _make_lancedb_repo(str(tmp_path))
    assert repo.retrieve_relevant("anything", campaign_id="c-1") == []


def test_retrieve_relevant_lancedb_filters_by_campaign_id(tmp_path: Path) -> None:
    repo = _make_lancedb_repo(str(tmp_path))
    repo.store_narrative(
        "Aldric fought goblins.",
        {"event_type": "encounter_summary", "campaign_id": "camp-A"},
    )
    repo.store_narrative(
        "Elara sang at the tavern.",
        {"event_type": "encounter_summary", "campaign_id": "camp-B"},
    )
    results = repo.retrieve_relevant("Aldric", campaign_id="camp-A")
    assert all("Elara" not in r for r in results)


# ---------------------------------------------------------------------------
# JSONL migration
# ---------------------------------------------------------------------------

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
    (tmp_path / "narrative_memory.jsonl").write_text(_MALACHAR_JSONL)
    _make_lancedb_repo(str(tmp_path))
    db = lancedb.connect(str(tmp_path / "lancedb"))
    assert db.open_table("narrative_memory").count_rows() == 1


def test_migration_skipped_when_table_already_has_rows(tmp_path: Path) -> None:
    narrative_path = tmp_path / "narrative_memory.jsonl"
    narrative_path.write_text(_FIRST_ENTRY_JSONL)
    _make_lancedb_repo(str(tmp_path))
    with narrative_path.open("a") as f:
        f.write(_SECOND_ENTRY_JSONL)
    _make_lancedb_repo(str(tmp_path))
    db = lancedb.connect(str(tmp_path / "lancedb"))
    assert db.open_table("narrative_memory").count_rows() == 1


def test_migration_skipped_when_no_jsonl_file(tmp_path: Path) -> None:
    _make_lancedb_repo(str(tmp_path))
    db = lancedb.connect(str(tmp_path / "lancedb"))
    assert db.open_table("narrative_memory").count_rows() == 0


def test_migration_migrated_records_are_retrievable(tmp_path: Path) -> None:
    (tmp_path / "narrative_memory.jsonl").write_text(_MALACHAR_JSONL)
    repo = _make_lancedb_repo(str(tmp_path))
    results = repo.retrieve_relevant("Malachar", campaign_id="c-1")
    assert len(results) >= 1
    assert any("Malachar" in r for r in results)


# ---------------------------------------------------------------------------
# clear_narrative
# ---------------------------------------------------------------------------


def test_clear_narrative_removes_lancedb_entries(tmp_path: Path) -> None:
    repo = _make_lancedb_repo(str(tmp_path))
    repo.store_narrative(
        "Aldric fought goblins.",
        {"event_type": "encounter_summary", "campaign_id": "camp-A"},
    )
    repo.store_narrative(
        "Elara sang at the tavern.",
        {"event_type": "encounter_summary", "campaign_id": "camp-B"},
    )
    repo.clear_narrative("camp-A")
    assert repo.retrieve_relevant("Aldric", campaign_id="camp-A") == []


def test_clear_narrative_preserves_other_campaign_entries(tmp_path: Path) -> None:
    repo = _make_lancedb_repo(str(tmp_path))
    repo.store_narrative(
        "Aldric fought goblins.",
        {"event_type": "encounter_summary", "campaign_id": "camp-A"},
    )
    repo.store_narrative(
        "Elara sang at the tavern.",
        {"event_type": "encounter_summary", "campaign_id": "camp-B"},
    )
    repo.clear_narrative("camp-A")
    results = repo.retrieve_relevant("Elara", campaign_id="camp-B")
    assert len(results) > 0


def test_clear_narrative_removes_jsonl_entries(tmp_path: Path) -> None:
    repo = _make_repo(str(tmp_path))
    repo.store_narrative(
        "Aldric.", {"event_type": "encounter_summary", "campaign_id": "camp-A"}
    )
    repo.store_narrative(
        "Elara.", {"event_type": "encounter_summary", "campaign_id": "camp-B"}
    )
    repo.clear_narrative("camp-A")
    lines = [
        json.loads(ln)
        for ln in (tmp_path / "narrative_memory.jsonl").read_text().splitlines()
        if ln.strip()
    ]
    assert all(ln["metadata"]["campaign_id"] != "camp-A" for ln in lines)
    assert any(ln["metadata"]["campaign_id"] == "camp-B" for ln in lines)


# ---------------------------------------------------------------------------
# Exchange buffer
# ---------------------------------------------------------------------------


def test_update_exchange_appends_two_items(tmp_path: Path) -> None:
    repo = NarrativeMemoryRepository(str(tmp_path))
    repo.update_exchange("Hello", "Welcome to the docks.")
    assert repo.get_exchange_buffer() == ("Hello", "Welcome to the docks.")


def test_update_exchange_caps_at_max_exchanges(tmp_path: Path) -> None:
    call_count = 6
    expected_buffer_size = 10
    repo = NarrativeMemoryRepository(str(tmp_path))
    for i in range(call_count):
        repo.update_exchange(f"in{i}", f"out{i}")
    buf = repo.get_exchange_buffer()
    assert len(buf) == expected_buffer_size
    assert buf[0] == "in1"


# ---------------------------------------------------------------------------
# stage_narration / log_combat_round
# ---------------------------------------------------------------------------


def test_stage_narration_does_not_write_disk(tmp_path: Path) -> None:
    repo = NarrativeMemoryRepository(str(tmp_path))
    repo.stage_narration("A summary.", {"event_type": "encounter_partial_summary"})
    assert not (tmp_path / "narrative_memory.jsonl").exists()


def test_log_combat_round_does_not_write_disk(tmp_path: Path) -> None:
    repo = NarrativeMemoryRepository(str(tmp_path))
    repo.log_combat_round("Talia strikes the goblin.")
    assert not (tmp_path / "combat_log.jsonl").exists()


# ---------------------------------------------------------------------------
# persist()
# ---------------------------------------------------------------------------


class TestPersist:
    def test_persist_stores_staged_narrations(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        expected_calls = [
            ("Hello world", {"source": "narrator"}),
            ("Second narration", {"source": "narrator"}),
        ]
        repo = NarrativeMemoryRepository(str(tmp_path))
        calls: list[tuple[str, dict[str, str]]] = []
        monkeypatch.setattr(
            repo, "store_narrative", lambda text, meta: calls.append((text, meta))
        )
        repo.stage_narration("Hello world", {"source": "narrator"})
        repo.stage_narration("Second narration", {"source": "narrator"})
        repo.persist()
        assert calls == expected_calls
        repo.persist()
        assert len(calls) == len(expected_calls)

    def test_persist_writes_exchange_buffer_to_disk(self, tmp_path: Path) -> None:
        repo = NarrativeMemoryRepository(str(tmp_path))
        repo.update_exchange("player says hi", "narrator replies")
        repo.persist()
        exchange_path = tmp_path / "exchange_buffer.json"
        assert exchange_path.exists()
        data = json.loads(exchange_path.read_text(encoding="utf-8"))
        assert data == ["player says hi", "narrator replies"]

    def test_persist_resets_staged_narrations_preserves_exchange_buffer(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = NarrativeMemoryRepository(str(tmp_path))
        calls: list[tuple[str, dict[str, str]]] = []
        monkeypatch.setattr(
            repo, "store_narrative", lambda text, meta: calls.append((text, meta))
        )
        repo.stage_narration("once", {"source": "narrator"})
        repo.update_exchange("p", "n")
        repo.persist()
        repo.persist()
        # staged narration flushed once only
        assert len(calls) == 1
        # exchange buffer survives
        assert repo.get_exchange_buffer() == ("p", "n")


# ---------------------------------------------------------------------------
# clear_combat_memory / clear_encounter_memory
# ---------------------------------------------------------------------------


class TestClearCombatMemory:
    def test_clear_combat_memory_clears_logs_preserves_exchange(
        self, tmp_path: Path
    ) -> None:
        repo = NarrativeMemoryRepository(str(tmp_path))
        repo.log_combat_round("round 1")
        repo.update_exchange("a", "b")
        repo.clear_combat_memory()
        assert repo.get_exchange_buffer() == ("a", "b")

    def test_clear_combat_memory_idempotent(self, tmp_path: Path) -> None:
        repo = NarrativeMemoryRepository(str(tmp_path))
        repo.log_combat_round("round 1")
        repo.clear_combat_memory()
        repo.clear_combat_memory()
        assert repo.get_exchange_buffer() == ()


class TestClearEncounterMemory:
    def test_clear_encounter_memory_resets_cache_except_exchange_buffer(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = NarrativeMemoryRepository(str(tmp_path))
        calls: list[tuple[str, dict[str, str]]] = []
        monkeypatch.setattr(
            repo, "store_narrative", lambda text, meta: calls.append((text, meta))
        )
        repo.stage_narration("text", {"source": "narrator"})
        repo.log_combat_round("round 1")
        repo.update_exchange("p", "n")
        repo.clear_encounter_memory()
        assert repo.get_exchange_buffer() == ("p", "n")
        repo.persist()
        assert calls == []


# ---------------------------------------------------------------------------
# _restore_exchange_buffer
# ---------------------------------------------------------------------------


class TestRestoreExchangeBuffer:
    def test_restore_reads_exchange_buffer_from_disk_on_init(
        self, tmp_path: Path
    ) -> None:
        exchange_path = tmp_path / "exchange_buffer.json"
        exchange_path.write_text(
            json.dumps(["prior player input", "prior narrator output"]),
            encoding="utf-8",
        )
        repo = NarrativeMemoryRepository(str(tmp_path))
        assert repo.get_exchange_buffer() == (
            "prior player input",
            "prior narrator output",
        )

    def test_restore_ignores_missing_exchange_buffer_file(self, tmp_path: Path) -> None:
        repo = NarrativeMemoryRepository(str(tmp_path))
        assert repo.get_exchange_buffer() == ()

    def test_restore_ignores_corrupt_exchange_buffer_file(self, tmp_path: Path) -> None:
        exchange_path = tmp_path / "exchange_buffer.json"
        exchange_path.write_text("not valid json", encoding="utf-8")
        repo = NarrativeMemoryRepository(str(tmp_path))
        assert repo.get_exchange_buffer() == ()
