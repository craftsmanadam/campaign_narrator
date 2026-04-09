# Wizard

## Core Traits

- Primary ability: Intelligence
- Hit Point Die: `d6`
- Saves: Intelligence, Wisdom
- Armor: none
- Weapons: Simple

## Level 1 to 5

- Level 1: `Spellcasting`, `Ritual Adept`, `Arcane Recovery`
- Level 2: `Scholar`
- Level 3: Wizard subclass
- Level 4: feat or Ability Score Improvement
- Level 5: `Memorize Spell`

## Spellbook Model

The Wizard is built around a spellbook rather than a fixed known-spells list.

- starts with six level 1 Wizard spells in the book,
- learns two more Wizard spells each level,
- prepares spells from the book after Long Rests,
- can copy discovered Wizard spells into the spellbook with time and gold.

## Spellcasting Shape

- Cantrips known at level 1: 3
- Prepared level 1+ spells at level 1: 4
- Spellcasting ability: Intelligence
- Can use an Arcane Focus or the spellbook as a spellcasting focus

## Core Features

- `Ritual Adept` allows ritual casting from the spellbook without preparing the spell
- `Arcane Recovery` restores some spell slots on a Short Rest
- `Scholar` grants expertise in a chosen knowledge skill
- `Memorize Spell` swaps one prepared Wizard spell after a Short Rest

## Subclass in the SRD

`Evoker`

This is the first SRD Wizard subclass and is the relevant baseline for early implementation.

## First-Cut Use

The Wizard requires persistent support for:

- spellbook contents,
- prepared-spell list,
- copied spells,
- and short-rest spell preparation changes.
