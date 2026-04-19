"""Unit tests for the memory repository."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from campaignnarrator.repositories.memory_repository import MemoryRepository


def test_memory_repository_appends_and_loads_event_log(tmp_path: Path) -> None:
    """The repository should persist events in newline-delimited JSON."""

    memory_root = tmp_path / "memory"
    memory_root.mkdir(parents=True)
    (memory_root / "event_log.jsonl").write_text(
        '{"event_id": "evt-001", "type": "seed"}\n'
    )

    repository = MemoryRepository(memory_root)

    repository.append_event({"event_id": "evt-002", "type": "state_updated"})

    assert repository.load_event_log() == [
        {"event_id": "evt-001", "type": "seed"},
        {"event_id": "evt-002", "type": "state_updated"},
    ]


def _make_repo(tmp: str) -> MemoryRepository:
    return MemoryRepository(tmp)


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


def test_retrieve_relevant_returns_matching_text() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(tmp)
        repo.store_narrative(
            "Aldric saw Malachar at the docks.",
            {"event_type": "encounter_summary"},
        )
        repo.store_narrative(
            "The barmaid served ale.",
            {"event_type": "encounter_summary"},
        )
        results = repo.retrieve_relevant("Malachar")
        assert len(results) == 1
        assert "Malachar" in results[0]


def test_retrieve_relevant_is_case_insensitive() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(tmp)
        repo.store_narrative(
            "The fog-shrouded DOCKS loomed ahead.",
            {"event_type": "encounter_summary"},
        )
        results = repo.retrieve_relevant("docks")
        assert len(results) == 1


def test_retrieve_relevant_respects_limit() -> None:
    entry_count = 10
    result_limit = 3
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(tmp)
        for i in range(entry_count):
            repo.store_narrative(
                f"Entry {i} mentions docks.",
                {"event_type": "encounter_summary"},
            )
        results = repo.retrieve_relevant("docks", limit=result_limit)
        assert len(results) == result_limit


def test_retrieve_relevant_empty_store_returns_empty_list() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(tmp)
        results = repo.retrieve_relevant("anything")
        assert results == []


def test_retrieve_relevant_no_match_returns_empty_list() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(tmp)
        repo.store_narrative(
            "A goblin lurked near the bridge.",
            {"event_type": "encounter_summary"},
        )
        results = repo.retrieve_relevant("dragon")
        assert results == []
