"""Unit tests for monster_loader."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
from campaignnarrator.domain.models import ActorState, ActorType
from campaignnarrator.tools.monster_loader import load_by_name, load_by_path

# --- Goblin constants (from SRD markdown) ---
_GOBLIN_AC = 15
_GOBLIN_HP = 7
_GOBLIN_DEX_MOD = 2
_GOBLIN_SCIMITAR_BONUS = 4
_GOBLIN_SCIMITAR_DAMAGE_BONUS = 2
_GOBLIN_SHORTBOW_BONUS = 4

# --- Zombie constants (from SRD markdown) ---
_ZOMBIE_DEX_MOD = -2
_ZOMBIE_SLAM_BONUS = 3
_ZOMBIE_SLAM_DAMAGE_BONUS = 1
_ZOMBIE_HP = 7

# --- Attack lines are long by SRD spec; line-length is suppressed for this file ---
_GOBLIN_MD = textwrap.dedent("""\
    ## Goblin

    *Small humanoid (goblinoid), neutral evil*

    **Armor Class** 15 (leather armor, shield)

    **Hit Points** 7 (2d6)

    **Speed** 30 ft.

    | STR | DEX | CON | INT | WIS | CHA |
    |-----|-----|-----|-----|-----|-----|
    | 8 (-1) | 14 (+2) | 10 (+0) | 10 (+0) | 8 (-1) | 8 (-1) |

    **Challenge** 1/4 (50 XP)

    ### Actions

    ***Scimitar***. *Melee Weapon Attack:* +4 to hit, reach 5 ft., one target. *Hit:* 5 (1d6 + 2) slashing damage.

    ***Shortbow***. *Ranged Weapon Attack:* +4 to hit, range 80/320 ft., one target. *Hit:* 5 (1d6 + 2) piercing damage.
""")

_ZOMBIE_MD = textwrap.dedent("""\
    ## Zombie

    *Medium undead, neutral evil*

    **Armor Class** 8

    **Hit Points** 22 (3d8 + 9)

    | STR | DEX | CON | INT | WIS | CHA |
    |-----|-----|-----|-----|-----|-----|
    | 13 (+1) | 6 (-2) | 16 (+3) | 3 (-4) | 6 (-2) | 5 (-3) |

    **Challenge** 1/4 (50 XP)

    ### Actions

    ***Slam***. *Melee Weapon Attack:* +3 to hit, reach 5 ft., one target. *Hit:* 4 (1d6 + 1) bludgeoning damage.
