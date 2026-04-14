# Combat Pass 1: ActorState Character Sheet Model — Design Spec

**Date:** 2026-04-13
**Status:** Approved
**Slice:** Combat backlog item 1, Pass 1 of 3

---

## Problem

The current `ActorState` is a minimal stub (`hp_current`, `hp_max`, `armor_class`, `kind`, `inventory`). It cannot carry the information the Rules Agent and Narrator need to adjudicate combat: ability scores, saving throws, attack bonuses, damage dice, action economy resources, feats, or conditions beyond a simple string list. Every combat adjudication call would require expensive compendium lookups, and the LLM would have to reconstruct mechanical context from prose instead of structured data.

---

## Goal

Replace the stub `ActorState` with a full D&D 2024 character-sheet-equivalent model. All combat-relevant stats are baked into the actor at encounter setup time — no runtime compendium lookups during combat. Add companion value types (`FeatState`, `WeaponState`, `InitiativeTurn`) and replace the stringly-typed `initiative_order` on `EncounterState` with a structured `combat_turns` field.

No combat orchestration is implemented in this pass. The output is a validated data model and fixtures for a level-5 Human Fighter (with Alert and Savage Attacker feats) and two Goblin Scouts.

---

## Scope

- `app/campaignnarrator/domain/models.py` — expand `ActorState`, add `FeatState`, `WeaponState`, `InitiativeTurn`; update `EncounterState`
- `tests/unit/test_models.py` — unit tests for new model behavior
- `tests/fixtures/` — Fighter and Goblin fixture files for acceptance tests (JSON or Python fixtures)
- No orchestrator wiring — that belongs to Pass 2

---

## Data Model

### `ActorType` (new enum)

```python
class ActorType(str, Enum):
    PC = "pc"
    NPC = "npc"
    ALLY = "ally"
```

### `FeatState` (new dataclass)

```python
@dataclass(frozen=True, slots=True)
class FeatState:
    name: str
    effect_summary: str   # Injected into Rules Agent context verbatim
    reference: str | None # e.g. "DND.SRD.Wiki-0.5.2/Feats.md#Alert"
    per_turn_uses: int | None  # None = passive; 1 = once per turn
```

`effect_summary` is what the Rules Agent reads to decide whether and how a feat applies to a given action. The LLM reasons from this text — no hard-coded feat logic anywhere in the system.

`per_turn_uses` drives resource tracking only: the orchestrator resets the matching `resources` counter at turn start. The *decision* of when a use is consumed comes from the LLM reading `effect_summary`.

### `WeaponState` (new dataclass)

```python
@dataclass(frozen=True, slots=True)
class WeaponState:
    name: str
    attack_bonus: int       # Fully computed: proficiency + ability mod (+ magic bonus if any)
    damage_dice: str        # e.g. "1d8", "2d6"
    damage_bonus: int       # Ability mod (+ magic bonus if any)
    damage_type: str        # "slashing", "piercing", "bludgeoning", etc.
    properties: tuple[str, ...]  # e.g. ("versatile (1d10)", "thrown (range 20/60)")
```

All bonuses are pre-computed. The LLM reads `attack_bonus` directly — it never adds proficiency + ability modifier itself.

### `InitiativeTurn` (new dataclass)

```python
@dataclass(frozen=True, slots=True)
class InitiativeTurn:
    actor_id: str
    initiative_roll: int
```

Replaces the plain `str` in `initiative_order`. The roll value travels with the slot for display and tie-breaking. `actor_id` resolves to a full `ActorState` via `EncounterState.actors`.

### `ActorState` (expanded)

The existing fields `kind`, `inventory`, `character_class`, and `character_background` are replaced. `is_visible` is retained.

