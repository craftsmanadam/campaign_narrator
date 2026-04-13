"""File-backed compendium repository."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar


@dataclass(frozen=True, slots=True)
class ClassEntry:
    """Minimal class entry loaded from the compendium."""

    class_id: str
    name: str
    reference: str | None


@dataclass(frozen=True, slots=True)
class BackgroundEntry:
    """Minimal background entry loaded from the compendium."""

    background_id: str
    name: str
    reference: str | None


class CompendiumRepository:
    """Load compendium entries from a repository root."""

    _VALID_MAGIC_ITEM_RARITIES: ClassVar[frozenset[str]] = frozenset(
        {"common", "uncommon", "rare"}
    )
    _MISSING_CONTEXT_MARKER: ClassVar[str] = "Missing compendium context:"

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

    def load_equipment_context(self, item_ids: tuple[str, ...]) -> tuple[str, ...]:
        """Return JSON-serialized equipment context for the requested item IDs."""

        entries = self._load_compendium_entries(
            self._root / "equipment",
            "equipment",
            "item_id",
        )
        return tuple(
            self._serialize_compendium_entry(item_id, entries) for item_id in item_ids
        )

    def load_monster_context(self, monster_ids: tuple[str, ...]) -> tuple[str, ...]:
        """Return JSON-serialized monster context for the requested monster IDs."""

        entries = self._load_compendium_entries(
            self._root / "monsters",
            "monsters",
            "monster_id",
        )
        return tuple(
            self._serialize_compendium_entry(monster_id, entries)
            for monster_id in monster_ids
        )

    def load_class(self, class_id: str) -> ClassEntry | None:
        """Return the class entry for the given class_id, or None if not found."""

        path = self._root / "character_options" / "classes.json"
        if not path.exists():
            return None
        payload = json.loads(path.read_text())
        for entry in payload.get("classes", []):
            if not isinstance(entry, dict):
                continue
            if entry.get("class_id") == class_id:
                ref = entry.get("reference")
                return ClassEntry(
                    class_id=class_id,
                    name=str(entry.get("name", "")),
                    reference=ref if isinstance(ref, str) else None,
                )
        return None

    def load_background(self, background_id: str) -> BackgroundEntry | None:
        """Return the background entry for the given background_id, or None."""

        path = self._root / "character_options" / "backgrounds.json"
        if not path.exists():
            return None
        payload = json.loads(path.read_text())
        for entry in payload.get("backgrounds", []):
            if not isinstance(entry, dict):
                continue
            if entry.get("background_id") == background_id:
                ref = entry.get("reference")
                return BackgroundEntry(
                    background_id=background_id,
                    name=str(entry.get("name", "")),
                    reference=ref if isinstance(ref, str) else None,
                )
        return None

    def load_reference_text(self, reference: str) -> str:
        """Load the full text of a compendium reference file.

        Strips any #anchor suffix before resolving the path.
        Raises FileNotFoundError if the file does not exist.
        """

        path_part = reference.split("#", maxsplit=1)[0]
        resolved = self._root / path_part
        return resolved.read_text()

    def _load_compendium_entries(
        self,
        directory: Path,
        collection_key: str,
        id_key: str,
    ) -> dict[str, dict[str, Any]]:
        entries: dict[str, dict[str, Any]] = {}
        if not directory.exists():
            return entries

        for path in sorted(directory.glob("*.json")):
            payload = json.loads(path.read_text())
            for entry in self._iter_compendium_entries(payload, collection_key):
                if not isinstance(entry, dict):
                    continue
                entry_id = entry.get(id_key)
                if isinstance(entry_id, str) and entry_id not in entries:
                    entries[entry_id] = entry
        return entries

    def _iter_compendium_entries(
        self,
        payload: Any,
        collection_key: str,
    ) -> list[Any]:
        if isinstance(payload, dict):
            collection = payload.get(collection_key)
            if isinstance(collection, list):
                return collection
            list_values = [
                value for value in payload.values() if isinstance(value, list)
            ]
            if list_values:
                entries: list[Any] = []
                for value in list_values:
                    entries.extend(value)
                return entries
            return [payload]
        if isinstance(payload, list):
            return payload
        return []

    def _serialize_compendium_entry(
        self,
        entry_id: str,
        entries: dict[str, dict[str, Any]],
    ) -> str:
        entry = entries.get(entry_id)
        if entry is None:
            return f"{self._MISSING_CONTEXT_MARKER} {entry_id}"
        return json.dumps(entry, sort_keys=True)
