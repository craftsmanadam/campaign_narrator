"""Verification for the persisted data contract baseline."""

import json
from pathlib import Path

MEDIUM_SPEED_FEET = 30
BARD_SKILL_CHOICES = 3
SUBCLASS_ENTRY_LEVEL = 3
WARLOCK_LEVEL_THREE_PACT_SLOTS = 2
WARLOCK_LEVEL_THREE_PACT_SLOT_LEVEL = 2
WARLOCK_LEVEL_THREE_INVOCATIONS = 3
WIZARD_STARTING_SPELLBOOK_SPELLS = 6
BARD_SHORT_REST_TEXT = "regain all your expended uses of Bardic Inspiration"
MONK_FOCUS_TEXT = "Your focus and martial training allow you to harness"
LIGHT_WEAPON_TEXT = "When you take the Attack action on your turn and attack"
ARMOR_TRAINING_TEXT = "If you wear Light, Medium, or Heavy armor and lack training"
ONE_SLOT_PER_TURN_TEXT = "On a turn, you can expend only one spell slot to cast a spell"
MATERIAL_HAND_TEXT = "hand free to access materials or a pouch"
CHARM_PERSON_TEXT = "The Charmed creature is Friendly to you"
COUNTERSPELL_TEXT = "the action, Bonus Action, or Reaction used to cast it is wasted"
FIREBALL_TEXT = (
    "Flammable objects in the area that aren't being worn or carried start burning"
)
SPIRIT_GUARDIANS_TEXT = "whenever the Emanation enters a creature's space"
WEB_TEXT = (
    "A Restrained creature can take an action to make a Strength (Athletics) check"
)
STARTER_SPELL_IDS = {
    "bane",
    "comprehend-languages",
    "hellish-rebuke",
    "hideous-laughter",
    "protection-from-evil-and-good",
    "speak-with-animals",
    "unseen-servant",
    "darkness",
    "enthrall",
    "mind-spike",
    "mirror-image",
    "ray-of-enfeeblement",
    "spider-climb",
    "find-familiar",
    "floating-disk",
    "silent-image",
    "detect-thoughts",
    "levitate",
    "locate-object",
    "magic-weapon",
    "phantasmal-force",
    "sleet-storm",
    "slow",
    "water-breathing",
    "chromatic-orb",
    "fireball",
    "magic-missile",
    "eldritch-blast",
}