```python
@dataclass(frozen=True, slots=True)
class ActorState:
    # --- Identity ---
    actor_id: str
    name: str
    actor_type: ActorType

    # --- Ability scores ---
    strength: int
    dexterity: int
    constitution: int
    intelligence: int
    wisdom: int
    charisma: int

    # --- Derived core stats (pre-computed, stored explicitly) ---
    proficiency_bonus: int
    initiative_bonus: int        # DEX mod + feat/feature bonuses (e.g. Alert)
    speed: int                   # Movement in feet per turn
    armor_class: int
    ac_breakdown: tuple[str, ...] # e.g. ("Chain Mail: 16", "Shield: +2")

    # --- Hit points ---
    hp_max: int
    hp_current: int
    hp_temp: int = 0

    # --- Saving throws (proficiency applied where applicable) ---
    saving_throws: tuple[tuple[str, int], ...]
    # e.g. (("strength", 7), ("dexterity", 3), ("constitution", 7), ...)

    # --- Combat resources (reset per long/short rest as appropriate) ---
    # Keys: "second_wind", "action_surge", "ki_points", "savage_attacker", etc.
    # Per-turn resources (e.g. "savage_attacker") are reset at turn start by CombatOrchestrator.
    resources: tuple[tuple[str, int], ...]

    # --- Action economy options (human-readable, injected as LLM context) ---
    action_options: tuple[str, ...]
    attacks_per_action: int
    bonus_action_options: tuple[str, ...]
    reaction_options: tuple[str, ...]

    # --- Equipped weapons ---
    equipped_weapons: tuple[WeaponState, ...]

    # --- Feats ---
    feats: tuple[FeatState, ...]

    # --- Defenses ---
    damage_resistances: tuple[str, ...]
    damage_vulnerabilities: tuple[str, ...]
    damage_immunities: tuple[str, ...]
    condition_immunities: tuple[str, ...]

    # --- Current conditions ---
    conditions: tuple[str, ...]  # e.g. ("prone", "poisoned", "unconscious", "dead")

    # --- Death saves (dynamic) ---
    death_save_successes: int = 0
    death_save_failures: int = 0

    # --- Spellcasting (None for non-casters) ---
    spell_slots: tuple[tuple[str, int], ...] = field(default_factory=tuple)
    # e.g. (("1", 4), ("2", 3)) — current available slots by level
    spell_slots_max: tuple[tuple[str, int], ...] = field(default_factory=tuple)
    available_spells: tuple[str, ...] = field(default_factory=tuple)
    # Spell names only for Pass 1; SpellState is a future slice
    concentration: str | None = None

    # --- NPC personality (None for PCs) ---
    personality: str | None = None

    # --- Visibility ---
    is_visible: bool = True
```

**Design notes:**
- `resources` and `saving_throws` use `tuple[tuple[str, int], ...]` instead of `dict` to preserve `frozen=True, slots=True` compatibility and immutability guarantees. Callers convert to `dict` at the edge.
- All bonuses are pre-computed. The Rules Agent never re-derives them from raw scores.
- `conditions` is the authoritative source for actor status. `CombatOrchestrator` inspects this to decide turn processing (skip dead actors, auto-process death saves for unconscious actors).

### `EncounterState` (updated field)

Replace:
```python
initiative_order: tuple[str, ...] = field(default_factory=tuple)
```

With:
```python
combat_turns: tuple[InitiativeTurn, ...] = field(default_factory=tuple)
```

All other `EncounterState` fields are unchanged.

---

## Fighter Fixture — Level 5 Human Fighter

**Name:** Talia Ironveil
**actor_id:** `pc:talia`
**actor_type:** `ActorType.PC`

| Stat | Value |
|---|---|
| STR | 18 (+4) |
| DEX | 14 (+2) |
| CON | 16 (+3) |
| INT | 10 (+0) |
| WIS | 12 (+1) |
| CHA | 8 (-1) |
| Proficiency Bonus | +3 |
| Initiative | +5 (DEX +2, Alert feat +3) |
| Speed | 30ft |
| AC | 20 (Plate 18 + Shield +2) |
| HP Max | 44 |
| HP Current | 44 |

**Saving throws:** STR +7, DEX +5, CON +6, INT +3, WIS +4, CHA +2
(Fighter proficient in STR and CON)

**Equipped weapons:**
- Longsword (one-hand): attack +7, damage 1d8+4 slashing, properties: ("versatile (1d10)",)
- Longsword (two-hand via versatile): attack +7, damage 1d10+4 slashing, properties: ("versatile",)

**Action options:** ("Attack", "Dodge", "Disengage", "Dash", "Help", "Grapple", "Shove", "Action Surge (expend to take an additional action)")

**attacks_per_action:** 2 (Extra Attack at Fighter level 5)

**Bonus action options:** ("Second Wind (regain 1d10+5 HP, uses Second Wind resource)",)

**Reaction options:** ("Opportunity Attack (when enemy leaves melee reach)",)

