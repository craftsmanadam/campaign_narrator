# Anchor Extraction in `load_reference_text` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modify `load_reference_text` so that references containing `#Heading` return only the text of the matching section rather than the full file, falling back to the full file with a warning when the anchor is not found.

**Architecture:** `load_reference_text` gains anchor-awareness: when a `#` is present it calls the new private helper `_extract_section(text, anchor)` which scans for the first case-insensitive heading match and returns lines up to the next same-or-higher-level heading. No public API changes — all existing callers work without modification.

**Tech Stack:** Python 3, `logging` (stdlib), pytest.

---

## File Map

| Action | Path |
|---|---|
| Modify | `app/campaignnarrator/repositories/compendium_repository.py` |
| Modify | `tests/unit/test_compendium_repository.py` |

---

## Task 1: Implement anchor extraction in `load_reference_text`

**Files:**
- Modify: `app/campaignnarrator/repositories/compendium_repository.py`
- Test: `tests/unit/test_compendium_repository.py`

**Context:**

`load_reference_text` currently lives in `CompendiumRepository` at the bottom of `compendium_repository.py`. It strips the anchor and returns the full file. The method signature must not change. The private helper `_extract_section` is not tested directly — all tests go through `load_reference_text`.

The existing test `test_load_reference_text_strips_anchor_before_path_resolution` passes anchor `#Sneak-Attack` (hyphen) against `Rogue.md` which has heading `### Sneak Attack` (space). These do not match, so the fallback fires and the equality assertion continues to hold — no change needed to that test.

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_compendium_repository.py` after the existing `load_reference_text` tests:

```python
def test_load_reference_text_returns_section_when_anchor_matches(
    tmp_path: Path,
) -> None:
    wiki = tmp_path / "DND.SRD.Wiki-0.5.2"
    wiki.mkdir(parents=True)
    (wiki / "Fighter.md").write_text(
        "# Fighter\n\n"
        "### Action Surge\n\n"
        "Push yourself beyond your limits.\n\n"
        "### Second Wind\n\n"
        "Regain hit points.\n"
    )
    repo = CompendiumRepository(tmp_path)
    result = repo.load_reference_text(
        "DND.SRD.Wiki-0.5.2/Fighter.md#Action Surge"
    )
    assert "Action Surge" in result
    assert "Push yourself beyond your limits." in result
    assert "Second Wind" not in result


def test_load_reference_text_anchor_match_is_case_insensitive(
    tmp_path: Path,
) -> None:
    wiki = tmp_path / "DND.SRD.Wiki-0.5.2"
    wiki.mkdir(parents=True)
    (wiki / "Fighter.md").write_text(
        "# Fighter\n\n"
        "### Action Surge\n\n"
        "Push yourself beyond your limits.\n\n"
        "### Second Wind\n\n"
        "Regain hit points.\n"
    )
    repo = CompendiumRepository(tmp_path)
    result = repo.load_reference_text(
        "DND.SRD.Wiki-0.5.2/Fighter.md#action surge"
    )
    assert "Action Surge" in result
    assert "Push yourself beyond your limits." in result
    assert "Second Wind" not in result


def test_load_reference_text_section_ends_at_same_level_heading(
    tmp_path: Path,
) -> None:
    wiki = tmp_path / "DND.SRD.Wiki-0.5.2"
    wiki.mkdir(parents=True)
    (wiki / "Feats.md").write_text(
        "# Feats\n\n"
        "## Grappler\n\n"
        "Grappling rules.\n\n"
        "## Alert\n\n"
        "Initiative rules.\n"
    )
    repo = CompendiumRepository(tmp_path)
    result = repo.load_reference_text(
        "DND.SRD.Wiki-0.5.2/Feats.md#Grappler"
    )
    assert "Grappler" in result
    assert "Grappling rules." in result
    assert "Alert" not in result


def test_load_reference_text_section_ends_at_higher_level_heading(
    tmp_path: Path,
) -> None:
    wiki = tmp_path / "DND.SRD.Wiki-0.5.2"
    wiki.mkdir(parents=True)
    (wiki / "Classes.md").write_text(
        "# Classes\n\n"
        "## Fighter\n\n"
        "### Action Surge\n\n"
        "Push yourself.\n\n"
        "## Rogue\n\n"
        "Sneaky.\n"
    )
    repo = CompendiumRepository(tmp_path)
    result = repo.load_reference_text(
        "DND.SRD.Wiki-0.5.2/Classes.md#Action Surge"
    )
    assert "Action Surge" in result
    assert "Push yourself." in result
    assert "Rogue" not in result


