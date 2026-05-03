Feature: Encounter flow
  A player navigates through an encounter via the real application CLI.

  Scenario: Player resolves a social encounter peacefully
    Given the OpenAI API is configured for a peaceful goblin encounter
    When the player runs the encounter with scripted input:
      """
      Hello there. I do not want trouble.
      exit
      """
    Then the CLI output includes "The goblins lower their weapons."

  Scenario: Player initiates combat from a social encounter
    Given the OpenAI API is configured for a hostile goblin encounter
    When the player runs the encounter with scripted input:
      """
      I charge the goblins and attack with my longsword.
      save and quit
      """
    Then the CLI output includes "Initiative:"
    And the persisted encounter "goblin-camp" is in phase "combat"
    And the persisted encounter "goblin-camp" has initiative order

  Scenario: Player succeeds at de-escalating an aggressive encounter
    Given the OpenAI API is configured for aggressive goblins and a successful de-escalation
    When the player runs the encounter with scripted input:
      """
      I raise my empty hand and tell them we can both walk away.
      exit
      """
    Then the CLI output includes "Persuasion check:"

  Scenario: Player saves and quits mid-encounter
    Given the OpenAI API is configured for a hostile goblin encounter
    When the player runs the encounter with scripted input:
      """
      I charge the goblins and attack with my longsword.
      save and quit
      """
    Then the CLI output includes "Game saved"
