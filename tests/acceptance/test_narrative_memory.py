"""Acceptance coverage for narrative memory persistence and retrieval."""

from __future__ import annotations

import json
from pathlib import Path

from pytest_bdd import given, parsers, scenario, then


@scenario(
    "features/narrative_memory.feature",
    "Each narration event during an encounter is recorded to narrative memory as it happens",
)
def test_narration_recorded_during_encounter() -> None:
    """Narration events are stored to narrative_memory.jsonl during a completed encounter."""


@scenario(
    "features/narrative_memory.feature",
    "Abandoning an unresolved encounter stores a generated summary so the next session has context",
)
def test_partial_summary_stored_on_save_and_quit() -> None:
    """save-and-quit stores a partial encounter summary for the next session."""


@scenario(
    "features/narrative_memory.feature",
    "Scene opening narration reflects a prior NPC description retrieved from memory",
)
def test_scene_opening_uses_prior_npc_memory() -> None:
    """Prior NPC description in memory influences scene opening narration."""


def _read_narrative_memory(runtime_data_root: Path) -> list[dict[str, object]]:
    path = runtime_data_root / "memory" / "narrative_memory.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


@given(
    "the narrative memory contains a prior encounter record:",
    target_fixture="narrative_memory_seeded",
)
def seed_prior_encounter_record(
    runtime_data_root: Path,
    docstring: str,
) -> None:
    """Write a prior narrative record into the runtime data root before the CLI runs."""
    memory_dir = runtime_data_root / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "text": docstring.strip(),
        "metadata": {
            "event_type": "narration",
            "encounter_id": "goblin-camp-prior",
            "campaign_id": "",
            "module_id": "",
        },
    }
    path = memory_dir / "narrative_memory.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")


@then(
    parsers.parse(
        "the narrative memory contains at least {count:d} narration entries"
        ' for encounter "{encounter_id}"'
    )
)
def narrative_memory_has_narration_entries(
    runtime_data_root: Path,
    count: int,
    encounter_id: str,
) -> None:
    """narrative_memory.jsonl must contain at least count narration records for the encounter."""
    records = _read_narrative_memory(runtime_data_root)
    matching = [
        r
        for r in records
        if r.get("metadata", {}).get("event_type") == "narration"
        and r.get("metadata", {}).get("encounter_id") == encounter_id
    ]
    assert len(matching) >= count, (
        f"Expected at least {count} narration entries for {encounter_id!r}, "
        f"found {len(matching)}. Records: {records}"
    )


@then(
    parsers.parse(
        "the narrative memory contains a partial summary entry"
        ' for encounter "{encounter_id}"'
    )
)
def narrative_memory_has_partial_summary(
    runtime_data_root: Path,
    encounter_id: str,
) -> None:
    """narrative_memory.jsonl must contain an encounter_partial_summary record."""
    records = _read_narrative_memory(runtime_data_root)
    matching = [
        r
        for r in records
        if r.get("metadata", {}).get("event_type") == "encounter_partial_summary"
        and r.get("metadata", {}).get("encounter_id") == encounter_id
    ]
    assert matching, (
        f"No partial summary entry found for {encounter_id!r}. Records: {records}"
    )
