Feature: Full combat encounters
  A solo Fighter can resolve multi-round D&D 5e combat through the CLI.

  Scenario: Fighter defeats two goblins in multi-round combat
    Given the OpenAI API is configured for fighter-vs-2-goblins on encounter fighter-vs-2-goblins
    When the player runs the encounter with scripted input:
      """
      I attack Goblin Scout 1
      end turn
      I attack Goblin Scout 2
      end turn
      I attack Goblin Scout 2
      end turn
      """
    Then the CLI output includes "Roll:"
    And the CLI output includes "Goblin Scout 1 falls dead"
    And the CLI output includes "Goblin Scout 2 falls"
    And the CLI output includes "Victory"
    And the encounter actor "npc:goblin-1" is defeated
    And the encounter actor "npc:goblin-2" is defeated

  Scenario: Fighter uses a healing potion and defeats three goblins
    Given the OpenAI API is configured for fighter-vs-3-goblins on encounter fighter-vs-3-goblins
    When the player runs the encounter with scripted input:
      """
      I attack Goblin Scout 1
      end turn
      I attack Goblin Scout 2
      I drink a Potion of Healing
      end turn
      I attack Goblin Scout 3
      end turn
      """
    Then the CLI output includes "Potion of Healing"
    And the CLI output includes "Victory"

  Scenario: Fighter is overwhelmed by four goblins and falls
    Given the OpenAI API is configured for fighter-vs-4-goblins on encounter fighter-vs-4-goblins
    When the player runs the encounter with scripted input:
      """

      """
    Then the CLI output includes "fallen"
