# System Architecture

This document records the current architectural understanding for
CampaignNarrator. It is a living design reference, not a replacement for
time-scoped feature specs or the project engineering rules.

## Purpose

CampaignNarrator is a local, LLM-assisted tabletop RPG narrator and rules
adjudication system. Its purpose is to let a solo player interact with a
campaign-like experience where the application coordinates scene flow, rules,
dice, state, and narration.

The system should feel like interacting with a Dungeon Master, while keeping
mechanical authority, state changes, and test boundaries explicit.

## Deployment Boundary

Inside the deployment unit:

- CLI entry point (`cli.py`)
- Orchestrators
- Agents
- Repositories
- Tool layer
- Adapters (PydanticAI and embedding)
- Domain models and all game state

Outside the deployment unit:

- OpenAI HTTP API
- Ollama HTTP API (embeddings and optionally LLM)

Acceptance tests may fake external network dependencies (OpenAI, Ollama) but
must not mock production code inside the deployment unit.

## Orchestration Hierarchy

Orchestrators are the application's control authorities. Each owns a specific
lifecycle boundary and delegates to subordinate orchestrators or agents for
work outside its scope. No orchestrator should absorb responsibilities that
belong to another layer.

Orchestrators live under `app/campaignnarrator/orchestrators/`.

### Game Orchestrator (`_LazyGameOrchestrator` in `application_factory.py`)

The top-level router. Reads persisted state on startup and delegates to the
appropriate sub-orchestrator based on what the game state contains:

- No player file → `CharacterCreationOrchestrator`, then `CampaignCreationOrchestrator`
- Player exists, no campaign → `CampaignCreationOrchestrator`
- Player and campaign exist → `StartupOrchestrator`

Also exposes `save_state()`, which flushes in-memory session state to disk.
Called on `SIGTERM` and `KeyboardInterrupt`.

### Startup Orchestrator (`startup_orchestrator.py`)

Owns the returning-player flow. Reads the persisted campaign and asks the
player what they want to do. Supports loading an existing campaign, starting a
new one (with confirmation to destroy the old one), or abandoning a partial
state. Delegates active play to `ModuleOrchestrator`.

### Campaign Creation Orchestrator (`campaign_creation_orchestrator.py`)

Owns campaign creation. Collects the player's story brief, calls
`CampaignGeneratorAgent` to produce structured campaign canon (name, setting,
narrator personality, BBEG, hidden goal, milestones), then calls
`ModuleGeneratorAgent` to produce the first module. Persists both to
`GameStateRepository` and delegates the encounter loop to `ModuleOrchestrator`.

### Character Creation Orchestrator (`character_creation_orchestrator.py`)

Owns the character build flow. Guides the player through class selection, name,
race, background, and appearance. Uses `BackstoryAgent` if the player requests
help writing a backstory. Persists the player `ActorState` via
`PlayerRepository` and writes the backstory to `NarrativeMemoryRepository`.

### Module Orchestrator (`module_orchestrator.py`)

Owns module progression. Runs a loop over encounters within one story module.
After each encounter completes it archives the result, checks whether the
module's guiding milestone is achieved, and either advances to the next
encounter via `EncounterPlannerOrchestrator` or generates a new module via
`ModuleGeneratorAgent`. Summarizes completed encounters into narrative memory
via `NarratorAgent.summarize_encounter()`.

### Encounter Planner Orchestrator (`encounter_planner_orchestrator.py`)

Prepares a ready-to-run `EncounterState` before a scene opens. Called by
`ModuleOrchestrator` only when no active encounter exists. Responsibilities:

1. **Planning** — if the module has no planned encounters, calls
   `EncounterPlannerAgent.plan_encounters()` and persists the result.
2. **Divergence check** — calls `EncounterPlannerAgent.assess_divergence()` to
   verify the next template still fits the narrative. If not, calls
   `EncounterPlannerAgent.recover_encounters()` to bridge, replace, or replan.
3. **Instantiation** — resolves NPC templates against the compendium via
   `build_npc_actor()` and `scale_encounter_npcs()`, builds the `EncounterState`
   and actor registry entries, and stages them in `GameStateRepository`.

Retries up to three times on transient LLM failure with exponential back-off.

### Encounter Orchestrator (`encounter_orchestrator.py`)

Owns tactical encounter resolution. Manages the phase state machine
(`SCENE_OPENING → SOCIAL → RULES_RESOLUTION → COMBAT → ENCOUNTER_COMPLETE`).
On each turn it:

1. Opens the scene via `NarratorAgent` on first entry.
2. Reads player input and classifies intent via `PlayerIntentAgent`.
3. Routes to `RulesAgent` for adjudication when mechanics apply.
4. Applies structured state effects to `GameState`.
5. Delegates to `CombatOrchestrator` when the encounter enters combat phase.
6. Narrates results via `NarratorAgent`.
7. Persists `GameState` to `GameStateRepository` after each action.

