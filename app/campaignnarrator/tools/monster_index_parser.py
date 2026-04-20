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


def build_index(monsters_dir: Path = _MONSTERS_DIR) -> list[dict[str, str]]:
    """Return index entries for every parseable monster in *monsters_dir*."""
    entries = []
    for path in sorted(monsters_dir.glob("*.md")):
        entry = parse_monster_file(path)
        if entry is not None:
            entries.append(entry)
    return entries


def write_index(
    output_file: Path = _OUTPUT_FILE,
    monsters_dir: Path = _MONSTERS_DIR,
) -> int:
    """Write the monster index JSON to *output_file*. Returns entry count."""
    output_file.parent.mkdir(parents=True, exist_ok=True)
    index = build_index(monsters_dir)
    output_file.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    return len(index)