def _spell_map(path: str) -> dict[str, dict]:
    """Load a spell compendium file keyed by spell ID."""

    spells = json.loads(Path(path).read_text())["spells"]
    return {spell["spell_id"]: spell for spell in spells}


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
        Path("data/compendium/equipment/weapons.json"),
        Path("data/compendium/equipment/armor.json"),
        Path("data/compendium/equipment/tools.json"),
        Path("data/compendium/equipment/adventuring_gear.json"),
        Path("data/compendium/character_options/species.json"),
        Path("data/compendium/character_options/origins.json"),
        Path("data/compendium/character_options/feats.json"),
        Path("data/compendium/character_options/classes.json"),
        Path("data/compendium/character_options/subclasses.json"),
        Path("data/compendium/character_options/class_progression.json"),
        Path("data/compendium/character_options/class_features.json"),
        Path("data/compendium/character_options/subclass_features.json"),
        Path("data/compendium/character_options/invocations.json"),
        Path("data/compendium/character_options/starting_build_options.json"),
        Path("data/compendium/spells/level_0.json"),
        Path("data/compendium/spells/level_1.json"),
        Path("data/compendium/spells/level_2.json"),
        Path("data/compendium/spells/level_3.json"),
        Path("data/compendium/spells/class_spell_lists.json"),
        Path("data/compendium/spells/spell_effects.json"),
        Path("data/rules/source/creation/choose_character_sheet.md"),
        Path("data/rules/source/creation/character_creation_overview.md"),
        Path("data/rules/source/creation/ability_scores.md"),
        Path("data/rules/source/creation/alignment.md"),
        Path("data/rules/source/creation/level_advancement.md"),
        Path("data/rules/source/creation/multiclassing.md"),
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
        Path("data/rules/source/adjudication/rhythm_of_play.md"),
        Path("data/rules/source/adjudication/six_abilities.md"),
        Path("data/rules/source/adjudication/d20_tests.md"),
        Path("data/rules/source/adjudication/ability_checks.md"),
        Path("data/rules/source/adjudication/saving_throws.md"),
        Path("data/rules/source/adjudication/attack_rolls.md"),
        Path("data/rules/source/adjudication/advantage_disadvantage.md"),
        Path("data/rules/source/adjudication/proficiency.md"),
        Path("data/rules/source/adjudication/combat_flow.md"),
        Path("data/rules/source/adjudication/combat_actions.md"),
        Path("data/rules/source/adjudication/actions.md"),
        Path("data/rules/source/adjudication/bonus_actions.md"),
        Path("data/rules/source/adjudication/reactions.md"),
        Path("data/rules/source/adjudication/social_interaction.md"),
        Path("data/rules/source/adjudication/exploration.md"),
        Path("data/rules/source/adjudication/vision_and_light.md"),
        Path("data/rules/source/adjudication/hiding.md"),
        Path("data/rules/source/adjudication/interacting_with_objects.md"),
        Path("data/rules/source/adjudication/hazards.md"),
        Path("data/rules/source/adjudication/travel.md"),
        Path("data/rules/source/adjudication/order_of_combat.md"),
        Path("data/rules/source/adjudication/movement_and_position.md"),
        Path("data/rules/source/adjudication/making_an_attack.md"),
        Path("data/rules/source/adjudication/ranged_attacks.md"),
        Path("data/rules/source/adjudication/melee_attacks.md"),
        Path("data/rules/source/adjudication/damage_healing.md"),
        Path("data/rules/source/adjudication/death_dying.md"),
        Path("data/rules/source/adjudication/equipment_overview.md"),
        Path("data/rules/source/adjudication/weapon_properties.md"),
        Path("data/rules/source/adjudication/armor_rules.md"),
        Path("data/rules/source/adjudication/tools.md"),
        Path("data/rules/source/adjudication/adventuring_gear.md"),
        Path("data/rules/source/adjudication/spellcasting_basics.md"),
        Path("docs/data-structures.md"),
        Path("TODO.md"),
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
            "conditions",
            "damage_types",
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
        Path("data/compendium/equipment/weapons.json"): {"weapons"},
        Path("data/compendium/equipment/armor.json"): {"armor"},
        Path("data/compendium/equipment/tools.json"): {"tools"},
        Path("data/compendium/equipment/adventuring_gear.json"): {"adventuring_gear"},
        Path("data/compendium/character_options/species.json"): {"species"},
        Path("data/compendium/character_options/origins.json"): {"origins"},
        Path("data/compendium/character_options/feats.json"): {
            "feat_categories",
            "feats",
        },
        Path("data/compendium/character_options/classes.json"): {"classes"},
        Path("data/compendium/character_options/subclasses.json"): {"subclasses"},
        Path("data/compendium/character_options/class_progression.json"): {
            "class_progression"
        },
        Path("data/compendium/character_options/class_features.json"): {
            "class_features"
        },
        Path("data/compendium/character_options/subclass_features.json"): {
            "subclass_features"
        },
        Path("data/compendium/character_options/invocations.json"): {"invocations"},
        Path("data/compendium/character_options/starting_build_options.json"): {
            "starting_build_options"
        },
        Path("data/compendium/spells/level_0.json"): {"spells"},
        Path("data/compendium/spells/level_1.json"): {"spells"},
        Path("data/compendium/spells/level_2.json"): {"spells"},
        Path("data/compendium/spells/level_3.json"): {"spells"},
        Path("data/compendium/spells/class_spell_lists.json"): {"class_spell_lists"},
        Path("data/compendium/spells/spell_effects.json"): {"spell_effects"},
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
    weapons = json.loads(Path("data/compendium/equipment/weapons.json").read_text())
    armor = json.loads(Path("data/compendium/equipment/armor.json").read_text())
    tools = json.loads(Path("data/compendium/equipment/tools.json").read_text())
    gear = json.loads(
        Path("data/compendium/equipment/adventuring_gear.json").read_text()
    )
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
    assert weapons["weapons"] == []
    assert armor["armor"] == []
    assert tools["tools"] == []
    assert gear["adventuring_gear"] == []


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
    equipment_paths = [
        Path("data/compendium/equipment/weapons.json"),
        Path("data/compendium/equipment/armor.json"),
        Path("data/compendium/equipment/tools.json"),
        Path("data/compendium/equipment/adventuring_gear.json"),
    ]
    option_paths = [
        Path("data/compendium/character_options/species.json"),
        Path("data/compendium/character_options/origins.json"),
        Path("data/compendium/character_options/feats.json"),
        Path("data/compendium/character_options/classes.json"),
        Path("data/compendium/character_options/subclasses.json"),
        Path("data/compendium/character_options/class_progression.json"),
        Path("data/compendium/character_options/class_features.json"),
        Path("data/compendium/character_options/subclass_features.json"),
        Path("data/compendium/character_options/invocations.json"),
        Path("data/compendium/character_options/starting_build_options.json"),
        Path("data/compendium/spells/class_spell_lists.json"),
        Path("data/compendium/spells/spell_effects.json"),
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

    for path in equipment_paths:
        parsed = json.loads(path.read_text())
        assert isinstance(next(iter(parsed.values())), list)

    for path in option_paths:
        parsed = json.loads(path.read_text())
        for value in parsed.values():
            assert isinstance(value, list)


def test_structured_character_options_and_spell_lists_exist() -> None:
    """Starter character options should include the top-level playable set."""

    species = json.loads(
        Path("data/compendium/character_options/species.json").read_text()
    )
    origins = json.loads(
        Path("data/compendium/character_options/origins.json").read_text()
    )
    classes = json.loads(
        Path("data/compendium/character_options/classes.json").read_text()
    )
    subclasses = json.loads(
        Path("data/compendium/character_options/subclasses.json").read_text()
    )
    class_spell_lists = json.loads(
        Path("data/compendium/spells/class_spell_lists.json").read_text()
    )

    assert any(entry["species_id"] == "human" for entry in species["species"])
    assert any(entry["species_id"] == "tiefling" for entry in species["species"])
    assert any(entry["origin_id"] == "acolyte" for entry in origins["origins"])
    assert any(entry["origin_id"] == "soldier" for entry in origins["origins"])
    assert any(entry["class_id"] == "wizard" for entry in classes["classes"])
    assert any(entry["class_id"] == "fighter" for entry in classes["classes"])
    assert any(
        entry["subclass_id"] == "path-of-the-berserker"
        for entry in subclasses["subclasses"]
    )
    assert any(
        entry["class_id"] == "wizard"
        and "magic-missile" in entry["spell_ids_by_level"]["1"]
        for entry in class_spell_lists["class_spell_lists"]
    )
    assert any(
        entry["class_id"] == "wizard"
        and "mage-armor" in entry["spell_ids_by_level"]["1"]
        for entry in class_spell_lists["class_spell_lists"]
    )
    assert any(
        entry["class_id"] == "sorcerer"
        and "mage-armor" in entry["spell_ids_by_level"]["1"]
        for entry in class_spell_lists["class_spell_lists"]
    )
    assert any(
        entry["class_id"] == "bard"
        and "feather-fall" in entry["spell_ids_by_level"]["1"]
        for entry in class_spell_lists["class_spell_lists"]
    )
    assert any(
        entry["class_id"] == "sorcerer"
        and "feather-fall" in entry["spell_ids_by_level"]["1"]
        for entry in class_spell_lists["class_spell_lists"]
    )
    assert any(
        entry["class_id"] == "wizard"
        and "feather-fall" in entry["spell_ids_by_level"]["1"]
        for entry in class_spell_lists["class_spell_lists"]
    )
    assert any(
        entry["class_id"] == "cleric" and "guidance" in entry["spell_ids_by_level"]["0"]
        for entry in class_spell_lists["class_spell_lists"]
    )


def test_character_rules_todo_schema_gaps_are_structured() -> None:
    """TODO schema gaps should have queryable first-cut structured contracts."""

    progression = json.loads(
        Path("data/compendium/character_options/class_progression.json").read_text()
    )
    features = json.loads(
        Path("data/compendium/character_options/class_features.json").read_text()
    )
    subclass_features = json.loads(
        Path("data/compendium/character_options/subclass_features.json").read_text()
    )
    invocations = json.loads(
        Path("data/compendium/character_options/invocations.json").read_text()
    )
    build_options = json.loads(
        Path(
            "data/compendium/character_options/starting_build_options.json"
        ).read_text()
    )
    spell_effects = json.loads(
        Path("data/compendium/spells/spell_effects.json").read_text()
    )

    warlock = next(
        entry
        for entry in progression["class_progression"]
        if entry["class_id"] == "warlock"
    )
    warlock_level_three = warlock["levels"]["3"]
    fiend_level_three = next(
        entry
        for entry in subclass_features["subclass_features"]
        if entry["subclass_id"] == "fiend-patron"
        and entry["level"] == SUBCLASS_ENTRY_LEVEL
    )
    agonizing_blast = next(
        entry
        for entry in invocations["invocations"]
        if entry["invocation_id"] == "agonizing-blast"
    )
    wizard_build = next(
        entry
        for entry in build_options["starting_build_options"]
        if entry["class_id"] == "wizard"
    )
    fireball_effect = next(
        entry
        for entry in spell_effects["spell_effects"]
        if entry["spell_id"] == "fireball"
    )

    assert warlock_level_three["pact_magic_slots"] == WARLOCK_LEVEL_THREE_PACT_SLOTS
    assert (
        warlock_level_three["pact_magic_slot_level"]
        == WARLOCK_LEVEL_THREE_PACT_SLOT_LEVEL
    )
    assert warlock_level_three["invocations_known"] == WARLOCK_LEVEL_THREE_INVOCATIONS
    assert warlock_level_three["subclass_feature_ids"] == [
        "dark-ones-blessing",
        "fiend-spells",
    ]
    assert any(
        entry["feature_id"] == "pact-magic"
        and entry["class_id"] == "warlock"
        and entry["level"] == 1
        for entry in features["class_features"]
    )
    assert "dark-ones-blessing" in fiend_level_three["feature_ids"]
    assert "eldritch-blast" in agonizing_blast["spell_ids"]
    assert (
        wizard_build["spellbook_level_1_spell_count"]
        == WIZARD_STARTING_SPELLBOOK_SPELLS
    )
    assert fireball_effect["save"] == "dexterity"
    assert fireball_effect["damage"]["dice"] == "8d6"
    assert fireball_effect["area"] == "20-foot-radius Sphere"


def test_class_and_subclass_metadata_support_basic_build_queries() -> None:
    """Class metadata should expose core chassis details needed during creation."""

    classes = json.loads(
        Path("data/compendium/character_options/classes.json").read_text()
    )
    subclasses = json.loads(
        Path("data/compendium/character_options/subclasses.json").read_text()
    )

    barbarian = next(
        entry for entry in classes["classes"] if entry["class_id"] == "barbarian"
    )
    bard = next(entry for entry in classes["classes"] if entry["class_id"] == "bard")
    warlock = next(
        entry for entry in classes["classes"] if entry["class_id"] == "warlock"
    )
    lore_bard = next(
        entry
        for entry in subclasses["subclasses"]
        if entry["subclass_id"] == "college-of-lore"
    )

    assert barbarian["saving_throws"] == ["strength", "constitution"]
    assert "martial-weapons" in barbarian["weapon_proficiencies"]
    assert "shields" in barbarian["armor_training"]

    assert bard["skill_choice_count"] == BARD_SKILL_CHOICES
    assert "musical-instrument" in bard["tool_proficiencies"]
    assert bard["spellcasting_ability"] == "charisma"

    assert warlock["saving_throws"] == ["wisdom", "charisma"]
    assert warlock["is_spellcaster"] is True
    assert lore_bard["entry_level"] == SUBCLASS_ENTRY_LEVEL


def test_origins_species_and_feats_are_structured_for_build_resolution() -> None:
    """Character options should carry enough structure for legal build queries."""

    species = json.loads(
        Path("data/compendium/character_options/species.json").read_text()
    )
    origins = json.loads(
        Path("data/compendium/character_options/origins.json").read_text()
    )
    feats = json.loads(Path("data/compendium/character_options/feats.json").read_text())

    dragonborn = next(
        entry for entry in species["species"] if entry["species_id"] == "dragonborn"
    )
    human = next(
        entry for entry in species["species"] if entry["species_id"] == "human"
    )
    acolyte = next(
        entry for entry in origins["origins"] if entry["origin_id"] == "acolyte"
    )
    alert = next(entry for entry in feats["feats"] if entry["feat_id"] == "alert")
    magic_initiate = next(
        entry for entry in feats["feats"] if entry["feat_id"] == "magic-initiate-cleric"
    )
    archery = next(entry for entry in feats["feats"] if entry["feat_id"] == "archery")

    assert dragonborn["creature_type"] == "humanoid"
    assert dragonborn["speed"] == MEDIUM_SPEED_FEET
    assert "draconic-ancestry" in dragonborn["trait_ids"]
    assert human["size_options"] == ["medium", "small"]
    assert "origin-feat-choice" in human["trait_ids"]

    assert acolyte["ability_score_options"] == [
        "intelligence",
        "wisdom",
        "charisma",
    ]
    assert acolyte["feat_id"] == "magic-initiate-cleric"
    assert acolyte["skill_proficiencies"] == ["insight", "religion"]

    assert alert["category"] == "origin"
    assert "initiative-proficiency" in alert["benefit_ids"]
    assert magic_initiate["repeatable"] is True
    assert archery["category"] == "fighting_style"


def test_first_ingested_corpus_content_exists() -> None:
    """The first SRD ingestion pass should load representative live corpus content."""

    aberrations = json.loads(
        Path("data/compendium/monsters/aberrations.json").read_text()
    )
    beasts = json.loads(Path("data/compendium/monsters/beasts.json").read_text())
    celestials = json.loads(
        Path("data/compendium/monsters/celestials.json").read_text()
    )
    constructs = json.loads(
        Path("data/compendium/monsters/constructs.json").read_text()
    )
    dragons = json.loads(Path("data/compendium/monsters/dragons.json").read_text())
    fey = json.loads(Path("data/compendium/monsters/fey.json").read_text())
    fiends = json.loads(Path("data/compendium/monsters/fiends.json").read_text())
    humanoids = json.loads(Path("data/compendium/monsters/humanoids.json").read_text())
    oozes = json.loads(Path("data/compendium/monsters/oozes.json").read_text())
    plants = json.loads(Path("data/compendium/monsters/plants.json").read_text())
    undead = json.loads(Path("data/compendium/monsters/undead.json").read_text())
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
    assert any(monster["monster_id"] == "wolf" for monster in beasts["monsters"])
    assert any(monster["monster_id"] == "couatl" for monster in celestials["monsters"])
    assert any(
        monster["monster_id"] == "animated-armor" for monster in constructs["monsters"]
    )
    assert any(
        monster["monster_id"] == "copper-dragon-wyrmling"
        for monster in dragons["monsters"]
    )
    assert any(monster["monster_id"] == "dryad" for monster in fey["monsters"])
    assert any(monster["monster_id"] == "imp" for monster in fiends["monsters"])
    assert any(monster["monster_id"] == "bandit" for monster in humanoids["monsters"])
    assert any(
        monster["monster_id"] == "gelatinous-cube" for monster in oozes["monsters"]
    )
    assert any(monster["monster_id"] == "shrieker" for monster in plants["monsters"])
    assert any(monster["monster_id"] == "skeleton" for monster in undead["monsters"])
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
    assert any(spell["spell_id"] == "acid-splash" for spell in cantrips["spells"])
    assert any(spell["spell_id"] == "vicious-mockery" for spell in cantrips["spells"])
    assert any(
        spell["spell_id"] == "magic-missile" for spell in level_one_spells["spells"]
    )
    assert any(
        spell["spell_id"] == "feather-fall" for spell in level_one_spells["spells"]
    )
    assert any(
        spell["spell_id"] == "mage-armor" for spell in level_one_spells["spells"]
    )
    assert any(spell["spell_id"] == "command" for spell in level_one_spells["spells"])
    assert any(spell["spell_id"] == "sleep" for spell in level_one_spells["spells"])
    assert any(
        spell["spell_id"] == "misty-step" for spell in level_two_spells["spells"]
    )
    assert any(
        spell["spell_id"] == "hold-person" for spell in level_two_spells["spells"]
    )
    assert any(
        spell["spell_id"] == "suggestion" for spell in level_two_spells["spells"]
    )
    assert any(
        spell["spell_id"] == "fireball" for spell in level_three_spells["spells"]
    )
    assert any(
        spell["spell_id"] == "dispel-magic" for spell in level_three_spells["spells"]
    )
    assert any(spell["spell_id"] == "fly" for spell in level_three_spells["spells"])


def test_requested_starter_spell_subset_exists_and_is_class_referenced() -> None:
    """The starter spell subset should be available for level 1 to 5 builds."""

    root = Path("data/compendium/spells")
    spell_files = [
        root / "level_0.json",
        root / "level_1.json",
        root / "level_2.json",
        root / "level_3.json",
    ]
    spell_ids = {
        spell["spell_id"]
        for path in spell_files
        for spell in json.loads(path.read_text())["spells"]
    }
    class_spell_lists = json.loads((root / "class_spell_lists.json").read_text())
    referenced_spell_ids = {
        spell_id
        for entry in class_spell_lists["class_spell_lists"]
        for spell_ids_by_level in entry["spell_ids_by_level"].values()
        for spell_id in spell_ids_by_level
    }

    assert STARTER_SPELL_IDS.issubset(spell_ids)
    assert STARTER_SPELL_IDS.issubset(referenced_spell_ids)
    assert referenced_spell_ids.issubset(spell_ids)


def test_rule_source_files_are_nonempty() -> None:
    """First-cut rule source files should contain ingested prose rather than stubs."""

    minimum_rule_length = 40

    rule_paths = [
        Path("data/rules/source/creation/choose_character_sheet.md"),
        Path("data/rules/source/creation/character_creation_overview.md"),
        Path("data/rules/source/creation/ability_scores.md"),
        Path("data/rules/source/creation/alignment.md"),
        Path("data/rules/source/creation/level_advancement.md"),
        Path("data/rules/source/creation/multiclassing.md"),
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
        Path("data/rules/source/adjudication/rhythm_of_play.md"),
        Path("data/rules/source/adjudication/six_abilities.md"),
        Path("data/rules/source/adjudication/d20_tests.md"),
        Path("data/rules/source/adjudication/ability_checks.md"),
        Path("data/rules/source/adjudication/saving_throws.md"),
        Path("data/rules/source/adjudication/attack_rolls.md"),
        Path("data/rules/source/adjudication/advantage_disadvantage.md"),
        Path("data/rules/source/adjudication/proficiency.md"),
        Path("data/rules/source/adjudication/combat_flow.md"),
        Path("data/rules/source/adjudication/combat_actions.md"),
        Path("data/rules/source/adjudication/actions.md"),
        Path("data/rules/source/adjudication/bonus_actions.md"),
        Path("data/rules/source/adjudication/reactions.md"),
        Path("data/rules/source/adjudication/social_interaction.md"),
        Path("data/rules/source/adjudication/exploration.md"),
        Path("data/rules/source/adjudication/vision_and_light.md"),
        Path("data/rules/source/adjudication/hiding.md"),
        Path("data/rules/source/adjudication/interacting_with_objects.md"),
        Path("data/rules/source/adjudication/hazards.md"),
        Path("data/rules/source/adjudication/travel.md"),
        Path("data/rules/source/adjudication/order_of_combat.md"),
        Path("data/rules/source/adjudication/movement_and_position.md"),
        Path("data/rules/source/adjudication/making_an_attack.md"),
        Path("data/rules/source/adjudication/ranged_attacks.md"),
        Path("data/rules/source/adjudication/melee_attacks.md"),
        Path("data/rules/source/adjudication/damage_healing.md"),
        Path("data/rules/source/adjudication/death_dying.md"),
        Path("data/rules/source/adjudication/equipment_overview.md"),
        Path("data/rules/source/adjudication/weapon_properties.md"),
        Path("data/rules/source/adjudication/armor_rules.md"),
        Path("data/rules/source/adjudication/tools.md"),
        Path("data/rules/source/adjudication/adventuring_gear.md"),
        Path("data/rules/source/adjudication/spellcasting_basics.md"),
    ]

    for path in rule_paths:
        assert len(path.read_text().strip()) > minimum_rule_length, path


def test_representative_class_files_capture_exact_low_level_rules() -> None:
    """Representative class files should include exact low-level SRD mechanics."""

    barbarian = Path("data/rules/source/creation/classes/barbarian.md").read_text()
    bard = Path("data/rules/source/creation/classes/bard.md").read_text()
    cleric = Path("data/rules/source/creation/classes/cleric.md").read_text()
    druid = Path("data/rules/source/creation/classes/druid.md").read_text()
    warlock = Path("data/rules/source/creation/classes/warlock.md").read_text()
    wizard = Path("data/rules/source/creation/classes/wizard.md").read_text()

    assert "Rage lasts until the end of your next turn" in barbarian
    assert "At level 1, Rage uses: `2`" in barbarian
    assert "At level 3, prepared spells: `6`" in bard
    assert BARD_SHORT_REST_TEXT in bard
    assert "You can use this class's Channel Divinity twice" in cleric
    assert "Divine Spark" in cleric
    assert "You know four Beast forms" in druid
    assert "Temporary Hit Points equal to your Druid level" in druid
    assert "At level 1, Pact Magic slots: `1`" in warlock
    assert "At level 3, Pact Magic slot level: `2`" in warlock
    assert "It starts with six level 1 Wizard spells of your choice" in wizard
    assert "Arcane Recovery" in wizard


def test_additional_class_files_capture_exact_low_level_rules() -> None:
    """The second class batch should also carry exact low-level SRD mechanics."""

    fighter = Path("data/rules/source/creation/classes/fighter.md").read_text()
    monk = Path("data/rules/source/creation/classes/monk.md").read_text()
    paladin = Path("data/rules/source/creation/classes/paladin.md").read_text()
    ranger = Path("data/rules/source/creation/classes/ranger.md").read_text()
    rogue = Path("data/rules/source/creation/classes/rogue.md").read_text()
    sorcerer = Path("data/rules/source/creation/classes/sorcerer.md").read_text()

    assert "You can use this feature twice" in fighter
    assert "you can take one additional action, except the Magic action" in fighter
    assert MONK_FOCUS_TEXT in monk
    assert "At level 2, Focus Points: `2`" in monk
    assert "pool of healing power" in paladin
    assert "You can use this class's Channel Divinity twice" in paladin
    assert "Hunter's Mark" in ranger
    assert "prepared spells: `6`" in ranger
    assert "Sneak Attack" in rogue
    assert "Cunning Strike" in rogue
    assert "Sorcery Points" in sorcerer
    assert "Innate Sorcery" in sorcerer


def test_equipment_and_spellcasting_rule_files_capture_core_srd_details() -> None:
    """Equipment and generic spellcasting files should preserve included SRD rules."""

    equipment = Path("data/rules/source/adjudication/equipment_overview.md").read_text()
    properties = Path("data/rules/source/adjudication/weapon_properties.md").read_text()
    armor = Path("data/rules/source/adjudication/armor_rules.md").read_text()
    tools = Path("data/rules/source/adjudication/tools.md").read_text()
    gear = Path("data/rules/source/adjudication/adventuring_gear.md").read_text()
    spellcasting = Path(
        "data/rules/source/adjudication/spellcasting_basics.md"
    ).read_text()

    assert "fifty coins weigh a pound" in equipment
    assert "Equipment fetches half its cost when sold" in equipment
    assert LIGHT_WEAPON_TEXT in properties
    assert "Push" in properties
    assert ARMOR_TRAINING_TEXT in armor
    assert "A creature can wear only one suit of armor at a time" in armor
    assert "If you have proficiency with a tool, add your Proficiency Bonus" in tools
    assert "Thieves' Tools" in tools
    assert "Potion of Healing" in gear
    assert "Portable Ram" in gear
    assert ONE_SLOT_PER_TURN_TEXT in spellcasting
    assert MATERIAL_HAND_TEXT in spellcasting


def test_cantrip_compendium_entries_capture_exact_spell_details() -> None:
    """Representative cantrips should preserve actionable SRD mechanics."""

    cantrips = _spell_map("data/compendium/spells/level_0.json")
    acid_splash = cantrips["acid-splash"]
    guidance = cantrips["guidance"]
    eldritch_blast = cantrips["eldritch-blast"]

    assert acid_splash["save"] == "dexterity"
    assert "within 5 feet of each other" in acid_splash["description"]
    assert "levels 5 (2d6), 11 (3d6), and 17 (4d6)" in acid_splash["higher_level"]

    assert guidance["concentration"] is True
    assert "choose a skill" in guidance["description"]

    assert eldritch_blast["attack"] == "ranged spell attack"
    assert "2 beams" in eldritch_blast["higher_level"]


def test_level_one_spell_compendium_entries_capture_exact_details() -> None:
    """Representative level 1 spells should preserve actionable SRD mechanics."""

    level_one = _spell_map("data/compendium/spells/level_1.json")
    bless = level_one["bless"]
    burning_hands = level_one["burning-hands"]
    charm_person = level_one["charm-person"]
    shield = level_one["shield"]
    sleep = level_one["sleep"]

    assert bless["concentration"] is True

    assert charm_person["save"] == "wisdom"
    assert CHARM_PERSON_TEXT in charm_person["description"]
    assert "one additional creature" in charm_person["higher_level"]

    assert burning_hands["area"] == "15-foot Cone"
    assert burning_hands["save"] == "dexterity"
    assert "3d6 Fire damage" in burning_hands["description"]

    assert (
        shield["trigger"]
        == "being hit by an attack roll or targeted by the Magic Missile spell"
    )
    assert "+5 bonus to AC" in shield["description"]

    assert sleep["concentration"] is True
    assert sleep["save"] == "wisdom"
    assert (
        "Incapacitated condition until the end of its next turn" in sleep["description"]
    )
    assert (
        "have Immunity to the Exhaustion condition automatically succeed"
        in sleep["description"]
    )


def test_level_two_spell_compendium_entries_capture_exact_details() -> None:
    """Representative level 2 spells should preserve actionable SRD mechanics."""

    level_two = _spell_map("data/compendium/spells/level_2.json")
    spiritual_weapon = level_two["spiritual-weapon"]
    web = level_two["web"]

    assert web["concentration"] is True
    assert web["area"] == "20-foot Cube"
    assert WEB_TEXT in web["description"]

    assert spiritual_weapon["attack"] == "melee spell attack"
    assert (
        "1d8 plus your spellcasting ability modifier" in spiritual_weapon["description"]
    )


def test_level_three_spell_compendium_entries_capture_exact_details() -> None:
    """Representative level 3 spells should preserve actionable SRD mechanics."""

    level_three = _spell_map("data/compendium/spells/level_3.json")
    counterspell = level_three["counterspell"]
    dispel_magic = level_three["dispel-magic"]
    fireball = level_three["fireball"]
    spirit_guardians = level_three["spirit-guardians"]

    assert counterspell["save"] == "constitution"
    assert COUNTERSPELL_TEXT in counterspell["description"]

    assert "Any ongoing spell of level 3 or lower" in dispel_magic["description"]
    assert "For each ongoing spell of level 4 or higher" in dispel_magic["description"]
    assert (
        "equal to or less than the level of the spell slot you use"
        in dispel_magic["higher_level"]
    )

    assert fireball["area"] == "20-foot-radius Sphere"
    assert FIREBALL_TEXT in fireball["description"]
    assert "The damage increases by 1d6" in fireball["higher_level"]

    assert spirit_guardians["area"] == "15-foot Emanation"
    assert spirit_guardians["save"] == "wisdom"
    assert SPIRIT_GUARDIANS_TEXT in spirit_guardians["description"]


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