def test_load_reference_text_section_includes_deeper_headings(
    tmp_path: Path,
) -> None:
    wiki = tmp_path / "DND.SRD.Wiki-0.5.2"
    wiki.mkdir(parents=True)
    (wiki / "Fighter.md").write_text(
        "# Fighter\n\n"
        "## Martial Archetypes\n\n"
        "Overview text.\n\n"
        "### Champion\n\n"
        "Champion details.\n\n"
        "#### Improved Critical\n\n"
        "Crit on 19 or 20.\n\n"
        "## Rogue\n\n"
        "Sneak attack.\n"
    )
    repo = CompendiumRepository(tmp_path)
    result = repo.load_reference_text(
        "DND.SRD.Wiki-0.5.2/Fighter.md#Martial Archetypes"
    )
    assert "Martial Archetypes" in result
    assert "Champion" in result
    assert "Improved Critical" in result
    assert "Crit on 19 or 20." in result
    assert "Rogue" not in result


def test_load_reference_text_falls_back_to_full_file_when_anchor_not_found(
    tmp_path: Path,
) -> None:
    wiki = tmp_path / "DND.SRD.Wiki-0.5.2"
    wiki.mkdir(parents=True)
    content = "# Fighter\n\nSome content.\n"
    (wiki / "Fighter.md").write_text(content)
    repo = CompendiumRepository(tmp_path)
    result = repo.load_reference_text(
        "DND.SRD.Wiki-0.5.2/Fighter.md#Nonexistent Heading"
    )
    assert result == content
```

- [ ] **Step 2: Run the new tests to verify they fail**

```bash
poetry run pytest \
  tests/unit/test_compendium_repository.py::test_load_reference_text_returns_section_when_anchor_matches \
  tests/unit/test_compendium_repository.py::test_load_reference_text_anchor_match_is_case_insensitive \
  tests/unit/test_compendium_repository.py::test_load_reference_text_section_ends_at_same_level_heading \
  tests/unit/test_compendium_repository.py::test_load_reference_text_section_ends_at_higher_level_heading \
  tests/unit/test_compendium_repository.py::test_load_reference_text_section_includes_deeper_headings \
  tests/unit/test_compendium_repository.py::test_load_reference_text_falls_back_to_full_file_when_anchor_not_found \
  -v
```

Expected: all 6 FAIL (the first 5 because the section is not extracted; the last because anchor absence currently returns full file but the assertion checks `result == content` which may accidentally pass — verify it fails or note it may already pass).

- [ ] **Step 3: Add logger and implement `_extract_section` and modify `load_reference_text`**

At the top of `app/campaignnarrator/repositories/compendium_repository.py`, after the existing imports, add:

```python
import logging

_logger = logging.getLogger(__name__)
```

Replace the existing `load_reference_text` method with:

```python
def load_reference_text(self, reference: str) -> str:
    """Load the text of a compendium reference, extracting the anchored section if present.

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
```

Add `_extract_section` as a private method after `load_reference_text`:

```python
def _extract_section(self, text: str, anchor: str) -> str | None:
    """Return the section under the first heading matching anchor (case-insensitive).

    Collects lines from the matching heading until the next heading at the
    same or higher level (same or fewer '#' characters), or end of file.
    Returns None if no heading matches.
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
```

- [ ] **Step 4: Run the new tests to verify they pass**

```bash
poetry run pytest \
  tests/unit/test_compendium_repository.py::test_load_reference_text_returns_section_when_anchor_matches \
  tests/unit/test_compendium_repository.py::test_load_reference_text_anchor_match_is_case_insensitive \
  tests/unit/test_compendium_repository.py::test_load_reference_text_section_ends_at_same_level_heading \
  tests/unit/test_compendium_repository.py::test_load_reference_text_section_ends_at_higher_level_heading \
  tests/unit/test_compendium_repository.py::test_load_reference_text_section_includes_deeper_headings \
  tests/unit/test_compendium_repository.py::test_load_reference_text_falls_back_to_full_file_when_anchor_not_found \
  -v
```

Expected: all 6 PASS.

- [ ] **Step 5: Run the full unit test suite**

```bash
make unit_test
```

Expected: all tests pass, coverage ≥ 90%.

- [ ] **Step 6: Run the linter**

```bash
make analyze_code
```

Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add \
  app/campaignnarrator/repositories/compendium_repository.py \
  tests/unit/test_compendium_repository.py
git commit -m "feat: add anchor extraction to load_reference_text"
```
