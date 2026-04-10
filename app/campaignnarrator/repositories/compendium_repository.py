"""File-backed compendium repository."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar


class CompendiumRepository:
    """Load compendium entries from a repository root."""

    _VALID_MAGIC_ITEM_RARITIES: ClassVar[frozenset[str]] = frozenset(
        {"common", "uncommon", "rare"}
    )

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)

    def load_magic_item(self, rarity: str) -> dict[str, Any]:
        """Return the first magic item for a rarity bucket."""

        if rarity not in self._VALID_MAGIC_ITEM_RARITIES:
            raise ValueError
        path = self._root / "magic_items" / f"{rarity}.json"
        payload = json.loads(path.read_text())
        items = payload["magic_items"]
        if not items:
            raise ValueError
        item = items[0]
        if not isinstance(item, dict):
            raise TypeError
        return item

    def load_magic_item_by_id(self, item_id: str) -> dict[str, Any]:
        """Return the first magic item matching an item_id across rarity buckets."""

        if not item_id:
            raise ValueError
        magic_items_root = self._root / "magic_items"
        for path in sorted(magic_items_root.glob("*.json")):
            payload = json.loads(path.read_text())
            for item in payload.get("magic_items", []):
                if not isinstance(item, dict):
                    continue
                if item.get("item_id") == item_id:
                    return item
        raise ValueError