**Feats:**
```python
FeatState(
    name="Alert",
    effect_summary=(
        "You add your Proficiency Bonus to your Initiative. You can't be surprised while you are "
        "conscious. Other creatures don't gain advantage on attack rolls against you as a result "
        "of being unseen by you. This proficiency bonus is already reflected in this actor's "
        "initiative_bonus — do not add it again when rolling initiative."
    ),
    reference="DND.SRD.Wiki-0.5.2/Feats.md#Alert",
    per_turn_uses=None,
)
FeatState(
    name="Savage Attacker",
    effect_summary=(
        "Once per turn when you roll damage for a melee weapon attack, you can reroll the weapon's "
        "damage dice and use either roll. The 'savage_attacker' resource tracks remaining uses this turn."
    ),
    reference="DND.SRD.Wiki-0.5.2/Feats.md#Savage Attacker",
    per_turn_uses=1,
)
```

**Resources:** `(("second_wind", 1), ("action_surge", 1), ("savage_attacker", 1))`

**AC breakdown:** `("Plate: 18", "Shield: +2")`

All other defense fields: empty tuples. No conditions. No spells.

---

## Goblin Scout Fixture

Two instances: `npc:goblin-1` and `npc:goblin-2`. Identical stats, different `actor_id` and `name`.

| Stat | Value |
|---|---|
| STR | 8 (-1) |
| DEX | 14 (+2) |
| CON | 10 (+0) |
| INT | 10 (+0) |
| WIS | 8 (-1) |
| CHA | 8 (-1) |
| Proficiency Bonus | +2 |
| Initiative | +2 |
| Speed | 30ft |
| AC | 15 (Leather + Shield) |
| HP Max | 7 |
| HP Current | 7 |

**Equipped weapons:**
- Scimitar: attack +4, damage 1d6+2 slashing, properties: ("light", "finesse")
- Shortbow: attack +4, damage 1d6+2 piercing, properties: ("ammunition (range 80/320)", "two-handed")

**Action options:** ("Attack", "Dodge", "Disengage", "Dash", "Hide", "Nimble Escape (Disengage or Hide as bonus action)")

**attacks_per_action:** 1

**Bonus action options:** ("Nimble Escape: Disengage as bonus action", "Nimble Escape: Hide as bonus action")

**Reaction options:** ()

**Feats:** ()

**Resources:** ()

**AC breakdown:** `("Leather: 11 + Dex modifier = 13 (DEX +2)", "Shield: +2", "Total: 15")`

**Personality:** `"Cowardly and opportunistic. Will flee when outmatched or when leader falls."`

---

## Testing

### `tests/unit/test_models.py` — new tests

- `ActorState` with full fields round-trips through `replace()` correctly
- `resources` as `tuple[tuple[str, int], ...]` converts to `dict` correctly
- `saving_throws` as `tuple[tuple[str, int], ...]` converts to `dict` correctly
- `EncounterState` with `combat_turns` preserves `InitiativeTurn` ordering
- `InitiativeTurn` is immutable (frozen)
- Fighter fixture has `initiative_bonus=5`
- Fighter fixture has `attacks_per_action=2`
- Fighter fixture `feats` contains Alert and Savage Attacker by name
- Goblin fixture `actor_type` is `ActorType.NPC`
- Goblin fixture `personality` is not None

### Existing tests

All existing `ActorState` usages must be updated to the new field names. `kind` → `actor_type` (use `ActorType` enum). `hp_max` remains. Remove `inventory`, `character_class`, `character_background`. `initiative_order` references → `combat_turns`.

---

## Files

| Action | Path |
|---|---|
| Modify | `app/campaignnarrator/domain/models.py` |
| Modify | `tests/unit/test_models.py` |
| Create | `tests/fixtures/fighter_talia.py` (or `.json`) |
| Create | `tests/fixtures/goblin_scout.py` (or `.json`) |
| Update (all callers) | Any file referencing `ActorState.kind`, `initiative_order`, `character_class`, `character_background`, `inventory` |

---

## Non-Goals

- Combat orchestration — Pass 2
- NPC turn processing — Pass 3
- Spellcaster fixtures — future slice
- `SpellState` dataclass — available spells stored as names only for now
- Magic item effects — backlog item 7
- Durable NPC personality persistence — backlog item 8

---

## Next Slice

Pass 2: Player combat turn loop. `CombatOrchestrator` receives the expanded `ActorState` and runs the player-side turn loop with resource tracking and feat context injection.
