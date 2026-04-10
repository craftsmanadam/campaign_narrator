Feature: Drink a potion of healing
  Scenario: Drinking a potion of healing updates state and logs the event
    Given the acceptance runtime root is ready
    When I run the real CLI in Docker
    Then the CLI prints the healing narration
    And the player character state is updated
    And the event log records the potion resolution
