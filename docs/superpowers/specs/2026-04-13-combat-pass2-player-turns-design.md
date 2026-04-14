# Combat Pass 2: Player Combat Turn — Design Spec

**Date:** 2026-04-13
**Status:** Approved
**Slice:** Combat backlog item 1, Pass 2 of 3
**Depends on:** Pass 1 (expanded `ActorState`, `FeatState`, `InitiativeTurn`)

---

## Problem

With the full `ActorState` model in place (Pass 1), there is still no combat execution path. The `EncounterOrchestrator` routes to a `COMBAT` phase but has no `CombatOrchestrator` to delegate to. Players cannot take combat turns: there is no action economy loop, no resource tracking, no feat context injection into the Rules Agent, and no movement budget management.

---

## Goal

Implement `CombatOrchestrator` handling of player turns only. This includes:

- Receiving combat handoff from `EncounterOrchestrator` (with `combat_turns` already set)
- Running the per-player-turn resource loop (action, bonus action, reaction, movement)
- Routing player freeform input to the Rules Agent with feat context injected
- Applying `StateEffect`s from Rules adjudication to `EncounterState`
- Routing adjudication results to the Narrator for voiced output
- Presenting remaining turn resources to the player after each declaration
- Advancing `combat_turns` rotation after each actor's turn completes

NPC turns are not implemented in this pass. When an NPC's turn comes up, `CombatOrchestrator` skips it (logs a warning) and advances to the next actor.

---

## Scope

- `app/campaignnarrator/orchestration/combat_orchestrator.py` — new file
- `app/campaignnarrator/orchestration/encounter_orchestrator.py` — wire handoff to `CombatOrchestrator` on phase transition to `COMBAT`
- `app/campaignnarrator/domain/models.py` — add `TurnResources`, `CombatResult`, `CombatStatus`
- `tests/unit/test_combat_orchestrator.py` — new test file

---

## New Domain Models

### `TurnResources`

Tracks what action economy the current actor has left this turn. Reset at the start of each actor's turn.

```python
class CombatStatus(str, Enum):
    COMPLETE = "complete"
    PLAYER_DOWN_NO_ALLIES = "player_down_no_allies"

@dataclass(frozen=True, slots=True)
class TurnResources:
    action_available: bool = True
    bonus_action_available: bool = True
    reaction_available: bool = True
    movement_remaining: int = 0   # feet; initialized from ActorState.speed at turn start
```

### `CombatResult`

Returned by `CombatOrchestrator` to `EncounterOrchestrator` when combat ends.

```python
@dataclass(frozen=True, slots=True)
class CombatResult:
    status: CombatStatus
    final_state: EncounterState
    death_saves_remaining: int | None  # None unless status is PLAYER_DOWN_NO_ALLIES
```

---

## `CombatOrchestrator`

### Responsibility

Own the combat loop for the duration of a single combat encounter. Receive `EncounterState` with `combat_turns` populated. Return `CombatResult` when combat is over.

### Constructor dependencies

```python
class CombatOrchestrator:
    def __init__(
        self,
        rules_agent: RulesAgent,
        narrator_agent: NarratorAgent,
        io: CombatIO,       # thin interface: prompt player, display text
    ) -> None:
```

`CombatIO` is a simple interface (or protocol) with two methods:
- `prompt(text: str) -> str` — display text and read player input
- `display(text: str) -> None` — display text with no input expected

This keeps `CombatOrchestrator` testable without a real terminal.

### Main entry point

```python
def run(self, state: EncounterState) -> CombatResult:
```

Loops while `combat_turns` is non-empty and no end condition is triggered. Processes one actor per iteration in `combat_turns[0]` order.

### Per-actor turn dispatch

```python
def _process_turn(self, state: EncounterState, turn: InitiativeTurn) -> EncounterState:
```

1. Resolve `actor = state.actors[turn.actor_id]`
2. Check `actor.conditions`:
   - `"dead"` → skip, return state unchanged
   - `"unconscious"` → auto-process death saves (see below), return updated state
   - `"incapacitated"` → skip, return state unchanged
3. If `actor.actor_type == ActorType.PC` → run player turn loop
4. If `actor.actor_type in (ActorType.NPC, ActorType.ALLY)` → log warning "NPC turns not yet implemented", skip
5. Rotate `combat_turns`: move `turn` to the end of the tuple

### Player turn loop

```python
def _run_player_turn(
    self, state: EncounterState, actor: ActorState
) -> EncounterState:
```

1. Reset per-turn resources:
   - `TurnResources(movement_remaining=actor.speed)`
   - Reset per-turn `resources` counters from `actor.feats`:
     - For each `FeatState` where `per_turn_uses is not None`, restore the resource key to `per_turn_uses`
2. Display turn banner: `"--- {actor.name}'s turn ---"`
3. Display resource summary (see format below)
4. Loop:
   a. Read player input via `io.prompt`
   b. If input signals turn complete (see pass detection below) → break
   c. Build `RulesAdjudicationRequest` with feat context injected (see below)
   d. Call `rules_agent.adjudicate(request)` → `RulesAdjudication`
   e. If `is_legal=False` and `action_type="clarifying_question"`:
      - Route to Narrator for a voiced answer
      - Display answer, loop continues, resources unchanged
   f. If `is_legal=False` and `action_type="impossible_action"`:
      - Route to Narrator with the `summary` from adjudication
      - Display response, loop continues, resources unchanged
   g. If `is_legal=True`:
      - Apply `state_effects` to `EncounterState` (update actor HP, conditions, etc.)
      - Update `TurnResources` based on `action_type` ("action", "bonus_action", "movement", "free")
      - Route to Narrator with adjudication result → display narration
      - Display updated resource summary
