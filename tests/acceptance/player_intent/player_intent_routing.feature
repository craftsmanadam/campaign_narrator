Feature: Player Intent Routing
  The EncounterOrchestrator routes player input to the correct handler
  based on the PlayerIntentAgent's classified intent.

  Background:
    Given an active encounter in social phase

  Scenario: Present-tense attack routes to combat
    When the player inputs "I charge the goblin with my sword" with hostile intent
    Then the encounter transitions to combat phase

  Scenario: Past-tense recounting does not trigger combat
    When the player inputs "We attacked the goblins yesterday" with scene observation intent
    Then the encounter remains in social phase
    And a narration is produced for scene_response

  Scenario: Save and exit saves state without narration agent involvement
    When the player inputs "save and exit the game" with save exit intent
    Then the encounter is saved
    And no narration is produced after scene opening

  Scenario: Stealth attempt routes to skill check with correct hint
    When the player inputs "I try to sneak past the guards" with skill check intent for Stealth
    Then the rules agent receives a request with check_hints containing Stealth
