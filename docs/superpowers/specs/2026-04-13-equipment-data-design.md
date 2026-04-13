# Equipment Data Population Design

**Date:** 2026-04-13
**Status:** Approved
**Slice:** Backlog item 6 — populate `equipment/armor.json` and `equipment/weapons.json`

---

## Problem

`data/compendium/equipment/armor.json` and `data/compendium/equipment/weapons.json` exist but contain empty arrays. `CompendiumRepository.load_equipment_context` already loads and serializes entries from the `equipment/` directory, but without data it returns missing-context markers. The combat adjudication slice (backlog item 1) requires structured weapon and armor data so the LLM can resolve attack rolls, damage dice, AC calculations, and property interactions.

---

## Goal

Populate both files with the full SRD equipment set and enrich every entry with a `reference` field. No code changes — the repository layer is already capable of serving this data.

---

## Scope

- `data/compendium/equipment/armor.json` — 13 entries (all SRD armor types including shield)
- `data/compendium/equipment/weapons.json` — 37 entries (all SRD weapons)
- Data contract tests and repository spot-check tests
- No orchestrator wiring — that belongs to the combat slice

---

## Data Schema

### `armor.json`

Top-level shape: `{"armor": [...]}`.

Each entry:

```json
{
  "item_id": "chain-mail",
  "name": "Chain Mail",
  "category": "heavy",
  "ac_formula": "16",
  "strength_requirement": 13,
  "stealth_disadvantage": true,
  "reference": "DND.SRD.Wiki-0.5.2/Equipment/Armor.md"
}
```

| Field | Type | Notes |
|---|---|---|
| `item_id` | string | kebab-case, unique |
| `name` | string | display name |
| `category` | string | `light`, `medium`, `heavy`, or `shield` |
| `ac_formula` | string | LLM-readable: `"11 + Dex modifier"`, `"14 + Dex modifier (max 2)"`, `"16"`, `"+2"` |
| `strength_requirement` | int \| null | minimum Strength score or null |
| `stealth_disadvantage` | bool | true when armor imposes disadvantage on Stealth |
| `reference` | string | `DND.SRD.Wiki-0.5.2/Equipment/Armor.md` (all entries; no anchor — individual items have no wiki headings) |

**`ac_formula` values by category:**
- Light: `"<N> + Dex modifier"` (no cap)
- Medium: `"<N> + Dex modifier (max 2)"`
- Heavy: `"<N>"` (flat integer)
- Shield: `"+2"` (additive bonus)

### `weapons.json`

Top-level shape: `{"weapons": [...]}`.

Each entry:

```json
{
  "item_id": "longsword",
  "name": "Longsword",
  "category": "martial_melee",
  "damage_dice": "1d8",
  "damage_type": "slashing",
  "properties": ["versatile (1d10)"],
  "reference": "DND.SRD.Wiki-0.5.2/Equipment/Weapons.md"
}
```

| Field | Type | Notes |
|---|---|---|
| `item_id` | string | kebab-case, unique |
| `name` | string | display name |
| `category` | string | `simple_melee`, `simple_ranged`, `martial_melee`, `martial_ranged` |
| `damage_dice` | string \| null | e.g. `"1d8"`, `"2d6"`, `"1"` (blowgun), null (net) |
| `damage_type` | string \| null | `"slashing"`, `"piercing"`, `"bludgeoning"`, null (net) |
| `properties` | array of strings | each property as a discrete string; data-bearing properties include their data inline: `"versatile (1d10)"`, `"thrown (range 20/60)"`, `"ammunition (range 80/320)"` |
| `reference` | string | `DND.SRD.Wiki-0.5.2/Equipment/Weapons.md` (all entries) |

**`properties` encoding:** data-bearing properties embed their values inline so the LLM can reason over discrete tokens:

```json
["finesse", "light", "thrown (range 20/60)"]
["versatile (1d10)"]
["ammunition (range 150/600)", "heavy", "two-handed"]
```

---

## Complete Entry Lists

### Armor (13 entries)

