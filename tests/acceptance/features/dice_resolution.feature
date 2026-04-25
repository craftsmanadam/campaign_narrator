Feature: Dice roll mechanical resolution

  Scenario: Skill check failure is narrated as failure
    Given a player who attempts an Investigation check
    And the rules agent returns a roll_request with difficulty_class=15
    When the dice roll produces a total of 3
    Then the roll display reads "Roll: Investigation check = 3 — Failed (DC 15)"
    And the narrator narrates a failure outcome
    And the narrator does not describe the player finding tracks or succeeding

  Scenario: Skill check success is narrated as success
    Given a player who attempts an Investigation check
    And the rules agent returns a roll_request with difficulty_class=15
    When the dice roll produces a total of 17
    Then the roll display reads "Roll: Investigation check = 17 — Succeeded (DC 15)"
    And the narrator narrates a success outcome

  Scenario: Roll with no DC set falls back to LLM summary outcome
    Given a player who attempts a skill check
    And the rules agent returns a roll_request with difficulty_class unset
    When the dice roll completes
    Then no DC comparison is performed
    And the roll display does not include a DC label
    And the outcome is narrated per the adjudication summary