Handles `save_exit` intent by persisting and returning, allowing the session
to resume later from the same encounter state.

### Combat Orchestrator (`combat_orchestrator.py`)

Owns the combat turn loop. Called by `EncounterOrchestrator` when phase is
`COMBAT`. Manages initiative order via `CombatState.turn_order`, processes
player and NPC turns, rolls and applies damage, tracks death saves, and
determines victory/defeat/retreat. Delegates rules questions to `RulesAgent`
and narration to `NarratorAgent`. Persists state after each turn.

## Agents

Agents live under `app/campaignnarrator/agents/`. Each wraps one or more
`pydantic_ai.Agent` instances configured via `PydanticAIAdapter`. Agents must
not mutate state; they return structured data that the calling orchestrator
validates and applies.

| Agent | File | Responsibility |
|---|---|---|
| `RulesAgent` | `rules_agent.py` | Adjudicate encounter actions into structured rules output with roll requests and state effects |
| `NarratorAgent` | `narrator_agent.py` | Convert public encounter frames into short player-facing prose; manage scene openings, NPC dialogue, and combat assessments |
| `PlayerIntentAgent` | `player_intent_agent.py` | Classify player input into a typed `PlayerIntent` (category, check hint, target NPC) |
| `EncounterPlannerAgent` | `encounter_planner_agent.py` | Plan, assess divergence, and recover encounter sequences for a module |
| `CampaignGeneratorAgent` | `campaign_generator_agent.py` | Generate a campaign skeleton from the player's brief |
| `ModuleGeneratorAgent` | `module_generator_agent.py` | Generate the next story module guided by milestones |
| `BackstoryAgent` | `backstory_agent.py` | Draft a character backstory from player-provided fragments |
| `StartupInterpreterAgent` | `startup_interpreter_agent.py` | Classify a returning player's free-form startup response into a structured intent |
| `CharacterInterpreterAgent` | `character_interpreter_agent.py` | Classify a player's class choice and extract name/race from free-form text |

## State Model

All structured runtime state is owned by `GameState`, a frozen immutable
dataclass. State mutations produce a new `GameState` via `with_*` methods.
`replace()` from `dataclasses` is used only inside domain model methods, never
by external callers.

```
GameState
├── campaign: CampaignState | None
│   ├── name, setting, narrator_personality, hidden_goal, bbeg_name/description
│   ├── milestones: tuple[Milestone, ...]
│   ├── current_milestone_index, starting_level, target_level
│   ├── player_brief, player_actor_id, current_module_id
│   └── (Milestone: milestone_id, title, description)
├── module: ModuleState | None
│   ├── module_id, campaign_id, title, summary, guiding_milestone_id
│   ├── planned_encounters: tuple[EncounterTemplate, ...]
│   ├── next_encounter_index
│   └── completed_encounter_summaries: tuple[str, ...]
├── encounter: EncounterState | None
│   ├── encounter_id, phase: EncounterPhase, setting, scene_tone
│   ├── actor_ids, player_actor_id
│   ├── npc_presences: tuple[NpcPresence, ...]
│   ├── public_events: tuple[str, ...]
│   ├── hidden_facts: tuple[str, ...]
│   ├── outcome: str | None
│   └── current_location: str | None
├── actor_registry: ActorRegistry
│   └── actors: dict[str, ActorState]
│       └── (ActorState: full D&D character sheet — HP, AC, ability scores,
│            conditions, death saves, resources, inventory, weapons, feats)
└── combat_state: CombatState | None
    ├── turn_order: TurnOrder
    ├── status: CombatStatus
    ├── current_turn_resources: TurnResources
    └── death_saves_remaining: int | None
```

`NpcPresence` tracks each NPC's identity, display name, name-known status, and
interaction status (`PRESENT`, `INTERACTED`, `AVAILABLE`, `CONCEALED`,
`MENTIONED`, `DEPARTED`). Persistent NPCs travel between encounters via
`EncounterTransition`.

## Repositories

Repositories hide storage layout and provide domain-oriented reads and writes.
All storage is currently file-backed. Each repository owns one data category.

| Repository | File | Stores |
|---|---|---|
| `GameStateRepository` | `game_state_repository.py` | Single JSON blob for campaign, module, encounter, and NPC actor registry. Player state is kept separate via `PlayerRepository`. |
| `PlayerRepository` | `player_repository.py` | Player `ActorState` as JSON. Enriches with compendium reference text on load; strips transient fields on save. |
| `NarrativeMemoryRepository` | `narrative_memory_repository.py` | Narrative events in LanceDB (vector store) + JSONL event log. Supports semantic retrieval, exchange buffer, combat logs, and campaign-scoped clearing. |
| `CompendiumRepository` | `compendium_repository.py` | Read-only D&D 5e content: monsters, equipment, magic items, rules. Provides topic-scoped context retrieval for agents. |
| `CharacterTemplateRepository` | `character_template_repository.py` | Pre-built Level 1 class templates as `ActorState` seeds for character creation. |

