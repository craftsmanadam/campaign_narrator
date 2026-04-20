"""Unit tests for monster_index_parser."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

from campaignnarrator.tools.monster_index_parser import (
    build_index,
    parse_monster_file,
    write_index,
)


def _make_file(tmp_path: Path, filename: str, content: str) -> Path:
    p = tmp_path / filename
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


def test_parse_extracts_name(tmp_path: Path) -> None:
    p = _make_file(
        tmp_path,
        "Goblin.md",
        """\
        ## Goblin

        *Small humanoid (goblinoid), neutral evil*

        **Armor Class** 15

        **Challenge** 1/4 (50 XP)
        """,
    )
    assert parse_monster_file(p)["name"] == "Goblin"


def test_parse_extracts_cr(tmp_path: Path) -> None:
    p = _make_file(
        tmp_path,
        "Goblin.md",
        """\
        ## Goblin

        *Small humanoid (goblinoid), neutral evil*

        **Challenge** 1/4 (50 XP)
        """,
    )
    assert parse_monster_file(p)["cr"] == "1/4"


def test_parse_extracts_type(tmp_path: Path) -> None:
    p = _make_file(
        tmp_path,
        "Goblin.md",
        """\
        ## Goblin

        *Small humanoid (goblinoid), neutral evil*

        **Challenge** 1/4 (50 XP)
        """,
    )
    assert parse_monster_file(p)["type"] == "humanoid"


def test_parse_three_hash_heading(tmp_path: Path) -> None:
    p = _make_file(
        tmp_path,
        "Zombie.md",
        """\
        ### Zombie

        *Medium undead, neutral evil*

        **Challenge** 1/4 (50 XP)
        """,
    )
    result = parse_monster_file(p)
    assert result["name"] == "Zombie"
    assert result["type"] == "undead"


def test_parse_integer_cr(tmp_path: Path) -> None:
    p = _make_file(
        tmp_path,
        "Xorn.md",
        """\
        ## Xorn

        *Medium elemental, neutral*

        **Challenge** 5 (1,800 XP)
        """,
    )
    assert parse_monster_file(p)["cr"] == "5"


def test_parse_returns_none_for_meta_file(tmp_path: Path) -> None:
    p = _make_file(
        tmp_path,
        "Statistics.md",
        """\
        # Monster Statistics

        A monster's statistics, sometimes referred to as its **stat block**...
        """,
    )
    assert parse_monster_file(p) is None


def test_parse_returns_none_when_missing_challenge(tmp_path: Path) -> None:
    p = _make_file(
        tmp_path,
        "Customizing.md",
        """\
        ### Customizing NPCs

        There are many easy ways to customize the NPCs...
        """,
    )
    assert parse_monster_file(p) is None


def test_parse_file_field_contains_path(tmp_path: Path) -> None:
    p = _make_file(
        tmp_path,
        "Goblin.md",
        """\
        ## Goblin

        *Small humanoid (goblinoid), neutral evil*

        **Challenge** 1/4 (50 XP)
        """,
    )
    result = parse_monster_file(p)
    assert result["file"] == str(p)


_GOBLIN_MD = (
    "## Goblin\n\n"
    "*Small humanoid (goblinoid), neutral evil*\n\n"
    "**Challenge** 1/4 (50 XP)\n"
)
_ZOMBIE_MD = (
    "### Zombie\n\n*Medium undead, neutral evil*\n\n**Challenge** 1/4 (50 XP)\n"
)


def test_build_index_skips_meta_files(tmp_path: Path) -> None:
    _make_file(tmp_path, "Statistics.md", "# Monster Statistics\n\nSome text.\n")
    _make_file(tmp_path, "Goblin.md", _GOBLIN_MD)
    result = build_index(tmp_path)
    assert len(result) == 1
    assert result[0]["name"] == "Goblin"


def test_build_index_entries_sorted_by_filename(tmp_path: Path) -> None:
    _make_file(tmp_path, "Zombie.md", _ZOMBIE_MD)
    _make_file(tmp_path, "Goblin.md", _GOBLIN_MD)
    result = build_index(tmp_path)
    assert [e["name"] for e in result] == ["Goblin", "Zombie"]


def test_parse_single_hash_heading(tmp_path: Path) -> None:
    p = _make_file(
        tmp_path,
        "Adult Black Dragon.md",
        """\
        # Adult Black Dragon (Chromatic)

        *Huge dragon, chaotic evil*

        **Challenge** 14 (11,500 XP)
        """,
    )
    result = parse_monster_file(p)
    assert result is not None
    assert result["name"] == "Adult Black Dragon (Chromatic)"
    assert result["type"] == "dragon"


def test_parse_single_hash_meta_file_still_returns_none(tmp_path: Path) -> None:
    p = _make_file(
        tmp_path,
        "Statistics.md",
        """\
        # Monster Statistics

        A monster's statistics, sometimes referred to as its **stat block**...
        """,
    )
    assert parse_monster_file(p) is None


def test_write_index_creates_output_file(tmp_path: Path) -> None:
    monsters_dir = tmp_path / "monsters"
    monsters_dir.mkdir()
    (monsters_dir / "Goblin.md").write_text(_GOBLIN_MD, encoding="utf-8")
    output_file = tmp_path / "out" / "index.json"
    count = write_index(output_file=output_file, monsters_dir=monsters_dir)
    assert output_file.exists()
    assert count == 1


def test_write_index_output_is_valid_json(tmp_path: Path) -> None:
    monsters_dir = tmp_path / "monsters"
    monsters_dir.mkdir()
    (monsters_dir / "Goblin.md").write_text(_GOBLIN_MD, encoding="utf-8")
    output_file = tmp_path / "index.json"
    write_index(output_file=output_file, monsters_dir=monsters_dir)
    data = json.loads(output_file.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert data[0]["name"] == "Goblin"


def test_write_index_creates_parent_directories(tmp_path: Path) -> None:
    monsters_dir = tmp_path / "monsters"
    monsters_dir.mkdir()
    (monsters_dir / "Goblin.md").write_text(_GOBLIN_MD, encoding="utf-8")
    output_file = tmp_path / "deeply" / "nested" / "index.json"
    write_index(output_file=output_file, monsters_dir=monsters_dir)
    assert output_file.exists()


def test_parse_challenge_beyond_line_25(tmp_path: Path) -> None:
    """Verify that Challenge line is parsed even after line 25."""
    # Simulate a monster file where Challenge appears on line 30
    lines = ["## Lich", "", "*Medium undead, any evil alignment*", ""]
    lines += [""] * 26  # pad to push Challenge past line 25
    lines += ["**Challenge** 21 (33,000 XP)"]
    p = tmp_path / "Lich.md"
    p.write_text("\n".join(lines), encoding="utf-8")
    result = parse_monster_file(p)
    assert result is not None
    assert result["name"] == "Lich"
    assert result["cr"] == "21"
