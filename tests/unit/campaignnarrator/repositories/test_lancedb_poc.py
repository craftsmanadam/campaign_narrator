"""Proof-of-concept tests verifying LanceDB API behaviour on this Python version.

These tests exist to catch API mismatches before implementation begins.
If any test here fails, update the implementation plan to match the actual API
before writing any MemoryRepository LanceDB code.
"""

from __future__ import annotations

from pathlib import Path

import lancedb
import pyarrow as pa

_DIMS = 4  # small dimension for fast POC; production uses 768


def _schema(dims: int = _DIMS) -> pa.Schema:
    return pa.schema(
        [
            pa.field("id", pa.string()),
            pa.field("text", pa.string()),
            pa.field("event_type", pa.string()),
            pa.field("campaign_id", pa.string()),
            pa.field("module_id", pa.string()),
            pa.field("encounter_id", pa.string()),
            pa.field("timestamp", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), dims)),
        ]
    )


def _sample_record(text: str, vector: list[float]) -> dict:
    return {
        "id": "rec-001",
        "text": text,
        "event_type": "encounter_summary",
        "campaign_id": "c-1",
        "module_id": "m-1",
        "encounter_id": "e-1",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "vector": vector,
    }


def test_lancedb_connect_creates_directory(tmp_path: Path) -> None:
    """lancedb.connect() creates the target directory if absent."""
    db_path = tmp_path / "lancedb"
    assert not db_path.exists()
    lancedb.connect(str(db_path))
    assert db_path.exists()


def test_lancedb_create_table_with_schema(tmp_path: Path) -> None:
    """create_table() with an explicit PyArrow schema succeeds."""
    db = lancedb.connect(str(tmp_path / "lancedb"))
    table = db.create_table("narrative_memory", schema=_schema())
    assert "narrative_memory" in db.list_tables().tables
    assert table.count_rows() == 0


def test_lancedb_open_existing_table(tmp_path: Path) -> None:
    """open_table() reopens a previously created table."""
    db = lancedb.connect(str(tmp_path / "lancedb"))
    db.create_table("narrative_memory", schema=_schema())

    db2 = lancedb.connect(str(tmp_path / "lancedb"))
    table = db2.open_table("narrative_memory")
    assert table.count_rows() == 0


def test_lancedb_list_tables_lists_tables(tmp_path: Path) -> None:
    """list_tables() returns names of created tables."""
    db = lancedb.connect(str(tmp_path / "lancedb"))
    assert "narrative_memory" not in db.list_tables().tables
    db.create_table("narrative_memory", schema=_schema())
    assert "narrative_memory" in db.list_tables().tables


def test_lancedb_add_record(tmp_path: Path) -> None:
    """add() inserts a record and count_rows() reflects it."""
    db = lancedb.connect(str(tmp_path / "lancedb"))
    table = db.create_table("narrative_memory", schema=_schema())

    table.add([_sample_record("Malachar stood at the docks.", [0.1, 0.2, 0.3, 0.4])])

    assert table.count_rows() == 1


def test_lancedb_vector_search_returns_nearest(tmp_path: Path) -> None:
    """Vector search returns the nearest record by cosine similarity."""
    db = lancedb.connect(str(tmp_path / "lancedb"))
    table = db.create_table("narrative_memory", schema=_schema())
    table.add(
        [
            _sample_record("Malachar stood at the docks.", [1.0, 0.0, 0.0, 0.0]),
            _sample_record("The barmaid served ale.", [0.0, 1.0, 0.0, 0.0]),
        ]
    )

    results = table.search([1.0, 0.0, 0.0, 0.0]).limit(1).to_list()

    assert len(results) == 1
    assert results[0]["text"] == "Malachar stood at the docks."


def test_lancedb_fts_search_returns_keyword_match(tmp_path: Path) -> None:
    """FTS search returns records whose text contains the query keyword."""
    db = lancedb.connect(str(tmp_path / "lancedb"))
    table = db.create_table("narrative_memory", schema=_schema())
    table.add(
        [
            _sample_record("Malachar stood at the docks.", [1.0, 0.0, 0.0, 0.0]),
            _sample_record("The barmaid served ale.", [0.0, 1.0, 0.0, 0.0]),
        ]
    )
    table.create_fts_index("text")

    results = table.search("Malachar", query_type="fts").limit(5).to_list()

    assert len(results) == 1
    assert results[0]["text"] == "Malachar stood at the docks."


def test_lancedb_fts_index_created_after_add(tmp_path: Path) -> None:
    """FTS index created after records are already present still works."""
    db = lancedb.connect(str(tmp_path / "lancedb"))
    table = db.create_table("narrative_memory", schema=_schema())
    table.add([_sample_record("Malachar stood at the docks.", [1.0, 0.0, 0.0, 0.0])])
    table.create_fts_index("text")

    results = table.search("Malachar", query_type="fts").limit(5).to_list()
    assert len(results) == 1


def test_lancedb_result_contains_text_field(tmp_path: Path) -> None:
    """Search results contain the 'text' field needed by retrieve_relevant."""
    db = lancedb.connect(str(tmp_path / "lancedb"))
    table = db.create_table("narrative_memory", schema=_schema())
    vector = [0.5, 0.5, 0.0, 0.0]
    record = _sample_record("The fog-shrouded docks loomed ahead.", vector)
    table.add([record])

    results = table.search([0.5, 0.5, 0.0, 0.0]).limit(1).to_list()

    assert "text" in results[0]
    assert "id" in results[0]


def test_lancedb_result_text_is_plain_string(tmp_path: Path) -> None:
    """The 'text' field in search results is a plain Python string."""
    db = lancedb.connect(str(tmp_path / "lancedb"))
    table = db.create_table("narrative_memory", schema=_schema())
    vector = [0.1, 0.2, 0.3, 0.4]
    record = _sample_record("A pale figure emerged from the mist.", vector)
    table.add([record])

    results = table.search([0.1, 0.2, 0.3, 0.4]).limit(1).to_list()

    assert isinstance(results[0]["text"], str)