`GameStateRepository` is the single persistence facade for structured game
state. It coordinates with `PlayerRepository` on `persist()` — the player actor
is split out and saved separately, preventing player state from being lost if
campaign state is destroyed.

## Adapters

Adapters isolate provider-specific SDK logic. All agent construction goes
through `PydanticAIAdapter`.

| Adapter | File | Wraps |
|---|---|---|
| `PydanticAIAdapter` | `adapters/pydantic_ai_adapter.py` | `pydantic_ai.Agent` with OpenAI or Ollama backend. Exposes `generate_text()` for plain-text output and `model` property for agent construction. Configured from environment via `from_env()`. |
| `OllamaEmbeddingAdapter` | `adapters/embedding_adapter.py` | Ollama REST API (`nomic-embed-text`, 768-dim). Used by `NarrativeMemoryRepository` for vector storage. |
| `StubEmbeddingAdapter` | `adapters/embedding_adapter.py` | Deterministic pseudo-random 768-dim embeddings. Used in tests to avoid Ollama dependency. |

## Tool Layer

Tools perform deterministic operations. They are invoked by orchestrators, not
by agents.

| Tool | File | Function |
|---|---|---|
| `roll` | `tools/dice.py` | Roll a dice expression string using the `multi_dice` library |
| `build_npc_actor` | `tools/npc_generator.py` | Build an `ActorState` from an `EncounterNpc` template, loading compendium stats when available |
| `scale_encounter_npcs` | `tools/cr_scaling.py` | Trim NPC list to fit a CR budget for the player's level |
| `load_by_name` | `tools/monster_loader.py` | Load a monster `ActorState` from the SRD compendium by name |
| `load_by_path` | `tools/monster_loader.py` | Parse a SRD monster markdown file into an `ActorState` |
| `build_index` / `write_index` | `tools/monster_index_parser.py` | Build and write the monster index used for name-based lookup |

## Authority Boundaries

- The Game Orchestrator owns top-level routing and startup detection.
- The Startup Orchestrator owns the returning-player decision flow.
- The Module Orchestrator owns module progression and inter-encounter lifecycle.
- The Encounter Planner Orchestrator owns encounter preparation and divergence recovery.
- The Encounter Orchestrator owns encounter phase and action routing.
- The Combat Orchestrator owns the combat turn loop and death save tracking.
- The Rules Agent owns mechanical interpretation and returns structured results only.
- The Narrator Agent owns player-facing prose only; it must not mutate state or invent mechanics.
- The PlayerIntent Agent owns input classification only.
- Repositories own storage access; no orchestrator reads files directly.
- Tools own deterministic mechanical execution.
- LLM agents may recommend structured decisions; production code validates and applies them.

These boundaries prevent prompt text or generated prose from becoming the
source of truth for game state, and prevent any single component from
accumulating control it does not own.

## Interaction Model

The current interaction boundary is CLI `STDIN` and `STDOUT` via `TerminalIO`.

`TerminalIO` uses `input()` for single-line reads and an `input()`-based loop
for multiline input (blank line or EOF terminates). This bypasses macOS
terminal canonical-mode buffer limits for long text pastes.

Acceptance tests act as scripted players by injecting structured input through
`TerminalIO` and asserting on `STDOUT`. This keeps tests on the same interaction
path as a real user.

A future UI should replace the CLI boundary without changing the orchestrator
or agent contracts.

## Lifecycle Boundaries

Encounters and modules have independent lifecycles and must not be conflated.

An **encounter** is a game-world state machine with phase transitions, rules
calls, dice handling, and completion logic. Encounter state persists in
`GameStateRepository`. An encounter may start and complete within one play
session, or it may span multiple sessions.

A **module** is a story arc containing a sequence of planned encounters. The
`ModuleOrchestrator` manages encounter progression within a module and advances
to the next module when the guiding milestone is achieved.

A **campaign** is the top-level story container. It holds milestones, BBEG,
setting, and the narrator personality. The current module is tracked within
`CampaignState`.

## Testing Boundaries

Unit tests verify one logical unit and may mock internal collaborators. They
live under `tests/unit/` and count toward coverage. Target: 90% or better at
the project level.

Integration tests verify interactions between internal production components.
They live under `tests/integration/` and do not count toward coverage.

Acceptance tests verify the full deployment unit through the CLI, using
WireMock to fake the OpenAI API. They must not mock production code and do not
count toward coverage.

Tests must not expose private methods or promote internal constants to test
them. The correct test for prompt wiring is an injection seam test that asserts
the expected constant reaches the `Agent` constructor, not a string content
assertion.
