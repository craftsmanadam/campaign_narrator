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


def test_json_contract_files_are_parseable_and_have_expected_top_level_keys() -> None:
    """Starter JSON files should parse and expose stable top-level contracts."""

    expected_keys = {
        Path("data/compendium/magic_items/common.json"): {"magic_items"},
        Path("data/compendium/magic_items/uncommon.json"): {"magic_items"},
        Path("data/compendium/magic_items/rare.json"): {"magic_items"},
        Path("data/compendium/equipment/weapons.json"): {"weapons"},
        Path("data/compendium/equipment/armor.json"): {"armor"},
        Path("data/compendium/equipment/tools.json"): {"tools"},
        Path("data/compendium/equipment/adventuring_gear.json"): {"adventuring_gear"},
        Path("data/compendium/character_options/species.json"): {"species"},
        Path("data/compendium/character_options/origins.json"): {"origins"},
        Path("data/compendium/character_options/feats.json"): {"feats"},
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


def test_live_compendium_files_match_their_wrappers() -> None:
    """Live compendium files should keep stable wrapper objects after ingestion."""

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

    monster_index = json.loads(Path("data/compendium/monsters/index.json").read_text())
    monster_names = {entry["name"] for entry in monster_index}
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

    assert "Aboleth" in monster_names
    assert "Wolf" in monster_names
    assert "Couatl" in monster_names
    assert "Animated Armor (Animated Object)" in monster_names
    assert "Copper Dragon Wyrmling (Metallic)" in monster_names
    assert "Dryad" in monster_names
    assert "Imp (Devil)" in monster_names
    assert "Bandit" in monster_names
    assert "Gelatinous Cube (Ooze)" in monster_names
    assert "Shrieker (Fungi)" in monster_names
    assert "Skeleton" in monster_names
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


def test_feats_json_has_no_feat_categories_key() -> None:
    """The feats.json should not have a redundant feat_categories key."""
    feats_path = Path("data/compendium/character_options/feats.json")
    payload = json.loads(feats_path.read_text())
    assert "feat_categories" not in payload


def test_all_feat_entries_have_summary() -> None:
    """All feat entries should have a non-empty summary field."""
    feats_path = Path("data/compendium/character_options/feats.json")
    payload = json.loads(feats_path.read_text())
    for entry in payload["feats"]:
        feat_id = entry.get("feat_id")
        assert "summary" in entry, f"feat {feat_id} missing summary"
        assert entry["summary"], f"feat {feat_id} has empty summary"


_ARMOR_PATH = Path("data/compendium/equipment/armor.json")
_WEAPONS_PATH = Path("data/compendium/equipment/weapons.json")
_VALID_ARMOR_CATEGORIES = {"light", "medium", "heavy", "shield"}
_VALID_WEAPON_CATEGORIES = {
    "simple_melee",
    "simple_ranged",
    "martial_melee",
    "martial_ranged",
}
_ARMOR_REQUIRED_FIELDS = {
    "item_id",
    "name",
    "category",
    "ac_formula",
    "strength_requirement",
    "stealth_disadvantage",
    "reference",
}
_WEAPON_REQUIRED_FIELDS = {
    "item_id",
    "name",
    "category",
    "damage_dice",
    "damage_type",
    "properties",
    "reference",
}
_EXPECTED_ARMOR_COUNT = 13
_EXPECTED_WEAPON_COUNT = 37
_CHAIN_MAIL_STR_REQUIREMENT = 13
_PLATE_STR_REQUIREMENT = 15


def test_armor_json_has_expected_entry_count() -> None:
    """armor.json must contain all 13 SRD armor entries."""
    payload = json.loads(_ARMOR_PATH.read_text())
    assert len(payload["armor"]) == _EXPECTED_ARMOR_COUNT


def test_armor_entries_have_required_fields() -> None:
    """Every armor entry must carry all required fields."""
    payload = json.loads(_ARMOR_PATH.read_text())
    for entry in payload["armor"]:
        item_id = entry.get("item_id")
        missing = _ARMOR_REQUIRED_FIELDS - entry.keys()
        assert not missing, f"armor {item_id} missing fields: {missing}"


def test_armor_category_values_are_valid() -> None:
    """Every armor entry must have a recognised category."""
    payload = json.loads(_ARMOR_PATH.read_text())
    for entry in payload["armor"]:
        assert entry["category"] in _VALID_ARMOR_CATEGORIES, (
            f"armor {entry.get('item_id')} has invalid category {entry['category']!r}"
        )


def test_armor_spot_checks() -> None:
    """Key armor entries must carry the correct mechanical values."""
    payload = json.loads(_ARMOR_PATH.read_text())
    entries = {e["item_id"]: e for e in payload["armor"]}

    chain_mail = entries["chain-mail"]
    assert chain_mail["ac_formula"] == "16"
    assert chain_mail["strength_requirement"] == _CHAIN_MAIL_STR_REQUIREMENT
    assert chain_mail["stealth_disadvantage"] is True

    plate = entries["plate"]
    assert plate["ac_formula"] == "18"
    assert plate["strength_requirement"] == _PLATE_STR_REQUIREMENT

    leather = entries["leather"]
    assert leather["category"] == "light"
    assert leather["ac_formula"] == "11 + Dex modifier"
    assert leather["stealth_disadvantage"] is False

    shield = entries["shield"]
    assert shield["category"] == "shield"
    assert shield["ac_formula"] == "+2"


def test_weapon_json_has_expected_entry_count() -> None:
    """weapons.json must contain all 37 SRD weapon entries."""
    payload = json.loads(_WEAPONS_PATH.read_text())
    assert len(payload["weapons"]) == _EXPECTED_WEAPON_COUNT


def test_weapon_entries_have_required_fields() -> None:
    """Every weapon entry must carry all required fields."""
    payload = json.loads(_WEAPONS_PATH.read_text())
    for entry in payload["weapons"]:
        item_id = entry.get("item_id")
        missing = _WEAPON_REQUIRED_FIELDS - entry.keys()
        assert not missing, f"weapon {item_id} missing fields: {missing}"


def test_weapon_category_values_are_valid() -> None:
    """Every weapon entry must have a recognised category."""
    payload = json.loads(_WEAPONS_PATH.read_text())
    for entry in payload["weapons"]:
        assert entry["category"] in _VALID_WEAPON_CATEGORIES, (
            f"weapon {entry.get('item_id')} has invalid category {entry['category']!r}"
        )


def test_weapon_properties_are_arrays() -> None:
    """Every weapon properties field must be a list."""
    payload = json.loads(_WEAPONS_PATH.read_text())
    for entry in payload["weapons"]:
        assert isinstance(entry["properties"], list), (
            f"weapon {entry.get('item_id')} properties is not a list"
        )


def test_weapon_spot_checks() -> None:
    """Key weapon entries must carry the correct mechanical values."""
    payload = json.loads(_WEAPONS_PATH.read_text())
    entries = {e["item_id"]: e for e in payload["weapons"]}

    longsword = entries["longsword"]
    assert longsword["damage_dice"] == "1d8"
    assert longsword["damage_type"] == "slashing"
    assert "versatile (1d10)" in longsword["properties"]

    dagger = entries["dagger"]
    assert dagger["damage_dice"] == "1d4"
    assert "finesse" in dagger["properties"]
    assert "thrown (range 20/60)" in dagger["properties"]

    greatsword = entries["greatsword"]
    assert greatsword["damage_dice"] == "2d6"
    assert "heavy" in greatsword["properties"]
    assert "two-handed" in greatsword["properties"]

    net = entries["net"]
    assert net["damage_dice"] is None
    assert net["damage_type"] is None

    blowgun = entries["blowgun"]
    assert blowgun["damage_dice"] == "1"
    assert blowgun["damage_type"] == "piercing"
