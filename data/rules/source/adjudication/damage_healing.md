# Damage and Healing

Injury and death are frequent threats. This file captures the core SRD rules for hit points, damage, healing, and temporary hit points.

## Hit Points

Hit Points represent durability and the will to live.

- Hit Point maximum is the number of Hit Points a creature has when uninjured.
- Current Hit Points can range from that maximum down to `0`.
- Whenever a creature takes damage, subtract that damage from current Hit Points.
- Losing Hit Points has no direct effect on a creature's capabilities until it reaches `0` Hit Points.
- A creature at half its Hit Points or fewer is Bloodied. Bloodied has no built-in effect on its own, but other rules can care about it.

## Resting

Short and Long Rests are part of the core recovery model.

- any creature can take a 1-hour Short Rest during the day
- any creature can take an 8-hour Long Rest to end the day
- regaining Hit Points is one of the main benefits of resting

## Damage Rolls

Each weapon, spell, and damaging monster ability specifies the damage it deals.

- roll the damage dice
- add any modifiers
- deal the result to the target
- penalties can reduce a damage roll to `0` but never below `0`

When attacking with a weapon:

- add the same ability modifier used for the attack roll to the damage roll

When a rule deals fixed damage that does not use a roll:

- do not add an ability modifier unless a rule explicitly says otherwise

## Critical Hits

On a Critical Hit:

- roll the attack's damage dice twice
- add the doubled dice together
- then add relevant modifiers as normal
- if the attack includes additional damage dice from another feature, those dice are also rolled twice

## Saving Throws and Damage

When a saving-throw-based effect damages multiple targets at the same time:

- roll the damage once for all affected targets

When an effect deals half damage on a successful save:

- use half of the failed-save damage
- round down

## Damage Types

Every instance of damage has a type such as Fire or Slashing. Damage types have no independent rules of their own, but many other rules refer to them.

## Resistance and Vulnerability

Resistance and Vulnerability modify damage of a specific type.

- Resistance halves damage of that type, rounding down
- Vulnerability doubles damage of that type

Multiple instances of Resistance affecting the same damage type count as only one instance. The same rule applies to multiple instances of Vulnerability.

Order of application:

1. apply adjustments such as bonuses, penalties, or multipliers
2. apply Resistance
3. apply Vulnerability

## Immunity

Immunity to a damage type means the creature takes none of that damage type.

Immunity to a condition means the creature is unaffected by that condition.

## Healing

Hit Points can be restored by:

- magic
- Short Rests
- Long Rests
- certain items

When a creature receives healing:

- add the restored Hit Points to current Hit Points
- current Hit Points cannot exceed Hit Point maximum
- any healing in excess of the maximum is lost

## Knocking Out a Creature

When a creature would reduce another creature to `0` Hit Points with a melee attack, it can instead:

- reduce the target to `1` Hit Point
- give the target the Unconscious condition
- cause the target to start a Short Rest

That Unconscious condition ends:

- at the end of that Short Rest
- early if the creature regains any Hit Points
- early if another creature takes an action to administer first aid and succeeds on a `DC 10 Wisdom (Medicine)` check

## Temporary Hit Points

Temporary Hit Points are a buffer against losing real Hit Points.

Rules for Temporary Hit Points:

- lose Temporary Hit Points before normal Hit Points
- they last until depleted or until the creature finishes a Long Rest
- they do not stack; when receiving more, choose whether to keep the old amount or take the new amount
- they are not normal Hit Points and do not count as healing
- healing cannot restore Temporary Hit Points
- a creature at full Hit Points can still gain Temporary Hit Points
- a creature at `0` Hit Points does not regain consciousness from Temporary Hit Points alone
