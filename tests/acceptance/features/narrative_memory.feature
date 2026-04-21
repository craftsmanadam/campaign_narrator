Feature: Narrative memory persistence and retrieval
  CampaignNarrator stores narration events to persistent memory (narrative_memory.jsonl
  mirrored to LanceDB via stub embeddings) during encounters, and retrieves prior
  narrative context to maintain NPC and location consistency across sessions.

  Narrative memory is the core value proposition over raw ChatGPT: descriptions of NPCs,
  locations, and story beats recorded during one encounter must be available the next
  time the same setting or character appears.

  Scenario: Each narration event during an encounter is recorded to narrative memory as it happens
    Given the OpenAI API is configured for a peaceful goblin encounter
    When the player runs the encounter with scripted input:
      """
      Hello there. I do not want trouble.
      exit
      """
    Then the narrative memory contains at least 2 narration entries for encounter "goblin-camp"

  Scenario: Abandoning an unresolved encounter stores a generated summary so the next session has context
    Given the OpenAI API is configured for a hostile goblin encounter
    When the player runs the encounter with scripted input:
      """
      save and quit
      """
    Then the narrative memory contains a partial summary entry for encounter "goblin-camp"

  Scenario: Scene opening narration reflects a prior NPC description retrieved from memory
    Given the OpenAI API is configured for a goblin encounter with prior NPC memory on encounter goblin-camp
    And the narrative memory contains a prior encounter record:
      """
      The Goblin Scout bears a deep scar across his left cheek, the mark of a blade wound from a past skirmish.
      """
    When the player runs the encounter with scripted input:
      """
      exit
      """
    Then the CLI output includes "scar"
