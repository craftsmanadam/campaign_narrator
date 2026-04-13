# Anchor Extraction in `load_reference_text` Design

**Date:** 2026-04-13
**Status:** Approved
**Slice:** Backlog item 4 — resolve `file.md#Heading` references to the specific section

---

## Problem

`load_reference_text` currently strips the `#anchor` suffix before resolving the path and returns the entire file. The enriched compendium references added in backlog item 2 include anchors such as `Classes/Fighter.md#Action Surge` and `Characterizations/Feats.md#Grappler`. Without anchor extraction, the orchestrator loads full wiki files (often several kilobytes) when it only needs a single section — wasting context window and diluting the signal available to the LLM adjudicator.

---

## Goal

When `load_reference_text` receives a reference containing `#`, return only the text of the section under the matching heading instead of the full file. References without `#` are unaffected.

---

## Design

### `load_reference_text` (modified)

Existing signature and caller contract are unchanged:

```python
def load_reference_text(self, reference: str) -> str
```

Behavior after this change:

1. Split on `#` to separate the file path and optional anchor.
2. Load the file at the resolved path (unchanged).
3. If no anchor is present, return the full file text (unchanged).
4. If an anchor is present, call `_extract_section(text, anchor)`.
5. If `_extract_section` returns a section, return it.
6. If `_extract_section` returns `None` (anchor not found), log a `WARNING` and return the full file text as a fallback.

### `_extract_section(text, anchor)` (new private helper)

```python
def _extract_section(self, text: str, anchor: str) -> str | None
```

Responsibility: given raw markdown text and an anchor string, return the section under the first matching heading, or `None` if no match.

**Matching rule:** scan lines for the first heading line (starts with one or more `#` followed by a space) whose text — after stripping leading `#` characters and whitespace — matches `anchor` case-insensitively.

**Section boundary rule:** once the matching heading is found, collect lines (including the heading line) until a subsequent heading with the same or fewer `#` characters is encountered, or until end of file. Deeper headings (more `#`) are included in the section body.

**Returns:** the collected lines joined as a string, or `None` if no heading matched.

### Anchor format

Anchors in the enriched compendium data use spaces (e.g., `#Action Surge`, `#Eldritch Invocations`). Wiki headings also use spaces. No slug conversion is required.

### Logging

Uses the standard `logging` module at `WARNING` level. Logger name: `campaignnarrator.repositories.compendium_repository`. Message format:

```
anchor '%s' not found in '%s'; returning full file
```

No new dependencies are introduced.

---

## Fallback Behaviour

| Situation | Result |
|---|---|
| No anchor in reference | Full file returned (unchanged) |
| Anchor matches a heading | Section text returned |
| Anchor not found in file | Full file returned + WARNING logged |
| File not found | `FileNotFoundError` raised (unchanged) |

The fallback ensures the orchestrator always receives usable context even when an anchor is stale or malformed.

---

## Files

| Action | Path |
|---|---|
| Modify | `app/campaignnarrator/repositories/compendium_repository.py` |
| Modify | `tests/unit/test_compendium_repository.py` |

---

## Testing

All tests exercise `load_reference_text` — `_extract_section` is not tested directly.

Unit tests using `tmp_path` (synthetic markdown):

- Anchor present, heading found → returns only the section text
- Anchor matches heading at `##` level → correct section extracted
- Anchor matches heading at `###` level → correct section extracted
- Anchor match is case-insensitive → `#action surge` finds `### Action Surge`
- Anchor present, heading not found → returns full file (fallback)
- No anchor → returns full file unchanged
- Section ends at the next same-level heading (does not include it)
- Section ends at a higher-level heading (fewer `#`)
- Deeper headings within the section are included in the returned text

Existing tests are unaffected:
- `test_load_reference_text_returns_file_content_for_rogue` — no anchor, full file
- `test_load_reference_text_strips_anchor_before_path_resolution` — anchor not found in Rogue.md → fallback returns full file, equality holds
- `test_load_reference_text_raises_for_missing_file` — file not found path unchanged
- `test_load_reference_text_resolves_grappler_feat_reference` — asserts `"Grappler" in text`; after this change returns the Grappler section, which still contains "Grappler"

---

## Non-Goals

- Slug-style anchor conversion (e.g., `#action-surge` → `Action Surge`) — anchors in the enriched data already use spaces
- Multiple section extraction — first match only
- Anchor extraction for `rules/` files — rules files are loaded by topic, not by anchor
- Any changes to orchestrator routing or prompt construction

---

## Next Slice

Backlog item 6: populate `equipment/armor.json` and `equipment/weapons.json` with structured entries and enrich with reference fields — required for combat adjudication.
