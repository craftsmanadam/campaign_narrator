"""Verification for the persisted data contract baseline."""

import json
from pathlib import Path


def test_data_contract_files_exist() -> None:
    """Core schema and docs artifacts should exist."""

    required_paths = [
        Path("data/metadata/enums.json"),
        Path("data/schema/campaign.schema.json"),
        Path("data/compendium/monsters/aberrations.json"),
        Path("data/compendium/monsters/beasts.json"),
        Path("data/compendium/monsters/celestials.json"),
        Path("data/compendium/monsters/constructs.json"),
        Path("data/compendium/monsters/dragons.json"),
        Path("data/compendium/monsters/elementals.json"),
        Path("data/compendium/monsters/fey.json"),
        Path("data/compendium/monsters/fiends.json"),
        Path("data/compendium/monsters/giants.json"),
        Path("data/compendium/monsters/humanoids.json"),
        Path("data/compendium/monsters/monstrosities.json"),
        Path("data/compendium/monsters/oozes.json"),
        Path("data/compendium/monsters/plants.json"),
        Path("data/compendium/monsters/undead.json"),
        Path("data/compendium/magic_items/common.json"),
        Path("data/compendium/magic_items/uncommon.json"),
        Path("data/compendium/magic_items/rare.json"),
        Path("data/compendium/spells/level_0.json"),
        Path("data/compendium/spells/level_1.json"),
        Path("data/compendium/spells/level_2.json"),
        Path("data/compendium/spells/level_3.json"),
        Path("data/rules/source/creation/character_creation_overview.md"),
        Path("data/rules/source/creation/ability_scores.md"),
        Path("data/rules/source/creation/species.md"),
        Path("data/rules/source/creation/origins.md"),
        Path("data/rules/source/creation/feats.md"),
        Path("data/rules/source/creation/equipment_starting.md"),
        Path("data/rules/source/creation/classes/barbarian.md"),
        Path("data/rules/source/creation/classes/bard.md"),
        Path("data/rules/source/creation/classes/cleric.md"),
        Path("data/rules/source/creation/classes/druid.md"),
        Path("data/rules/source/creation/classes/fighter.md"),
        Path("data/rules/source/creation/classes/monk.md"),
        Path("data/rules/source/creation/classes/paladin.md"),
        Path("data/rules/source/creation/classes/ranger.md"),
        Path("data/rules/source/creation/classes/rogue.md"),
        Path("data/rules/source/creation/classes/sorcerer.md"),
        Path("data/rules/source/creation/classes/warlock.md"),
        Path("data/rules/source/creation/classes/wizard.md"),
        Path("data/rules/source/adjudication/core_resolution.md"),
        Path("data/rules/source/adjudication/ability_checks.md"),
        Path("data/rules/source/adjudication/advantage_disadvantage.md"),
        Path("data/rules/source/adjudication/combat_flow.md"),
        Path("data/rules/source/adjudication/combat_actions.md"),
        Path("data/rules/source/adjudication/damage_healing.md"),
        Path("data/rules/source/adjudication/death_dying.md"),
        Path("data/rules/source/adjudication/spellcasting_basics.md"),
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
            "monster_types",
            "item_rarities",
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
        Path("data/compendium/monsters/aberrations.json"): {"monsters"},
        Path("data/compendium/monsters/beasts.json"): {"monsters"},
        Path("data/compendium/monsters/celestials.json"): {"monsters"},
        Path("data/compendium/monsters/constructs.json"): {"monsters"},
        Path("data/compendium/monsters/dragons.json"): {"monsters"},
        Path("data/compendium/monsters/elementals.json"): {"monsters"},
        Path("data/compendium/monsters/fey.json"): {"monsters"},
        Path("data/compendium/monsters/fiends.json"): {"monsters"},
        Path("data/compendium/monsters/giants.json"): {"monsters"},
        Path("data/compendium/monsters/humanoids.json"): {"monsters"},
        Path("data/compendium/monsters/monstrosities.json"): {"monsters"},
        Path("data/compendium/monsters/oozes.json"): {"monsters"},
        Path("data/compendium/monsters/plants.json"): {"monsters"},
        Path("data/compendium/monsters/undead.json"): {"monsters"},
        Path("data/compendium/magic_items/common.json"): {"magic_items"},
        Path("data/compendium/magic_items/uncommon.json"): {"magic_items"},
        Path("data/compendium/magic_items/rare.json"): {"magic_items"},
        Path("data/compendium/spells/level_0.json"): {"spells"},
        Path("data/compendium/spells/level_1.json"): {"spells"},
        Path("data/compendium/spells/level_2.json"): {"spells"},
        Path("data/compendium/spells/level_3.json"): {"spells"},
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


def test_live_compendium_files_match_their_wrappers() -> None:
    """Live compendium files should keep stable wrapper objects after ingestion."""

    monster_paths = [
        Path("data/compendium/monsters/aberrations.json"),
        Path("data/compendium/monsters/beasts.json"),
        Path("data/compendium/monsters/celestials.json"),
        Path("data/compendium/monsters/constructs.json"),
        Path("data/compendium/monsters/dragons.json"),
        Path("data/compendium/monsters/elementals.json"),
        Path("data/compendium/monsters/fey.json"),
        Path("data/compendium/monsters/fiends.json"),
        Path("data/compendium/monsters/giants.json"),
        Path("data/compendium/monsters/humanoids.json"),
        Path("data/compendium/monsters/monstrosities.json"),
        Path("data/compendium/monsters/oozes.json"),
        Path("data/compendium/monsters/plants.json"),
        Path("data/compendium/monsters/undead.json"),
    ]
    item_paths = [
        Path("data/compendium/magic_items/common.json"),
        Path("data/compendium/magic_items/uncommon.json"),
        Path("data/compendium/magic_items/rare.json"),
    ]
    spell_paths = [
        Path("data/compendium/spells/level_0.json"),
        Path("data/compendium/spells/level_1.json"),
        Path("data/compendium/spells/level_2.json"),
        Path("data/compendium/spells/level_3.json"),
    ]

    for path in monster_paths:
        parsed = json.loads(path.read_text())
        assert isinstance(parsed["monsters"], list)

    for path in item_paths:
        parsed = json.loads(path.read_text())
        assert isinstance(parsed["magic_items"], list)

    for path in spell_paths:
        parsed = json.loads(path.read_text())
        assert isinstance(parsed["spells"], list)


def test_first_ingested_corpus_content_exists() -> None:
    """The first SRD ingestion pass should load representative live corpus content."""

    aberrations = json.loads(
        Path("data/compendium/monsters/aberrations.json").read_text()
    )
    celestials = json.loads(
        Path("data/compendium/monsters/celestials.json").read_text()
    )
    dragons = json.loads(Path("data/compendium/monsters/dragons.json").read_text())
    common_items = json.loads(
        Path("data/compendium/magic_items/common.json").read_text()
    )
    uncommon_items = json.loads(
        Path("data/compendium/magic_items/uncommon.json").read_text()
    )
    rare_items = json.loads(Path("data/compendium/magic_items/rare.json").read_text())
    cantrips = json.loads(Path("data/compendium/spells/level_0.json").read_text())
    level_one_spells = json.loads(
        Path("data/compendium/spells/level_1.json").read_text()
    )
    level_two_spells = json.loads(
        Path("data/compendium/spells/level_2.json").read_text()
    )
    level_three_spells = json.loads(
        Path("data/compendium/spells/level_3.json").read_text()
    )

    assert any(
        monster["monster_id"] == "aboleth" for monster in aberrations["monsters"]
    )
    assert any(monster["monster_id"] == "couatl" for monster in celestials["monsters"])
    assert any(
        monster["monster_id"] == "copper-dragon-wyrmling"
        for monster in dragons["monsters"]
    )
    assert any(
        item["item_id"] == "potion-of-healing" for item in common_items["magic_items"]
    )
    assert any(
        item["item_id"] == "elemental-gem" for item in uncommon_items["magic_items"]
    )
    assert any(
        item["item_id"] == "elixir-of-health" for item in rare_items["magic_items"]
    )
    assert any(spell["spell_id"] == "light" for spell in cantrips["spells"])
    assert any(
        spell["spell_id"] == "magic-missile" for spell in level_one_spells["spells"]
    )
    assert any(
        spell["spell_id"] == "misty-step" for spell in level_two_spells["spells"]
    )
    assert any(
        spell["spell_id"] == "fireball" for spell in level_three_spells["spells"]
    )


def test_rule_source_files_are_nonempty() -> None:
    """First-cut rule source files should contain ingested prose rather than stubs."""

    minimum_rule_length = 40

    rule_paths = [
        Path("data/rules/source/creation/character_creation_overview.md"),
        Path("data/rules/source/creation/ability_scores.md"),
        Path("data/rules/source/creation/species.md"),
        Path("data/rules/source/creation/origins.md"),
        Path("data/rules/source/creation/feats.md"),
        Path("data/rules/source/creation/equipment_starting.md"),
        Path("data/rules/source/creation/classes/barbarian.md"),
        Path("data/rules/source/creation/classes/bard.md"),
        Path("data/rules/source/creation/classes/cleric.md"),
        Path("data/rules/source/creation/classes/druid.md"),
        Path("data/rules/source/creation/classes/fighter.md"),
        Path("data/rules/source/creation/classes/monk.md"),
        Path("data/rules/source/creation/classes/paladin.md"),
        Path("data/rules/source/creation/classes/ranger.md"),
        Path("data/rules/source/creation/classes/rogue.md"),
        Path("data/rules/source/creation/classes/sorcerer.md"),
        Path("data/rules/source/creation/classes/warlock.md"),
        Path("data/rules/source/creation/classes/wizard.md"),
        Path("data/rules/source/adjudication/core_resolution.md"),
        Path("data/rules/source/adjudication/ability_checks.md"),
        Path("data/rules/source/adjudication/advantage_disadvantage.md"),
        Path("data/rules/source/adjudication/combat_flow.md"),
        Path("data/rules/source/adjudication/combat_actions.md"),
        Path("data/rules/source/adjudication/damage_healing.md"),
        Path("data/rules/source/adjudication/death_dying.md"),
        Path("data/rules/source/adjudication/spellcasting_basics.md"),
    ]

    for path in rule_paths:
        assert len(path.read_text().strip()) > minimum_rule_length, path


def test_example_fixture_content_exists_for_reference_data() -> None:
    """Acceptance fixtures should contain concrete example content."""

    fixture_root = Path("tests/acceptance/fixtures/examples")
    assert (fixture_root / "narrative/campaign.json").exists()
    assert (fixture_root / "state/world_state.json").exists()
    assert (fixture_root / "memory/session_summaries.jsonl").exists()
    assert (fixture_root / "compendium/monsters/dragons.json").exists()
    assert (fixture_root / "compendium/magic_items/rare.json").exists()
    assert (fixture_root / "compendium/spells/level_3.json").exists()


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
