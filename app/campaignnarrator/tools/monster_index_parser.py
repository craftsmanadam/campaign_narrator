"""Parse SRD monster markdown files to build a flat monster index."""

from __future__ import annotations

import json
import re
from pathlib import Path

_MONSTERS_DIR = Path("data/compendium/DND.SRD.Wiki-0.5.2/Monsters")
_OUTPUT_FILE = Path("data/compendium/monsters/index.json")

_NAME_RE = re.compile(r"^#{1,3}\s+(.+)$")
_TYPE_RE = re.compile(r"^\*\w+\s+(\w+)")
_CR_RE = re.compile(r"\*\*Challenge\*\*\s+([\d/]+)")


def parse_monster_file(path: Path) -> dict[str, str] | None:
    """Extract index fields from one SRD monster markdown file.

    Returns None when any required field is missing (meta-files, etc.).
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    name: str | None = None
    creature_type: str | None = None
    cr: str | None = None

    for line in lines:
        if name is None:
            m = _NAME_RE.match(line)
            if m:
                name = m.group(1).strip()
        if creature_type is None:
            m = _TYPE_RE.match(line)
            if m:
                creature_type = m.group(1).strip()
        if cr is None:
            m = _CR_RE.search(line)
            if m:
                cr = m.group(1).strip()

    if not (name and creature_type and cr):
        return None

    return {"name": name, "cr": cr, "type": creature_type, "file": str(path)}


def _relative_to_dir(path: Path, output_dir: Path) -> str:
    """Return *path* as a POSIX string relative to *output_dir*.

    Uses ``Path.relative_to(walk_up=True)`` (Python 3.12+) so that paths
    outside the output directory are expressed with leading ``..`` segments
    rather than raising ``ValueError``.
    """
    return path.relative_to(output_dir, walk_up=True).as_posix()


def build_index(
    monsters_dir: Path = _MONSTERS_DIR,
    *,
    output_dir: Path | None = None,
) -> list[dict[str, str]]:
    """Return index entries for every parseable monster in *monsters_dir*.

    When *output_dir* is provided, the ``file`` field in each entry is stored
    as a path relative to *output_dir* rather than relative to the current
    working directory.  This makes the index portable: after the data directory
    is copied elsewhere the loader can resolve paths correctly by joining the
    stored relative path with the index file's parent directory.
    """
    entries = []
    for path in sorted(monsters_dir.glob("*.md")):
        entry = parse_monster_file(path)
        if entry is not None:
            if output_dir is not None:
                entry = {**entry, "file": _relative_to_dir(path, output_dir)}
            entries.append(entry)
    return entries


def write_index(
    output_file: Path = _OUTPUT_FILE,
    monsters_dir: Path = _MONSTERS_DIR,
) -> int:
    """Write the monster index JSON to *output_file*. Returns entry count."""
    output_file.parent.mkdir(parents=True, exist_ok=True)
    index = build_index(monsters_dir, output_dir=output_file.parent)
    output_file.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    return len(index)