| item_id | name | category | ac_formula | str_req | stealth_disadv |
|---|---|---|---|---|---|
| padded | Padded | light | 11 + Dex modifier | null | true |
| leather | Leather | light | 11 + Dex modifier | null | false |
| studded-leather | Studded Leather | light | 12 + Dex modifier | null | false |
| hide | Hide | medium | 12 + Dex modifier (max 2) | null | false |
| chain-shirt | Chain Shirt | medium | 13 + Dex modifier (max 2) | null | false |
| scale-mail | Scale Mail | medium | 14 + Dex modifier (max 2) | null | true |
| breastplate | Breastplate | medium | 14 + Dex modifier (max 2) | null | false |
| half-plate | Half Plate | medium | 15 + Dex modifier (max 2) | null | true |
| ring-mail | Ring Mail | heavy | 14 | null | true |
| chain-mail | Chain Mail | heavy | 16 | 13 | true |
| splint | Splint | heavy | 17 | 15 | true |
| plate | Plate | heavy | 18 | 15 | true |
| shield | Shield | shield | +2 | null | false |

### Weapons (37 entries)

**Simple Melee (10):** club, dagger, greatclub, handaxe, javelin, light-hammer, mace, quarterstaff, sickle, spear

**Simple Ranged (4):** light-crossbow, dart, shortbow, sling

**Martial Melee (18):** battleaxe, flail, glaive, greataxe, greatsword, halberd, lance, longsword, maul, morningstar, pike, rapier, scimitar, shortsword, trident, war-pick, warhammer, whip

**Martial Ranged (5):** blowgun, hand-crossbow, heavy-crossbow, longbow, net

---

## Repository Layer

No code changes required. `CompendiumRepository.load_equipment_context(item_ids)` already:
1. Globs `data/compendium/equipment/*.json`
2. Falls back to all list values when the collection key `"equipment"` is not found — correctly loading both `{"armor": [...]}` and `{"weapons": [...]}` entries
3. Indexes entries by `item_id` and serializes matches as JSON strings

---

## Testing

**`tests/unit/test_data_contracts.py`** — data shape validation:

- All armor entries have all required fields (`item_id`, `name`, `category`, `ac_formula`, `strength_requirement`, `stealth_disadvantage`, `reference`)
- All armor `category` values are in `{"light", "medium", "heavy", "shield"}`
- All weapon entries have all required fields (`item_id`, `name`, `category`, `damage_dice`, `damage_type`, `properties`, `reference`)
- All weapon `category` values are in `{"simple_melee", "simple_ranged", "martial_melee", "martial_ranged"}`
- All `properties` values are arrays

**`tests/unit/test_compendium_repository.py`** — repository behavior with real data:

- `load_equipment_context(("longsword",))` returns a tuple whose first element is a JSON string containing `"longsword"` and `"1d8"`
- `load_equipment_context(("chain-mail",))` returns a tuple whose first element contains `"chain-mail"` and `"16"`
- `load_equipment_context(("dagger",))` first element contains `"finesse"`
- `load_equipment_context(("nonexistent-item",))` returns the missing-context marker

---

## Files

| Action | Path |
|---|---|
| Populate | `data/compendium/equipment/armor.json` |
| Populate | `data/compendium/equipment/weapons.json` |
| Modify | `tests/unit/test_data_contracts.py` |
| Modify | `tests/unit/test_compendium_repository.py` |

---

## Non-Goals

- Typed `ArmorEntry`/`WeaponEntry` dataclasses — not needed until the combat slice requires typed access
- Wiring `load_equipment_context` into the orchestrator — combat slice
- Populating `adventuring_gear.json` or `tools.json` — not required for combat adjudication
- `magic_items/` population — backlog item 7

---

## Next Slice

Backlog item 1: full combat resolution scenario. This slice's structured weapon data (damage dice, properties) and armor data (AC formula) enable the LLM adjudicator to resolve attack rolls, damage calculation, and AC checks for the Fighter vs goblin scout encounter.
