Feature: Combat flow
  A player completes a combat encounter via the real application CLI.

  Scenario: Fighter defeats two goblins in multi-round combat
    Given the OpenAI API is configured for fighter-vs-2-goblins on encounter fighter-vs-2-goblins
    When the player runs the encounter with scripted input:
      """
      I attack Goblin Scout 1
      end turn
      I attack Goblin Scout 2
      end turn
      """
    Then the CLI output includes "Roll:"
    And the CLI output includes "Goblin Scout 1 falls dead"
    And the CLI output includes "Victory"
    And the encounter actor "npc:goblin-1" is defeated
