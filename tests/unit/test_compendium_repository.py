"""Unit tests for the compendium repository."""

from pathlib import Path

from campaignnarrator.repositories.compendium_repository import CompendiumRepository


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
