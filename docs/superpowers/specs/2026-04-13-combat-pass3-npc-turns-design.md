# Combat Pass 3: NPC Turns, Combat Assessment, and Acceptance Tests — Design Spec

**Date:** 2026-04-13
**Status:** Approved
**Slice:** Combat backlog item 1, Pass 3 of 3
**Depends on:** Pass 1 (expanded `ActorState`), Pass 2 (`CombatOrchestrator` player turns)

---

## Problem

After Pass 2, the `CombatOrchestrator` processes player turns but skips NPC turns entirely. The combat loop has no Narrator-driven end condition — it terminates only when actors run out mechanically. Acceptance tests covering the full combat lifecycle (player + NPC turns, multi-round, potion use, player death) are marked pending.

---

## Goal

Complete the `CombatOrchestrator` with:

1. **NPC turn processing** — Narrator declares NPC intent, Rules Agent adjudicates, Narrator narrates result
2. **Narrator override of NPC critical hits** — before applying a crit to a player, the Narrator approves or downgrades
3. **`CombatAssessment` after every turn** — Narrator declares whether combat continues and, if not, supplies `CombatOutcome`
4. **`CombatOutcome` and `CombatResult`** — replace the Pass 2 stub with the full contract
5. **Potion of Healing** as a bonus action — required for Scenario 2
6. **Activate three acceptance test scenarios** — Fighter vs 2 goblins, vs 3 goblins + potion, vs 4 goblins + death

---

## Scope

- `app/campaignnarrator/domain/models.py` — add `CombatAssessment`, `CombatOutcome`; finalize `CombatResult` / `CombatStatus`
- `app/campaignnarrator/orchestration/combat_orchestrator.py` — NPC turn, Narrator assessment, crit override
- `tests/unit/test_combat_orchestrator.py` — extend with NPC turn and assessment tests
- `tests/acceptance/features/combat.feature` — three scenarios (previously pending)
- `tests/acceptance/steps/combat_steps.py` — step definitions

---

## New Domain Models

### `CombatOutcome`

```python
@dataclass(frozen=True, slots=True)
class CombatOutcome:
    short_description: str   # Compact — feeds encounter summary log
    full_description: str    # Rich prose — narrated to player, stored in detailed encounter log
```

`short_description` is written for future logging and memory systems (backlog item 8). `full_description` is the closing narration the player sees.

### `CombatAssessment`

```python
@dataclass(frozen=True, slots=True)
class CombatAssessment:
    combat_active: bool
    outcome: CombatOutcome | None  # None when combat_active is True
```

The Narrator emits one `CombatAssessment` after every actor's turn completes. When `combat_active` is `False`, the orchestrator exits the combat loop and uses `outcome.full_description` as the closing narration to the player.

### `CombatStatus` (finalized)

```python
class CombatStatus(str, Enum):
    COMPLETE = "complete"                   # Narrator declared combat over
    PLAYER_DOWN_NO_ALLIES = "player_down_no_allies"  # Player at 0 HP, no allies conscious
```

### `CombatResult` (finalized)

```python
@dataclass(frozen=True, slots=True)
class CombatResult:
    status: CombatStatus
    final_state: EncounterState
    death_saves_remaining: int | None  # None unless status is PLAYER_DOWN_NO_ALLIES
```

---

## NPC Turn Processing

### Narrator intent declaration

When `CombatOrchestrator` processes an NPC turn, it calls the Narrator with a focused NPC intent prompt. The Narrator receives:

- The acting NPC's full `ActorState` (conditions, equipped weapons, feats, personality)
- `hidden_facts` from `EncounterState` (short-term situational modifiers)
- Current encounter state (which actors are visible, their visible HP status, recent public events)

The Narrator returns a prose intent declaration:
- `"The goblin is wounded and frightened — it disengages and backs toward the door, loosing an arrow as it goes."`
- `"The goblin charges Talia, slashing with its scimitar."`
- `"The goblin flees."`

No enumerated action types. The Narrator speaks; the Rules Agent interprets.

### Rules Agent adjudication of NPC intent

The NPC intent declaration is passed to the Rules Agent exactly as the player's freeform input is — it is the "player" for this turn. The Rules Agent receives:

- NPC `ActorState` (attack bonuses, feats, weapons)
- Feat effect summaries in `compendium_context` (same injection as player turns)
- Narrator's intent prose as `intent`
- `allowed_outcomes` includes `"attack"`, `"move"`, `"flee"`, `"disengage"`, `"hide"`, `"bonus_action"`