""")


@pytest.fixture
def goblin_file(tmp_path: Path) -> Path:
    p = tmp_path / "Goblin.md"
    p.write_text(_GOBLIN_MD, encoding="utf-8")
    return p


@pytest.fixture
def zombie_file(tmp_path: Path) -> Path:
    p = tmp_path / "Zombie.md"
    p.write_text(_ZOMBIE_MD, encoding="utf-8")
    return p


def test_load_by_path_returns_actor_state(goblin_file: Path) -> None:
    actor = load_by_path(goblin_file)
    assert isinstance(actor, ActorState)


def test_load_by_path_actor_id_from_filename(goblin_file: Path) -> None:
    actor = load_by_path(goblin_file)
    assert actor.actor_id == "npc:goblin"


def test_load_by_path_name_from_filename(goblin_file: Path) -> None:
    actor = load_by_path(goblin_file)
    assert actor.name == "Goblin"


def test_load_by_path_actor_type_is_npc(goblin_file: Path) -> None:
    actor = load_by_path(goblin_file)
    assert actor.actor_type == ActorType.NPC


def test_load_by_path_parses_armor_class(goblin_file: Path) -> None:
    actor = load_by_path(goblin_file)
    assert actor.armor_class == _GOBLIN_AC


def test_load_by_path_parses_hp_max(goblin_file: Path) -> None:
    actor = load_by_path(goblin_file)
    assert actor.hp_max == _GOBLIN_HP


def test_load_by_path_hp_current_equals_hp_max(goblin_file: Path) -> None:
    actor = load_by_path(goblin_file)
    assert actor.hp_current == actor.hp_max


def test_load_by_path_parses_dex_initiative_bonus(goblin_file: Path) -> None:
    # DEX 14 → modifier +2
    actor = load_by_path(goblin_file)
    assert actor.initiative_bonus == _GOBLIN_DEX_MOD


def test_load_by_path_parses_negative_initiative(zombie_file: Path) -> None:
    # Zombie DEX 6 → modifier -2
    actor = load_by_path(zombie_file)
    assert actor.initiative_bonus == _ZOMBIE_DEX_MOD


def test_load_by_path_parses_melee_attack(goblin_file: Path) -> None:
    actor = load_by_path(goblin_file)
    scimitar = next(w for w in actor.equipped_weapons if w.name == "Scimitar")
    assert scimitar.attack_bonus == _GOBLIN_SCIMITAR_BONUS
    assert scimitar.damage_dice == "1d6"
    assert scimitar.damage_bonus == _GOBLIN_SCIMITAR_DAMAGE_BONUS
    assert scimitar.damage_type == "slashing"


def test_load_by_path_parses_ranged_attack(goblin_file: Path) -> None:
    actor = load_by_path(goblin_file)
    shortbow = next(w for w in actor.equipped_weapons if w.name == "Shortbow")
    assert shortbow.attack_bonus == _GOBLIN_SHORTBOW_BONUS


def test_load_by_path_sets_compendium_text(goblin_file: Path) -> None:
    actor = load_by_path(goblin_file)
    assert actor.compendium_text is not None
    assert "Goblin" in actor.compendium_text


def test_load_by_path_zombie_slam(zombie_file: Path) -> None:
    actor = load_by_path(zombie_file)
    slam = next(w for w in actor.equipped_weapons if w.name == "Slam")
    assert slam.attack_bonus == _ZOMBIE_SLAM_BONUS
    assert slam.damage_dice == "1d6"
    assert slam.damage_bonus == _ZOMBIE_SLAM_DAMAGE_BONUS
    assert slam.damage_type == "bludgeoning"


def test_load_by_name_returns_actor(tmp_path: Path) -> None:
    monster_dir = tmp_path / "monsters_dir"
    monster_dir.mkdir()
    goblin_path = monster_dir / "Goblin.md"
    goblin_path.write_text(_GOBLIN_MD, encoding="utf-8")

    index_dir = tmp_path / "data" / "compendium" / "monsters"
    index_dir.mkdir(parents=True)
    index_path = index_dir / "index.json"
    index_path.write_text(
        json.dumps(
            [
                {
                    "name": "Goblin",
                    "cr": "1/4",
                    "type": "humanoid",
                    "file": str(goblin_path),
                }
            ]
        )
    )

    actor = load_by_name("Goblin", index_path=index_path)
    assert actor.name == "Goblin"
    assert actor.hp_max == _GOBLIN_HP


def test_load_by_name_raises_on_unknown_monster(tmp_path: Path) -> None:
    index_path = tmp_path / "index.json"
    index_path.write_text(json.dumps([]))

    with pytest.raises(KeyError, match="Dragon"):
        load_by_name("Dragon", index_path=index_path)


def test_load_by_name_case_insensitive(tmp_path: Path) -> None:
    monster_dir = tmp_path / "monsters_dir"
    monster_dir.mkdir()
    goblin_path = monster_dir / "Goblin.md"
    goblin_path.write_text(_GOBLIN_MD, encoding="utf-8")

    index_path = tmp_path / "index.json"
    index_path.write_text(
        json.dumps(
            [
                {
                    "name": "Goblin",
                    "cr": "1/4",
                    "type": "humanoid",
                    "file": str(goblin_path),
                }
            ]
        )
    )

    actor = load_by_name("goblin", index_path=index_path)
    assert actor.hp_max == _GOBLIN_HP
