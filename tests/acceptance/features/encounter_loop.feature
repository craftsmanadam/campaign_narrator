Feature: Encounter loop
  A solo player can resolve a constrained goblin encounter through the CLI.

  Scenario: Friendly player and peaceful goblins resolve the encounter without combat
    Given the OpenAI API is configured for a peaceful goblin encounter
    When the player runs the encounter with scripted input:
      """
      Hello there. I do not want trouble.
      status
      look around
      what happened
      exit
      """
    Then the CLI output includes "The goblins lower their weapons."
    And the CLI output includes "Status: Talia has 12 of 12 hit points"
    And the CLI output includes "Visible creatures: Talia, Goblin Scout"
    And the CLI output includes "Encounter outcome: peaceful"
    And the CLI output does not include "Initiative:"

  Scenario: Hostile player and hostile goblins enter combat immediately
    Given the OpenAI API is configured for a hostile goblin encounter
    When the player runs the encounter with scripted input:
      """
      I charge the goblins and attack with my longsword.
      status
      what happened
      exit
      """
    Then the CLI output includes "Initiative:"
    And the CLI output includes "Talia attacks with the longsword."
    And the CLI output includes "Encounter outcome: combat"

  Scenario: Neutral player succeeds at de-escalating aggressive goblins
    Given the OpenAI API is configured for aggressive goblins and a successful de-escalation
    When the player runs the encounter with scripted input:
      """
      I raise my empty hand and tell them we can both walk away.
      status
      what happened
      exit
      """
    Then the CLI output includes "Persuasion check:"
    And the CLI output includes "The goblins back away from the ruined camp."
    And the CLI output includes "Encounter outcome: de-escalated"
    And the CLI output does not include "Initiative:"

  Scenario: Neutral player fails to de-escalate aggressive goblins
    Given the OpenAI API is configured for aggressive goblins and a failed de-escalation
    When the player runs the encounter with scripted input:
      """
      I ask them to let me pass and promise I mean no harm.
      status
      what happened
      exit
      """
    Then the CLI output includes "Persuasion check:"
    And the CLI output includes "Initiative:"
    And the CLI output includes "Encounter outcome: combat"

  Scenario: Player saves and quits during combat
    Given the OpenAI API is configured for a hostile goblin encounter
    When the player runs the encounter with scripted input:
      """
      I charge the goblins and attack with my longsword.
      save and quit
      """
    Then the CLI output includes "Game saved"
    And the event log includes an encounter_saved event for "goblin-camp" in phase "combat"
    And the persisted encounter "goblin-camp" is in phase "combat"
    And the persisted encounter "goblin-camp" has initiative order
