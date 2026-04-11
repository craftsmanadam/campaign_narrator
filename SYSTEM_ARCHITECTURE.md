# System Architecture

This document records the current architectural understanding for
CampaignNarrator. It is a living design reference, not a replacement for
time-scoped feature specs or the engineering rules in `AGENTS.md`.

## Purpose

CampaignNarrator is a local, LLM-assisted tabletop RPG narrator and rules
adjudication system. Its purpose is to let a solo player interact with a
campaign-like experience where the application coordinates scene flow, rules,
dice, state, and narration.

The system should feel like interacting with a Dungeon Master, while keeping
mechanical authority, state changes, and test boundaries explicit.

## Deployment Boundary

Inside the deployment unit:

- CLI or future UI boundary
- Orchestrator
- Rules Agent
- Narrator Agent
- repositories
- tool layer
- runtime state
- real OpenAI adapter
- real dice library usage

Outside the deployment unit:

- OpenAI HTTP API
- future network dependencies

Acceptance tests may fake external network dependencies, such as OpenAI, but
must not mock production code inside the deployment unit.

## Core Responsibilities

### CLI

The CLI is the temporary user interface. It owns terminal interaction through
`STDIN` and `STDOUT`.

The CLI should not contain game logic, scripted player behavior, rules
adjudication, or narration decisions.

### Orchestrator

The Orchestrator is the application control authority.

It owns:

- encounter startup and completion
- current phase
- routing player input
- deciding when rules adjudication is required
- deciding when narration is required
- deciding when player input is required
- invoking tools
- validating agent outputs
- applying state mutations
- enforcing combat sequencing
- returning user-facing results to the CLI

The Orchestrator may use bounded LLM calls to assist with non-combat scene flow,
but it must retain authority over validation, phase transitions, state
mutation, and failure behavior.

### Rules Agent

The Rules Agent owns mechanical interpretation.

It receives structured adjudication requests from the Orchestrator and returns
structured mechanical results. It should know or retrieve relevant rules and
compendium data, but it must not mutate state directly.

### Narrator Agent

The Narrator Agent owns player-facing expression.

It receives resolved facts and narration frames from the Orchestrator. It may
write descriptions and dialogue, but it must not invent mechanics, mutate state,
or directly call the Rules Agent.

### Repositories

Repositories hide storage layout and provide domain-oriented reads and writes.
Files on disk are acceptable for the current stage. Durable encounter
persistence is not required until the design reaches the last responsible
moment for save/load behavior.

### Tool Layer

Tools perform deterministic operations such as dice rolling and state update
application. Tools should be invoked by the Orchestrator or by narrowly scoped
application services, not directly by narration.

## Authority Boundaries

- The Orchestrator owns control flow.
- The Rules Agent owns rules interpretation.
- The Narrator Agent owns prose, dialogue, and player-facing presentation.
- Repositories own storage access.
- Tools own deterministic mechanical execution.
- OpenAI may recommend structured decisions, but production code validates and
  applies them.

These boundaries are intended to prevent prompt text or generated prose from
becoming the source of truth for game state.

## Interaction Model

The current interaction boundary is CLI `STDIN` and `STDOUT`.

Acceptance tests act as scripted players by piping input into the CLI process
and asserting output from `STDOUT`. This keeps tests on the same interaction
path as a real user.

A future UI should replace the CLI boundary without changing Orchestrator,
Rules Agent, or Narrator Agent contracts.

## State Model

For the current encounter-loop work, runtime state may be held in memory and
seeded from fixture or repository data.

Runtime state should distinguish:

- player-visible facts
- hidden narrator/world facts
- canonical state
- derived narration context
- recent event history

Acceptance tests should verify state through ordinary player-visible queries
such as `status`, `look around`, or `what happened`, not through privileged
test-only state inspection.

## Testing Boundaries

Unit tests verify one logical unit and may mock internal collaborators except
the unit under test.

Integration tests verify interactions between internal production components.
They live under `tests/integration` and do not count toward coverage.

Acceptance tests verify the full deployment unit through the CLI. They may fake
external network dependencies such as OpenAI, typically with Dockerized
WireMock. They must not mock production code and do not count toward coverage.

Only unit tests count toward project coverage.

## Current Constraints

The next encounter-loop cut is intentionally constrained to:

- one encounter template
- one player character
- Fighter support required at a minimum
- goblin support required if available in the corpus
- basic dialogue
- basic skill checks
- basic combat
- basic equipment and potion handling
- deterministic acceptance tests

These constraints define the next implementation slice, not permanent product
limits.

## Open Design Questions Not Yet At LRM

### Combat And Non-Combat Sub-Orchestration

The Orchestrator currently owns all flow. It may eventually benefit from
specialized collaborators for combat flow and non-combat flow.

This split is not introduced yet. The next encounter-loop implementation should
watch for natural pressure toward this seam without creating premature
abstractions.

### Durable Persistence

In-memory encounter state is acceptable for the next cut. Durable save/load
behavior should be designed when the project needs multi-session continuity.

### Retrieval And Storage Strategy

Files on disk remain acceptable for current corpus and fixture data. Database,
document-store, and vector-store decisions are deferred until retrieval needs
exceed simple file-backed access.

### User Interface

The CLI is the current UI boundary. A richer UI is expected later, but its shape
is not yet at the last responsible moment.

### Player-Interactive Dice

The system must preserve roll ownership and visibility so player-facing rolls
can later become interactive. The next cut may still roll automatically.

### Dungeon Master Personality

Narrator personality styles are deferred. The current narrator may rely on
default LLM behavior, while preserving a contract that can later accept tone or
personality guidance.