5. Return updated `EncounterState`

**Pass detection:** Input text is normalized (lowercased, whitespace collapsed). Treated as "turn complete" if it matches any of: `"done"`, `"end turn"`, `"pass"`, `"i'm done"`, `"that's all"`, `"finished"`. This list is a constant, not business logic — the Narrator may supplement in future.

### Feat context injection

When building `RulesAdjudicationRequest`, append each acting actor's feat effect summaries to `compendium_context`:

```python
feat_context = tuple(
    f"Feat — {feat.name}: {feat.effect_summary}"
    for feat in actor.feats
)
request = RulesAdjudicationRequest(
    actor_id=actor.actor_id,
    intent=player_input,
    phase=EncounterPhase.COMBAT,
    allowed_outcomes=("attack", "move", "bonus_action", "clarifying_question", "impossible_action", "free_action"),
    compendium_context=feat_context,
)
```

The LLM reads the feat text and decides whether Alert already fired (passive, already reflected in `initiative_bonus` — effect summary says so), whether Savage Attacker applies to this damage roll (once per turn, checks the resource), etc. No conditional logic in the orchestrator.

### Movement tracking

`TurnResources.movement_remaining` is initialized to `actor.speed` at turn start. When the Rules Agent returns a `StateEffect` with `effect_type="movement"` and `value=<feet_spent>`, the orchestrator subtracts from `movement_remaining`. The Rules Agent estimates feet spent from narrative context (adjacent enemy ≈ 5ft, crossing medium room ≈ 25ft). The orchestrator enforces: if `value > movement_remaining`, the Rules Agent's adjudication is returned as `is_legal=False` with `action_type="impossible_action"`.

### Resource summary format

Displayed after each action and at turn start:

```
Action: used | Bonus Action: available | Movement: 25ft remaining | Reaction: available
```

Fields update as resources are consumed. `movement_remaining=0` displays as `Movement: none remaining`.

### Death save auto-processing

When `actor.conditions` contains `"unconscious"`, on the actor's turn:

1. Roll 1d20 (system roll, hidden)
2. If ≥ 10: increment `death_save_successes`; if 3 → add `"stable"` condition, remove `"unconscious"`
3. If < 10: increment `death_save_failures`; if 3 → add `"dead"` condition, remove `"unconscious"`
4. Display result to player: `"Talia makes a death saving throw..."` + outcome
5. Return updated state

A critical hit (natural 20) on a death save counts as 2 successes. This is handled by the Rules Agent if an NPC attacks an unconscious actor — for auto-processing, a natural 1 counts as 2 failures.

### Combat end detection (Pass 2 stub)

In Pass 2, `CombatOrchestrator.run()` ends when:
- `combat_turns` is exhausted (all actors dead/skipped) — `CombatStatus.COMPLETE`
- Player HP reaches 0 and no other PC/ALLY actors have HP > 0 — `CombatStatus.PLAYER_DOWN_NO_ALLIES`

The Narrator's `CombatAssessment` call is added in Pass 3. In Pass 2, combat termination is purely mechanical.

---

## `EncounterOrchestrator` Changes

When `EncounterOrchestrator` detects phase transition to `COMBAT`:

1. Instantiate `CombatOrchestrator`
2. Call `combat_orchestrator.run(state)` → `CombatResult`
3. On return: update `EncounterState` from `CombatResult.final_state`
4. If `CombatResult.status == PLAYER_DOWN_NO_ALLIES`: route to Narrator with `death_saves_remaining`
5. Continue encounter lifecycle from post-combat state

---

## Testing

### `tests/unit/test_combat_orchestrator.py`

All tests use a fake `CombatIO` (pre-scripted inputs), fake `RulesAgent` (returns canned `RulesAdjudication`), and fake `NarratorAgent` (returns canned `Narration`).

- Player says "end turn" immediately → turn completes, no resources consumed
- Player declares attack → `RulesAdjudicationRequest` contains feat effect summaries for Alert and Savage Attacker in `compendium_context`
- Legal attack → `state_effects` applied to actor HP, Narrator receives adjudication result
- Clarifying question (`action_type="clarifying_question"`) → resources unchanged, Narrator routes, loop continues
- Impossible action → resources unchanged, Narrator redirects, loop continues
- `TurnResources` correctly resets `savage_attacker` to 1 at turn start (from `FeatState.per_turn_uses`)
- Movement deduction → `movement_remaining` decremented by `StateEffect(effect_type="movement", value=5)`
- Movement exceeded → adjudication returned as `impossible_action`
- Dead actor in `combat_turns` → turn skipped, state unchanged
- Unconscious actor → death saves auto-processed

---

## Files

| Action | Path |
|---|---|
| Create | `app/campaignnarrator/orchestration/combat_orchestrator.py` |
| Modify | `app/campaignnarrator/orchestration/encounter_orchestrator.py` |
| Modify | `app/campaignnarrator/domain/models.py` |
| Create | `tests/unit/test_combat_orchestrator.py` |

---

## Non-Goals

- NPC turns — Pass 3
- Narrator `CombatAssessment` — Pass 3
- `CombatOutcome` / `CombatResult.status` beyond stub — Pass 3
- Reactions (opportunity attacks, Shield spell, Counterspell) — future slice
- Surprise round — future slice
- Healing potions as items — Pass 3 (needed for Scenario 2 acceptance test)

---

## Next Slice

Pass 3: NPC turns, Narrator `CombatAssessment`, `CombatOutcome`, and activation of all three acceptance test scenarios.
