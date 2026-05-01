# Combat Flow

Combat is a turn-based form of the standard play loop.

## Core Structure

1. Determine Initiative.
2. Creatures take turns in Initiative order.
3. On a turn, a creature can move and take actions according to the rules.

## Action Economy Topics

Combat in the first cut needs to support:

- Action
- Bonus Action
- Reaction
- movement
- attacks
- spellcasting

## Action Economy Constraints

- A creature takes one Action on its turn unless a rule grants more.
- Bonus Actions are only available when a rule grants one.
- Reactions are taken in response to triggers and reset at the start of the creature's turn.

## Situational Combat Rules Deferred for Now

Mounted combat and underwater combat remain deferred. Their omission is tracked in `docs/excluded_rules.md`.
