Feature: Character Class Selection Menu
  The CharacterCreationOrchestrator presents a numbered class menu
  so the player selects their class deterministically.

  Scenario: Class selection presents a numbered menu and accepts number input
    Given available character classes fighter and rogue
    When the player reaches class selection and enters "1"
    Then fighter is selected as the class

  Scenario: Class selection accepts class name typed directly
    Given available character classes fighter and rogue
    When the player reaches class selection and enters "rogue"
    Then rogue is selected as the class

  Scenario: Class selection reprompts on invalid input then accepts valid input
    Given available character classes fighter and rogue
    When the player enters "9" then "wizard" then "2"
    Then rogue is selected as the class