All roll requests from NPC adjudication have `owner="system"` and are resolved internally by the orchestrator (no player input).

### Narrator crit override

When the Rules Agent returns a `RulesAdjudication` for an NPC action that includes a critical hit against a player actor (detected by: a `StateEffect` with `effect_type="critical_hit"` whose `target` resolves to an actor with `actor_type=ActorType.PC` in `EncounterState.actors`), the orchestrator pauses and sends the full mechanical result to the Narrator for approval before applying state effects:

```
"The goblin rolled a natural 20 against Talia. This would deal 14 damage (double dice). Approve, or downgrade to a normal hit?"
```

The Narrator returns either:
- `approved: True` → apply as-is (double damage dice)
- `approved: False, reason: str` → apply normal hit damage instead; Narrator uses `reason` in narration

This is the DM's classic "fudge behind the screen." Players never see the override. Player crits are never overridden — the player rolled it, they own it.

### NPC turn narration

After state effects are applied (with crit override resolved), the orchestrator routes the adjudication result to the Narrator to produce player-facing narration. The Narrator voices the entire NPC turn as a single coherent description — the intent, the action, and the outcome.

---

## Narrator `CombatAssessment` Call

After every actor's turn completes (player or NPC), `CombatOrchestrator` calls the Narrator with:

- Current `EncounterState` (all actor HP, conditions, `combat_turns` state)
- The just-completed turn's narration

The Narrator returns `CombatAssessment`. When `combat_active=False`:

1. Display `outcome.full_description` to player
2. Exit combat loop
3. Return `CombatResult(status=COMPLETE, final_state=state, death_saves_remaining=None)`

The Narrator may end combat for any story reason: all enemies dead, enemies fleeing, a cinematic moment, NPC surrender, etc. The orchestrator does not second-guess this decision.

---

## Potion of Healing (Bonus Action)

Required for Scenario 2 (3 goblins) and Scenario 3 (4 goblins, player dies).

A Potion of Healing is a consumable item usable as a bonus action. For this slice, it is modeled as a named entry in `actor.resources` rather than a full inventory system:

```python
resources=(("second_wind", 1), ("action_surge", 1), ("savage_attacker", 1), ("potion_of_healing", 2))
```

When the player declares "I drink a healing potion" (or similar), the Rules Agent identifies it as a bonus action consuming `potion_of_healing` resource and returns:
- `StateEffect(effect_type="heal", target=actor_id, value="2d4+2")`
- `StateEffect(effect_type="resource_spent", target=actor_id, value="potion_of_healing")`

The orchestrator rolls `2d4+2` (system roll, public) and applies the HP change. This pattern is intentionally minimal — a full inventory system is a future slice.

---

## Player Down / Death Handling

### Player reaches 0 HP, allies still in combat

Player enters death save mode:
- `"unconscious"` added to `actor.conditions`
- HP set to 0
- On each of the player's turns: orchestrator auto-processes death saves (see Pass 2 spec)
- If an ally heals the player: `"unconscious"` removed, HP set to heal amount, player resumes normal turns
- 3 successes → `"stable"` condition, `"unconscious"` removed
- 3 failures → `"dead"` condition added

### Player reaches 0 HP, no allies conscious

`CombatOrchestrator` detects: `actor.hp_current <= 0` and no other actors with `actor_type in (PC, ALLY)` have `hp_current > 0`.

Immediately returns:
```python
CombatResult(
    status=CombatStatus.PLAYER_DOWN_NO_ALLIES,
    final_state=state,
    death_saves_remaining=(3 - actor.death_save_failures),
)
```

`EncounterOrchestrator` reads `status` and routes to Narrator: "Player is down with {N} death saves remaining, no allies, enemies present — what happens?" Narrator decides based on story context and campaign personality. This is not resolved by `CombatOrchestrator`.

---

## Acceptance Test Scenarios

All three scenarios use WireMock stubs to pre-determine every LLM response. Rolls are deterministic because the acceptance test fixture pre-scripts the roll sequence via the `CombatIO` interface and system roll injection.

### Scenario 1: Fighter vs 2 Goblins

