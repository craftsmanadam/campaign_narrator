"""Monster loader: parses SRD markdown files into ActorState instances."""

from __future__ import annotations

import json
import re
from pathlib import Path

from campaignnarrator.domain.models import ActorState, ActorType, WeaponState

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

_AC_RE = re.compile(r"\*\*Armor Class\*\*\s+(\d+)")
_HP_RE = re.compile(r"\*\*Hit Points\*\*\s+(\d+)")

# DEX modifier: second group in parentheses on stat table data row
# | 8 (-1) | 14 (+2) | 10 (+0) | ...  → capture (+2)
_DEX_MOD_RE = re.compile(r"\|\s*\d+\s*\([+-]?\d+\)\s*\|\s*\d+\s*\(([+-]?\d+)\)")

# Attack line pattern:
# ***Name***. *Melee/Ranged Weapon Attack:* +N to hit...Hit: N (XdY + Z) type damage
_ATTACK_RE = re.compile(
    r"\*\*\*(.+?)\*\*\*\.\s+\*(Melee|Ranged) Weapon Attack:\*\s+\+(\d+) to hit"
    r".*?\*Hit:\*\s*\d+\s*\(([^)]+)\)\s*(\w+) damage"
)

# Default values for fields not parsed from markdown
_DEFAULT_ABILITY_SCORE = 10
_DEFAULT_PROFICIENCY_BONUS = 2
_DEFAULT_SPEED = 30
_DEFAULT_ATTACKS_PER_ACTION = 1


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _slugify(name: str) -> str:
    """Return a lowercase, hyphen-separated, alphanumeric-only slug."""
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def _parse_damage(expr: str) -> tuple[str, int]:
    """Parse a damage expression like '1d6 + 2' into (dice, bonus).

    Handles:
      - '1d6 + 2'  → ('1d6', 2)
      - '2d8 - 1'  → ('2d8', -1)
      - '1d4'      → ('1d4', 0)
    """
    if " + " in expr:
        dice, bonus_str = expr.split(" + ", 1)
        return dice.strip(), int(bonus_str.strip())
    if " - " in expr:
        dice, bonus_str = expr.split(" - ", 1)
        return dice.strip(), -int(bonus_str.strip())
    return expr.strip(), 0


def _parse_weapons(text: str) -> tuple[WeaponState, ...]:
    """Extract all weapon attacks from the markdown text."""
    weapons: list[WeaponState] = []
    for match in _ATTACK_RE.finditer(text):
        name = match.group(1)
        attack_bonus = int(match.group(3))
        damage_expr = match.group(4)
        damage_type = match.group(5)
        dice, bonus = _parse_damage(damage_expr)
        weapons.append(
            WeaponState(
                name=name,
                attack_bonus=attack_bonus,
                damage_dice=dice,
                damage_bonus=bonus,
                damage_type=damage_type,
                properties=(),
            )
        )
    return tuple(weapons)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_by_path(path: Path) -> ActorState:
    """Parse an SRD monster markdown file and return an ActorState.

    Parsed fields:
      - actor_id: derived from filename stem (e.g. 'Goblin.md' → 'npc:goblin')
      - name: filename stem (title-cased)
      - actor_type: always NPC
      - armor_class: from **Armor Class** line
      - hp_max / hp_current: from **Hit Points** line (integer, not average)
      - initiative_bonus: DEX modifier extracted from stat table
      - equipped_weapons: all ***Name***. *Melee/Ranged Weapon Attack* entries
      - compendium_text: full raw markdown content

    All other ability scores default to 10; proficiency_bonus defaults to 2.
    """
    raw_text = path.read_text(encoding="utf-8")
    name = path.stem

    ac_match = _AC_RE.search(raw_text)
    armor_class = int(ac_match.group(1)) if ac_match else 0

    hp_match = _HP_RE.search(raw_text)
    hp_max = int(hp_match.group(1)) if hp_match else 0

    dex_mod_match = _DEX_MOD_RE.search(raw_text)
    initiative_bonus = int(dex_mod_match.group(1)) if dex_mod_match else 0

    # Back-compute DEX score from modifier: score = 10 + modifier * 2
    dex_score = _DEFAULT_ABILITY_SCORE + initiative_bonus * 2

    weapons = _parse_weapons(raw_text)

    return ActorState(
        actor_id=f"npc:{_slugify(name)}",
        name=name,
        actor_type=ActorType.NPC,
        hp_max=hp_max,
        hp_current=hp_max,
        armor_class=armor_class,
        strength=_DEFAULT_ABILITY_SCORE,
        dexterity=dex_score,
        constitution=_DEFAULT_ABILITY_SCORE,
        intelligence=_DEFAULT_ABILITY_SCORE,
        wisdom=_DEFAULT_ABILITY_SCORE,
        charisma=_DEFAULT_ABILITY_SCORE,
        proficiency_bonus=_DEFAULT_PROFICIENCY_BONUS,
        initiative_bonus=initiative_bonus,
        speed=_DEFAULT_SPEED,
        attacks_per_action=_DEFAULT_ATTACKS_PER_ACTION,
        action_options=(),
        ac_breakdown=(),
        equipped_weapons=weapons,
        compendium_text=raw_text,
    )


def load_by_name(name: str, *, index_path: Path) -> ActorState:
    """Look up a monster by name in the index and return its ActorState.

    Args:
        name: The monster name (case-sensitive, must match the index).
        index_path: Path to the index.json file.

    Raises:
        KeyError: When the monster name is not found in the index.
    """
    entries: list[dict[str, str]] = json.loads(index_path.read_text(encoding="utf-8"))
    name_lower = name.lower()
    for entry in entries:
        if entry["name"].lower() == name_lower:
            file_value = entry["file"]
            file_path = Path(file_value)
            if not file_path.is_absolute():
                # Resolve relative path against the index file's parent directory
                file_path = index_path.parent / file_value
            return load_by_path(file_path)
    raise KeyError(name)


__all__ = ["load_by_name", "load_by_path"]
