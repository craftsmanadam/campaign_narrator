#!/usr/bin/env python3
"""Generate data/compendium/monsters/index.json from SRD monster markdown files.

Run from the project root:
    python bin/build_monster_index.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from campaignnarrator.tools.monster_index_parser import write_index

if __name__ == "__main__":
    count = write_index()
    print(f"Wrote {count} monsters to data/compendium/monsters/index.json")