```gherkin
Scenario: Fighter defeats two goblins in multi-round combat
  Given a combat encounter with Talia Ironveil (Fighter) against Goblin Scout 1 and Goblin Scout 2
  And Talia wins initiative with a roll of 22
  When Talia attacks Goblin Scout 1 and rolls a critical hit
  And Talia uses Savage Attacker to reroll damage
  Then Goblin Scout 1 is killed
  When Goblin Scout 2 attacks Talia and hits for 2 damage
  Then Talia has 42 HP remaining
  When Talia attacks Goblin Scout 2 and deals 3 damage
  Then Goblin Scout 2 has 4 HP remaining
  When Goblin Scout 2 attacks Talia and misses
  When Talia attacks Goblin Scout 2 and kills it
  Then the Narrator declares combat complete
  And the encounter outcome is narrated to the player
```

Exercises: Alert initiative bonus, Savage Attacker reroll resource, NPC hit, NPC miss, multi-round, `CombatAssessment(combat_active=False)`.

### Scenario 2: Fighter vs 3 Goblins with Potion

```gherkin
Scenario: Fighter uses a healing potion and defeats three goblins
  Given a combat encounter with Talia Ironveil against three Goblin Scouts
  And Talia has 2 Potions of Healing in her resources
  When Talia takes sufficient damage to use a healing potion
  And Talia uses a Potion of Healing as a bonus action
  Then Talia's HP increases by the healing roll result
  And Talia's bonus action is consumed for that turn
  When Talia kills all three goblins over subsequent rounds
  Then the Narrator declares combat complete
```

Exercises: bonus action item use, HP healing via `StateEffect`, `potion_of_healing` resource decrement, sustained multi-round combat.

### Scenario 3: Fighter vs 4 Goblins, Player Dies

```gherkin
Scenario: Fighter is overwhelmed by four goblins and falls
  Given a combat encounter with Talia Ironveil against four Goblin Scouts
  And Talia has 1 Potion of Healing in her resources
  When Talia uses her healing potion but takes lethal damage
  And Talia's HP reaches 0 with no allies remaining
  Then CombatOrchestrator returns PLAYER_DOWN_NO_ALLIES status
  And the death saves remaining count is correct
  And the EncounterOrchestrator routes to the Narrator for outcome
```

Exercises: player death path, `CombatResult.status=PLAYER_DOWN_NO_ALLIES`, `death_saves_remaining`, handoff to `EncounterOrchestrator`.

---

## Testing

### `tests/unit/test_combat_orchestrator.py` — additions

- NPC turn: Narrator intent prompt is called with NPC actor state and `hidden_facts`
- NPC turn: Rules Agent receives feat effect summaries in `compendium_context`
- NPC crit against player: crit override prompt sent to Narrator before state effects applied
- NPC crit approved: double damage dice applied
- NPC crit downgraded: normal damage applied, override not visible in player narration
- `CombatAssessment(combat_active=False)`: combat loop exits, `CombatResult.status=COMPLETE`
- `CombatAssessment(combat_active=True)`: loop continues
- Potion of healing: `StateEffect(effect_type="heal")` increases `hp_current`; resource decremented
- Player down, allies present: death save mode entered
- Player down, no allies: `CombatResult(status=PLAYER_DOWN_NO_ALLIES)` returned immediately

### `tests/acceptance/features/combat.feature`

Three scenarios as defined above. Previously marked `@pending` in Pass 1 and Pass 2 — activated in this pass.

---

## Files

| Action | Path |
|---|---|
| Modify | `app/campaignnarrator/domain/models.py` |
| Modify | `app/campaignnarrator/orchestration/combat_orchestrator.py` |
| Modify | `tests/unit/test_combat_orchestrator.py` |
| Create | `tests/acceptance/features/combat.feature` |
| Create | `tests/acceptance/steps/combat_steps.py` |
| Create/Modify | WireMock stub fixtures for LLM responses |

---

## Non-Goals

- Reactions (opportunity attacks, Shield spell, Counterspell) — future slice
- Surprise round — future slice
- Allied NPCs joining combat — future slice
- Spellcasting — future slice
- Durable NPC personality persistence — backlog item 8
- Encounter logging / memory — backlog item 8
- Magic items beyond Potion of Healing — backlog item 7
- Multi-party encounters (more than one PC) — future slice

---

## Future Slices Identified

- **Reactions:** `CombatOrchestrator` must pause mid-NPC-turn and prompt the PC for a reaction declaration (opportunity attack, Shield, Counterspell). Significant scope.
- **Spellcaster slice:** Full `SpellState` dataclass, concentration tracking, spell slot management, spell-as-action routing.
- **Encounter logging:** High-level encounter summary (compact, always available) + detailed event log (indexed by encounter ID, pulled on demand). Feeds backlog item 8.
