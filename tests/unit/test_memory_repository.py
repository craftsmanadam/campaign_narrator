"""Unit tests for the memory repository."""

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
