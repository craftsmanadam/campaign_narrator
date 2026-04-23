Feature: Encounter Planner — planning, scaling, and continuity
  The EncounterPlannerOrchestrator prepares every encounter before the narrator
  opens the scene. NPCs are declared at planning time, not by the narrator.

  # ─── Scenario 1: Initial encounter list ────────────────────────────────────
  Scenario: Module initialisation produces encounter list with named distinct NPCs
    Given a module "The Dockside Murders" has been generated for player level 1
    When the encounter planner generates the initial encounter list
    Then the module has between 3 and 5 planned encounters
    And no two EncounterNpc entries share the same template_npc_id within the module

  # ─── Scenario 2: Pre-built NPC state ───────────────────────────────────────
  Scenario: Narrator receives a fully-populated EncounterState with pre-built NPCs
    Given a module with a planned encounter containing two goblin NPCs
    When the encounter planner prepares the next encounter
    Then the saved EncounterState has actors for both goblins
    And the saved EncounterState has NpcPresence entries for both goblins
    And the narrator open_scene frame contains those NpcPresence entries

  # ─── Scenario 3: Viable path ────────────────────────────────────────────────
  Scenario: Pre-encounter divergence check — viable path
    Given a module with one planned encounter whose prerequisites are met
    When the encounter planner checks divergence before prepare
    Then divergence status is "viable"
    And the encounter is prepared without modification

  # ─── Scenario 4: Bridge inserted ────────────────────────────────────────────
  Scenario: Pre-encounter divergence check — bridge encounter inserted
    Given a module whose next encounter requires Grizznak to be alive
    And the narrative memory records that Grizznak died in a prior encounter
    When the encounter planner checks divergence before prepare
    Then divergence status is "needs_bridge"
    And a bridge encounter is inserted before the original next encounter
    And next_encounter_index still points to the bridge encounter

  # ─── Scenario 5: Milestone achieved early ───────────────────────────────────
  Scenario: Pre-encounter divergence check — milestone achieved early
    Given a module with two remaining planned encounters
    And the narrative memory shows the guiding milestone is complete
    When the encounter planner checks divergence before prepare
    Then prepare returns MilestoneAchieved
    And ModuleOrchestrator advances to the next module

  # ─── Scenario 6: CR scaling — over-budget trimmed ────────────────────────────
  Scenario: CR scaling trims an over-budget encounter
    Given a planned encounter with two goblins (CR 0.25 each) for player level 1
    And the CR budget is player_level / 4 = 0.25 with tolerance 0.25
    When scale_encounter_npcs is called
    Then the encounter is trimmed to 1 goblin
    And a warning is logged about the trim

  # ─── Scenario 7: CR scaling — floor at 1 NPC ────────────────────────────────
  Scenario: CR scaling floors at 1 NPC
    Given a planned encounter with one dragon (CR 17) for player level 1
    When scale_encounter_npcs is called
    Then the encounter still has 1 NPC
    And a warning is logged about the trim

  # ─── Scenario 8: Cross-session resume ───────────────────────────────────────
  Scenario: Cross-session resume — in-progress encounter not re-created
    Given a module with next_encounter_index = 1
    And an active encounter already exists in the encounter repository
    When ModuleOrchestrator runs
    Then prepare is never called
    And the existing active encounter resumes without modification

  # ─── Scenario 9: Module recovery — empty encounter list ─────────────────────
  Scenario: Module recovery when divergence produces an empty encounter list
    Given a module whose recovery agent returns an empty encounter list
    When the encounter planner handles the recovery result
    Then the planner calls the full-replan agent to regenerate the encounter list
    And the regenerated list has at least one encounter

  # ─── Scenario 10: NPC identity preserved across encounters ──────────────────
  Scenario: NPC identity preserved across encounters via stable template_npc_id
    Given a module where Grizznak appears in enc-001 and enc-003
    And both EncounterNpc entries have template_npc_id "grizznak"
    When both encounters are instantiated
    Then the actor_id in both EncounterState instances is "npc:grizznak"
    And narrative memory written for enc-001 is retrievable in enc-003 via "npc:grizznak"
