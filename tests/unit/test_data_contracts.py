"""Verification for the persisted data contract baseline."""

import json
from pathlib import Path


def test_data_contract_files_exist() -> None:
    """Core schema and docs artifacts should exist."""

    required_paths = [
        Path("data/metadata/enums.json"),
        Path("data/schema/campaign.schema.json"),
        Path("docs/data-structures.md"),
    ]

    assert all(path.exists() for path in required_paths)


def test_json_contract_files_are_parseable_and_have_expected_top_level_keys() -> None:
    """Starter JSON files should parse and expose stable top-level contracts."""

    expected_keys = {
        Path("data/metadata/enums.json"): {
            "event_types",
            "npc_statuses",
            "quest_statuses",
        },
        Path("data/narrative/campaign.json"): {
            "campaign_id",
            "starting_location_id",
            "starting_quest_id",
        },
        Path("data/narrative/npcs.json"): {"npcs"},
        Path("data/narrative/locations.json"): {"locations"},
        Path("data/narrative/quests.json"): {"quests"},
        Path("data/state/world_state.json"): {
            "current_session",
            "quest_progress",
            "flags",
        },
        Path("data/state/campaign_state.json"): {
            "npc_relationships",
            "campaign_flags",
            "discovered_secrets",
        },
        Path("data/scenarios/test_scenarios.json"): {"scenarios"},
    }

    for path, required_keys in expected_keys.items():
        parsed = json.loads(path.read_text())
        assert required_keys.issubset(parsed.keys()), path


def test_data_files_are_neutral_and_example_content_lives_in_fixtures() -> None:
    """Starter data should stay neutral while examples live in fixtures."""

    campaign = json.loads(Path("data/narrative/campaign.json").read_text())
    npcs = json.loads(Path("data/narrative/npcs.json").read_text())
    locations = json.loads(Path("data/narrative/locations.json").read_text())
    quests = json.loads(Path("data/narrative/quests.json").read_text())
    factions = json.loads(Path("data/narrative/factions.json").read_text())
    player_character = json.loads(Path("data/state/player_character.json").read_text())
    world_state = json.loads(Path("data/state/world_state.json").read_text())
    campaign_state = json.loads(Path("data/state/campaign_state.json").read_text())
    scenarios = json.loads(Path("data/scenarios/test_scenarios.json").read_text())

    assert campaign["campaign_id"] == ""
    assert campaign["name"] == ""
    assert campaign["npc_ids"] == []
    assert npcs["npcs"] == []
    assert locations["locations"] == []
    assert quests["quests"] == []
    assert factions["factions"] == []
    assert player_character["character_id"] == ""
    assert player_character["inventory"] == []
    assert world_state["active_quest_ids"] == []
    assert campaign_state["npc_relationships"] == {}
    assert scenarios["scenarios"] == []

    fixture_root = Path("tests/acceptance/fixtures/examples")
    assert (fixture_root / "narrative/campaign.json").exists()
    assert (fixture_root / "state/world_state.json").exists()
    assert (fixture_root / "memory/session_summaries.jsonl").exists()


def test_schema_files_are_parseable_json() -> None:
    """JSON Schema files should at least be valid JSON documents."""

    schema_paths = sorted(Path("data/schema").glob("*.json"))

    assert schema_paths
    for path in schema_paths:
        parsed = json.loads(path.read_text())
        assert "$schema" in parsed, path
        assert "title" in parsed, path


def test_jsonl_memory_files_contain_one_json_object_per_line() -> None:
    """Memory files should remain structured JSONL rather than freeform text."""

    jsonl_paths = [
        Path("data/memory/session_summaries.jsonl"),
        Path("data/memory/event_log.jsonl"),
    ]

    for path in jsonl_paths:
        lines = [line for line in path.read_text().splitlines() if line.strip()]
        for line in lines:
            parsed = json.loads(line)
            assert isinstance(parsed, dict), path
