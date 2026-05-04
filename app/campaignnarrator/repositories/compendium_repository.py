"""File-backed compendium repository."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, ClassVar

from campaignnarrator.domain.models.background_entry import BackgroundEntry
from campaignnarrator.domain.models.class_entry import ClassEntry
from campaignnarrator.domain.models.feat_entry import FeatEntry

_logger = logging.getLogger(__name__)


class CompendiumRepository:
    """Load compendium entries from a repository root."""

    _VALID_MAGIC_ITEM_RARITIES: ClassVar[frozenset[str]] = frozenset(
        {"common", "uncommon", "rare"}
    )
    _MISSING_CONTEXT_MARKER: ClassVar[str] = "Missing compendium context:"
    _MISSING_RULES_CONTEXT_MARKER: ClassVar[str] = "Missing rules context:"

    def __init__(self, root: Path | str) -> None:
        """Resolve the compendium root and rules sub-root for path validation."""
        self._root = Path(root)
        self._resolved_rules_root = (self._root / "rules").resolve()

    def monster_index_path(self) -> Path:
        """Return the absolute path to the monster compendium index."""
        return self._root / "monsters" / "index.json"

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

    def load_feat(self, feat_id: str) -> FeatEntry | None:
        """Return the feat entry for the given feat_id, or None if not found."""

        path = self._root / "character_options" / "feats.json"
        if not path.exists():
            return None
        payload = json.loads(path.read_text())
        for entry in payload.get("feats", []):
            if not isinstance(entry, dict):
                continue
            if entry.get("feat_id") == feat_id:
                ref = entry.get("reference")
                return FeatEntry(
                    feat_id=feat_id,
                    name=str(entry.get("name", "")),
                    summary=str(entry.get("summary", "")),
                    reference=ref if isinstance(ref, str) else None,
                )
        return None

    def load_reference_text(self, reference: str) -> str:
        """Load compendium reference text, extracting the anchored section if present.

        When the reference contains a '#anchor', returns only the section under
        the first case-insensitive heading match. Falls back to the full file
        (with a WARNING log) if the anchor is not found.
        Raises FileNotFoundError if the file does not exist.
        """

        parts = reference.split("#", maxsplit=1)
        path_part = parts[0]
        anchor = parts[1] if len(parts) > 1 else None

        resolved = self._root / path_part
        text = resolved.read_text()

        if anchor is None:
            return text

        section = self._extract_section(text, anchor)
        if section is not None:
            return section

        _logger.warning(
            "anchor '%s' not found in '%s'; returning full file", anchor, path_part
        )
        return text

    def load_rule_index(self) -> dict[str, list[str]]:
        """Return the generated rule index."""

        path = self._root / "rules" / "generated" / "rule_index.json"
        return json.loads(path.read_text())

    def load_rules_topic_markdown(self, relative_path: str | Path) -> str:
        """Return the raw markdown for a rule topic."""

        rules_root = self._root / "rules"
        candidate = (rules_root / Path(relative_path)).resolve()
        if self._resolved_rules_root not in candidate.parents and (
            candidate != self._resolved_rules_root
        ):
            raise ValueError
        return candidate.read_text()

    def load_rules_context_for_topics(self, topics: tuple[str, ...]) -> tuple[str, ...]:
        """Return loaded markdown context for the requested rule topics."""

        rule_index = self._load_rule_index_or_empty()
        contexts: list[str] = []
        for topic in topics:
            contexts.append(self._load_rules_topic_context(topic, rule_index))
        return tuple(contexts)

    def _load_rule_index_or_empty(self) -> dict[str, list[str]]:
        """Return the rule index, or an empty dict if the index file is missing."""
        try:
            return self.load_rule_index()
        except FileNotFoundError:
            return {}

    def _load_rules_topic_context(
        self,
        topic: str,
        rule_index: dict[str, list[str]],
    ) -> str:
        """Load and join all markdown files for topic; return missing marker if none."""
        relative_paths = rule_index.get(topic)
        if not relative_paths:
            return f"{self._MISSING_RULES_CONTEXT_MARKER} {topic}"

        topic_markdown: list[str] = []
        for relative_path in relative_paths:
            try:
                topic_markdown.append(self.load_rules_topic_markdown(relative_path))
            except (FileNotFoundError, ValueError) as exc:
                _logger.warning(
                    "Could not load rule topic %r (%r): %s",
                    topic,
                    relative_path,
                    exc,
                )
                return f"{self._MISSING_RULES_CONTEXT_MARKER} {topic}"
        return "\n\n".join(topic_markdown)

    def _extract_section(self, text: str, anchor: str) -> str | None:
        """Return the section under the first heading that matches anchor.

        Matching is case-insensitive. Collects lines from the matching heading
        until a heading at the same or higher level (same or fewer '#'
        characters), or end of file. Returns None if no heading matches.
        """

        anchor_lower = anchor.lower()
        lines = text.splitlines(keepends=True)
        start_idx: int | None = None
        start_level: int | None = None

        for i, line in enumerate(lines):
            stripped = line.lstrip()
            if not stripped.startswith("#"):
                continue
            level = len(stripped) - len(stripped.lstrip("#"))
            if level >= len(stripped) or stripped[level] != " ":
                continue  # not a valid ATX heading (needs space after #s)
            heading_text = stripped[level:].strip()

            if start_idx is None:
                if heading_text.lower() == anchor_lower:
                    start_idx = i
                    start_level = level
            elif start_level is not None and level <= start_level:
                return "".join(lines[start_idx:i])

        if start_idx is not None:
            return "".join(lines[start_idx:])
        return None

    def _load_compendium_entries(
        self,
        directory: Path,
        collection_key: str,
        id_key: str,
    ) -> dict[str, dict[str, Any]]:
        """Build an id-keyed dict from all JSON files in directory."""
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
        """Extract the entry list from a payload dict or list."""
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
        """Return JSON for entry_id or a missing-context marker string."""
        entry = entries.get(entry_id)
        if entry is None:
            return f"{self._MISSING_CONTEXT_MARKER} {entry_id}"
        return json.dumps(entry, sort_keys=True)
