"""Unit tests for the compendium repository."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from campaignnarrator.repositories.compendium_repository import CompendiumRepository

_COMPENDIUM_ROOT = Path(__file__).resolve().parents[2] / "data" / "compendium"


def _repository() -> CompendiumRepository:
    return CompendiumRepository(_COMPENDIUM_ROOT)


def test_compendium_repository_loads_magic_items_by_rarity_and_id(
    tmp_path: Path,
) -> None:
    """The repository should load and index compendium files from disk."""

    compendium_root = tmp_path / "compendium"
    (compendium_root / "magic_items").mkdir(parents=True)
    (compendium_root / "magic_items" / "common.json").write_text(
        '{"magic_items": [{"item_id": "potion-of-healing", "name": '
        '"Potion of Healing", "rarity": "common"}]}'
    )
    (compendium_root / "magic_items" / "uncommon.json").write_text(
        '{"magic_items": [{"item_id": "alchemy-jug", "name": "Alchemy Jug", '
        '"rarity": "uncommon"}]}'
    )
    (compendium_root / "magic_items" / "rare.json").write_text(
        '{"magic_items": [{"item_id": "bag-of-beans", "name": "Bag of Beans", '
        '"rarity": "rare"}]}'
    )

    repository = CompendiumRepository(compendium_root)

    assert repository.load_magic_item("common") == {
        "item_id": "potion-of-healing",
        "name": "Potion of Healing",
        "rarity": "common",
    }
    assert repository.load_magic_item("uncommon") == {
        "item_id": "alchemy-jug",
        "name": "Alchemy Jug",
        "rarity": "uncommon",
    }
    assert repository.load_magic_item("rare") == {
        "item_id": "bag-of-beans",
        "name": "Bag of Beans",
        "rarity": "rare",
    }
    assert repository.load_magic_item_by_id("potion-of-healing") == {
        "item_id": "potion-of-healing",
        "name": "Potion of Healing",
        "rarity": "common",
    }


def test_compendium_repository_rejects_invalid_rarity_inputs(
    tmp_path: Path,
) -> None:
    """Magic item lookup should fail closed on traversal-style rarity inputs."""

    compendium_root = tmp_path / "compendium"
    (compendium_root / "magic_items").mkdir(parents=True)
    (compendium_root / "magic_items" / "common.json").write_text(
        '{"magic_items": [{"item_id": "potion-of-healing", "name": '
        '"Potion of Healing", "rarity": "common"}]}'
    )
    (tmp_path / "rare.json").write_text(
        '{"magic_items": [{"item_id": "bag-of-beans", "name": "Bag of Beans", '
        '"rarity": "rare"}]}'
    )
    repository = CompendiumRepository(compendium_root)

    for rarity in ["/etc/passwd", "../common", "common/../../rare"]:
        try:
            repository.load_magic_item(rarity)
        except ValueError:
            continue
        raise AssertionError


def test_compendium_repository_rejects_unknown_item_ids(
    tmp_path: Path,
) -> None:
    """Magic item lookup by ID should fail closed when the item is missing."""

    compendium_root = tmp_path / "compendium"
    (compendium_root / "magic_items").mkdir(parents=True)
    (compendium_root / "magic_items" / "common.json").write_text(
        '{"magic_items": [{"item_id": "potion-of-healing", "name": '
        '"Potion of Healing", "rarity": "common"}]}'
    )
    repository = CompendiumRepository(compendium_root)

    try:
        repository.load_magic_item_by_id("bag-of-beans")
    except ValueError:
        return
    raise AssertionError


def test_compendium_repository_loads_equipment_and_monster_context(
    tmp_path: Path,
) -> None:
    """Equipment and monster context should be loaded from simple JSON fixtures."""

    compendium_root = tmp_path / "compendium"
    (compendium_root / "equipment").mkdir(parents=True)
    (compendium_root / "monsters").mkdir(parents=True)
    (compendium_root / "equipment" / "weapons.json").write_text(
        '{"weapons": [{"item_id": "longsword", "name": "Longsword"}]}'
    )
    (compendium_root / "monsters" / "goblins.json").write_text(
        '{"monsters": [{"monster_id": "goblin", "name": "Goblin"}]}'
    )

    repository = CompendiumRepository(compendium_root)

    assert repository.load_equipment_context(("longsword",)) == (
        '{"item_id": "longsword", "name": "Longsword"}',
    )
    assert repository.load_monster_context(("goblin",)) == (
        '{"monster_id": "goblin", "name": "Goblin"}',
    )


def test_compendium_repository_marks_missing_context(tmp_path: Path) -> None:
    """Missing equipment and monster IDs should return explicit markers."""

    compendium_root = tmp_path / "compendium"
    (compendium_root / "equipment").mkdir(parents=True)
    (compendium_root / "monsters").mkdir(parents=True)
    repository = CompendiumRepository(compendium_root)

    assert repository.load_equipment_context(("longsword",)) == (
        "Missing compendium context: longsword",
    )
    assert repository.load_monster_context(("goblin",)) == (
        "Missing compendium context: goblin",
    )


def test_load_class_returns_entry_for_rogue() -> None:
    repo = _repository()
    entry = repo.load_class("rogue")
    assert entry is not None
    assert entry.class_id == "rogue"
    assert entry.name == "Rogue"
    assert entry.reference == "DND.SRD.Wiki-0.5.2/Classes/Rogue.md"


def test_load_class_returns_entry_for_fighter() -> None:
    repo = _repository()
    entry = repo.load_class("fighter")
    assert entry is not None
    assert entry.class_id == "fighter"
    assert entry.reference == "DND.SRD.Wiki-0.5.2/Classes/Fighter.md"


def test_load_class_returns_none_for_unknown_class() -> None:
    repo = _repository()
    assert repo.load_class("unicorn") is None


def test_load_background_returns_entry_for_charlatan() -> None:
    repo = _repository()
    entry = repo.load_background("charlatan")
    assert entry is not None
    assert entry.background_id == "charlatan"
    assert entry.name == "Charlatan"
    assert entry.reference is not None


def test_load_background_returns_none_for_unknown_background() -> None:
    repo = _repository()
    assert repo.load_background("pirate") is None


def test_load_reference_text_returns_file_content_for_rogue() -> None:
    repo = _repository()
    text = repo.load_reference_text("DND.SRD.Wiki-0.5.2/Classes/Rogue.md")
    assert "Sneak Attack" in text


def test_load_reference_text_returns_section_for_real_wiki_anchor() -> None:
    """load_reference_text extracts the Sneak Attack section from Rogue.md."""
    repo = _repository()
    full = repo.load_reference_text("DND.SRD.Wiki-0.5.2/Classes/Rogue.md")
    section = repo.load_reference_text(
        "DND.SRD.Wiki-0.5.2/Classes/Rogue.md#Sneak Attack"
    )
    assert "Sneak Attack" in section
    assert len(section) < len(full)
    assert "Thieves' Cant" not in section


def test_load_reference_text_raises_for_missing_file() -> None:
    repo = _repository()
    with pytest.raises(FileNotFoundError):
        repo.load_reference_text("DND.SRD.Wiki-0.5.2/Classes/DoesNotExist.md")


def test_load_feat_returns_entry_with_all_fields(tmp_path: Path) -> None:
    """The repository should load and return feat entries with all required fields."""

    reference = "DND.SRD.Wiki-0.5.2/Characterizations/Feats.md#Alert"
    (tmp_path / "character_options").mkdir()
    (tmp_path / "character_options" / "feats.json").write_text(
        json.dumps(
            {
                "feats": [
                    {
                        "feat_id": "alert",
                        "name": "Alert",
                        "category": "origin",
                        "summary": "You gain proficiency in Initiative.",
                        "benefit_ids": ["initiative-proficiency"],
                        "repeatable": False,
                        "reference": reference,
                    }
                ]
            }
        )
    )
    repo = CompendiumRepository(tmp_path)
    entry = repo.load_feat("alert")
    assert entry is not None
    assert entry.feat_id == "alert"
    assert entry.name == "Alert"
    assert entry.summary == "You gain proficiency in Initiative."
    assert entry.reference == reference


def test_load_feat_returns_none_for_unknown_feat(tmp_path: Path) -> None:
    """The repository should return None when a feat is not found."""

    (tmp_path / "character_options").mkdir()
    (tmp_path / "character_options" / "feats.json").write_text('{"feats": []}')
    repo = CompendiumRepository(tmp_path)
    assert repo.load_feat("nonexistent") is None


_FEATS_PATH = _COMPENDIUM_ROOT / "character_options" / "feats.json"
_LEVEL_0_SPELLS_PATH = _COMPENDIUM_ROOT / "spells" / "level_0.json"
_HUMANOIDS_PATH = _COMPENDIUM_ROOT / "monsters" / "humanoids.json"


def test_all_feats_have_reference_field_after_enrichment() -> None:
    """Every feat entry must have a reference key (null is ok for non-SRD feats)."""
    payload = json.loads(_FEATS_PATH.read_text())
    for entry in payload["feats"]:
        feat_id = entry.get("feat_id")
        assert "reference" in entry, f"feat {feat_id} missing reference key"


def test_load_feat_grappler_has_non_null_reference() -> None:
    """Grappler is the only SRD feat and must have a non-null wiki reference."""
    repo = _repository()
    entry = repo.load_feat("grappler")
    assert entry is not None
    assert entry.reference is not None
    assert "Feats.md" in entry.reference


def test_load_reference_text_resolves_grappler_feat_reference() -> None:
    """load_reference_text must load Feats.md when given the grappler reference."""
    repo = _repository()
    feat = repo.load_feat("grappler")
    assert feat is not None
    assert feat.reference is not None
    text = repo.load_reference_text(feat.reference)
    assert "Grappler" in text


def test_spell_entries_have_reference_field() -> None:
    """All level-0 spell entries must have a reference key after enrichment."""
    payload = json.loads(_LEVEL_0_SPELLS_PATH.read_text())
    for entry in payload["spells"]:
        assert "reference" in entry, f"spell {entry.get('spell_id')} missing reference"


def test_acid_splash_reference_resolves_to_real_wiki_file() -> None:
    repo = _repository()
    text = repo.load_reference_text("DND.SRD.Wiki-0.5.2/Spells/Acid Splash.md")
    assert "Acid Splash" in text


def test_monster_entries_have_reference_field() -> None:
    """All humanoid monster entries must have a reference key after enrichment."""
    payload = json.loads(_HUMANOIDS_PATH.read_text())
    for entry in payload["monsters"]:
        monster_id = entry.get("monster_id")
        assert "reference" in entry, f"monster {monster_id} missing reference"


def test_load_reference_text_returns_section_when_anchor_matches(
    tmp_path: Path,
) -> None:
    wiki = tmp_path / "DND.SRD.Wiki-0.5.2"
    wiki.mkdir(parents=True)
    (wiki / "Fighter.md").write_text(
        "# Fighter\n\n"
        "### Action Surge\n\n"
        "Push yourself beyond your limits.\n\n"
        "### Second Wind\n\n"
        "Regain hit points.\n"
    )
    repo = CompendiumRepository(tmp_path)
    result = repo.load_reference_text("DND.SRD.Wiki-0.5.2/Fighter.md#Action Surge")
    assert "Action Surge" in result
    assert "Push yourself beyond your limits." in result
    assert "Second Wind" not in result


def test_load_reference_text_anchor_match_is_case_insensitive(
    tmp_path: Path,
) -> None:
    wiki = tmp_path / "DND.SRD.Wiki-0.5.2"
    wiki.mkdir(parents=True)
    (wiki / "Fighter.md").write_text(
        "# Fighter\n\n"
        "### Action Surge\n\n"
        "Push yourself beyond your limits.\n\n"
        "### Second Wind\n\n"
        "Regain hit points.\n"
    )
    repo = CompendiumRepository(tmp_path)
    result = repo.load_reference_text("DND.SRD.Wiki-0.5.2/Fighter.md#action surge")
    assert "Action Surge" in result
    assert "Push yourself beyond your limits." in result
    assert "Second Wind" not in result


def test_load_reference_text_section_ends_at_same_level_heading(
    tmp_path: Path,
) -> None:
    wiki = tmp_path / "DND.SRD.Wiki-0.5.2"
    wiki.mkdir(parents=True)
    (wiki / "Feats.md").write_text(
        "# Feats\n\n## Grappler\n\nGrappling rules.\n\n## Alert\n\nInitiative rules.\n"
    )
    repo = CompendiumRepository(tmp_path)
    result = repo.load_reference_text("DND.SRD.Wiki-0.5.2/Feats.md#Grappler")
    assert "Grappler" in result
    assert "Grappling rules." in result
    assert "Alert" not in result


def test_load_reference_text_section_ends_at_higher_level_heading(
    tmp_path: Path,
) -> None:
    wiki = tmp_path / "DND.SRD.Wiki-0.5.2"
    wiki.mkdir(parents=True)
    (wiki / "Classes.md").write_text(
        "# Classes\n\n"
        "## Fighter\n\n"
        "### Action Surge\n\n"
        "Push yourself.\n\n"
        "## Rogue\n\n"
        "Sneaky.\n"
    )
    repo = CompendiumRepository(tmp_path)
    result = repo.load_reference_text("DND.SRD.Wiki-0.5.2/Classes.md#Action Surge")
    assert "Action Surge" in result
    assert "Push yourself." in result
    assert "Rogue" not in result


def test_load_reference_text_section_includes_deeper_headings(
    tmp_path: Path,
) -> None:
    wiki = tmp_path / "DND.SRD.Wiki-0.5.2"
    wiki.mkdir(parents=True)
    (wiki / "Fighter.md").write_text(
        "# Fighter\n\n"
        "## Martial Archetypes\n\n"
        "Overview text.\n\n"
        "### Champion\n\n"
        "Champion details.\n\n"
        "#### Improved Critical\n\n"
        "Crit on 19 or 20.\n\n"
        "## Rogue\n\n"
        "Sneak attack.\n"
    )
    repo = CompendiumRepository(tmp_path)
    result = repo.load_reference_text(
        "DND.SRD.Wiki-0.5.2/Fighter.md#Martial Archetypes"
    )
    assert "Martial Archetypes" in result
    assert "Champion" in result
    assert "Improved Critical" in result
    assert "Crit on 19 or 20." in result
    assert "Rogue" not in result


def test_load_reference_text_falls_back_to_full_file_when_anchor_not_found(
    tmp_path: Path,
) -> None:
    wiki = tmp_path / "DND.SRD.Wiki-0.5.2"
    wiki.mkdir(parents=True)
    content = "# Fighter\n\nSome content.\n"
    (wiki / "Fighter.md").write_text(content)
    repo = CompendiumRepository(tmp_path)
    result = repo.load_reference_text(
        "DND.SRD.Wiki-0.5.2/Fighter.md#Nonexistent Heading"
    )
    assert result == content


def test_load_equipment_context_returns_longsword_data() -> None:
    repo = _repository()
    result = repo.load_equipment_context(("longsword",))
    assert len(result) == 1
    assert "longsword" in result[0]
    assert "1d8" in result[0]


def test_load_equipment_context_returns_chain_mail_data() -> None:
    repo = _repository()
    result = repo.load_equipment_context(("chain-mail",))
    assert len(result) == 1
    assert "chain-mail" in result[0]
    assert '"ac_formula": "16"' in result[0]


def test_load_equipment_context_dagger_has_finesse_property() -> None:
    repo = _repository()
    result = repo.load_equipment_context(("dagger",))
    assert len(result) == 1
    assert "finesse" in result[0]


def test_load_equipment_context_returns_missing_marker_for_unknown_item() -> None:
    repo = _repository()
    result = repo.load_equipment_context(("nonexistent-item",))
    assert len(result) == 1
    assert "Missing compendium context:" in result[0]
