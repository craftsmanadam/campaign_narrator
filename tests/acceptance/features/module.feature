Feature: Module encounter progression
  When an encounter completes naturally the ModuleOrchestrator archives it,
  generates a rich summary, plans the next encounter via the Narrator, and
  begins the new encounter — all without manual intervention.

  Scenario: Completed encounter is archived and next encounter begins
    Given the module has a completed encounter for scenario module-s1
    When the player runs the game with scripted input:
      """
      load it
      save and quit
      """
    Then the CLI output includes "docks"
