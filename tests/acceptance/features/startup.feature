Feature: Game startup flow
  A player can start a new game, create a character, and have a campaign created.
  A returning player can load a saved campaign or start a new one.

  Scenario: New player creates a Fighter and sees the opening scene
    Given the game state is empty for scenario startup-s1
    When the player runs the game with scripted input:
      """
      I want to be a warrior
      Aldric
      Human
      I served the king's guard for six years and lost everything when the city fell.


      save and quit
      """
    Then the CLI output includes "docks"

  Scenario: Returning player loads a saved campaign
    Given the game state has a saved campaign for scenario startup-s2
    When the player runs the game with scripted input:
      """
      load it
      save and quit
      """
    Then the CLI output includes "Darkholm"

  Scenario: Returning player has a character but no campaign
    Given the game state has a player but no campaign for scenario startup-s3
    When the player runs the game with scripted input:
      """
      I want dark coastal horror with undead and political intrigue.
      save and quit
      """
    Then the CLI output includes "docks"
