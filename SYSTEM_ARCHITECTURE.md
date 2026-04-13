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
- Orchestrators
- Rules Agent
- Narrative Director
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
adjudication, or narration decisions. It wires the application graph and
delegates entirely to the Application Orchestrator.

### Orchestration Hierarchy

Orchestrators are the application's control authorities. Each owns a specific
lifecycle boundary and delegates to subordinate orchestrators or agents for
work outside its scope. No orchestrator should absorb responsibilities that
belong to another layer.

Orchestrators live under `app/campaignnarrator/orchestrators/`.

#### Application Orchestrator

The Application Orchestrator is the top-level router. It reads persisted state
on startup and routes to the appropriate sub-orchestrator based on what the
current game state requires:

- No campaign exists → Campaign Orchestrator
- Campaign exists but no character → Character Creation Orchestrator
- Campaign and character exist → Session Orchestrator

The Application Orchestrator also handles in-progress state detection. If an
encounter was saved mid-session, the Session Orchestrator is responsible for
detecting and resuming it. The Application Orchestrator delegates that decision
rather than routing directly to the Encounter Orchestrator.

#### Campaign Orchestrator

The Campaign Orchestrator owns campaign creation. It turns player preferences
such as tone, genre, setting inspiration, and desired play style into
structured campaign canon, including campaign premise, constraints, DM
personality, major conflicts, starting locations, important NPC seeds, and
content boundaries.

#### Character Creation Orchestrator

The Character Creation Orchestrator owns the character build flow. It guides
the player through species, origin or background, class, ability scores,
proficiencies, equipment, spells, and derived statistics. It relies heavily on
the rules and compendium repositories and produces a validated player character
state object.

#### Session Orchestrator

The Session Orchestrator owns a single play window. A session is a real-world
calendar event bounded by player availability, not by game state. The Session
Orchestrator does not own the encounter lifecycle.

It loads campaign canon, mutable runtime state, and derived memory at the
start of a play window. During the session it routes player input to the
correct workflow:

- If an encounter is in progress (saved state exists) → Encounter Orchestrator (resume)
- If no active encounter → await player intent
  - Player initiates an encounter → Encounter Orchestrator (new)
  - Player explores, rests, or takes other narrative actions → future flows
  - Player saves and quits → session ends; encounter state is already persisted

When an encounter completes, control returns to the Session Orchestrator, which
then waits for the next player intent. Multiple encounters may start and
complete within a single session. A session may also end mid-encounter without
that encounter ending.

The Session Orchestrator records session-level events such as session started
and session ended, including a summary of what occurred during the play window.

#### Encounter Orchestrator

The Encounter Orchestrator owns tactical encounter resolution. It is the
current implemented steel thread in `app/campaignnarrator/orchestrators/encounter_orchestrator.py`.

It tracks encounter phase, routes player input, requests rules adjudication,
executes dice and state effects, constructs narration frames, and determines
when an encounter completes. Encounter state persists independently of session
boundaries, so an encounter may begin in one session and complete in another.

### Narrative Director

The Narrative Director owns story-level authority. It is distinct from the
Narrator Agent, which only converts resolved facts into prose.

The Narrative Director holds narrative intent for the current session and
encounter, shapes pacing and dramatic tension, and may flag a narrative
preferred outcome to the Session Orchestrator when story considerations should
take precedence over mechanical outcomes. This includes the Rule of Cool: the
right to allow a dramatically appropriate action to succeed even when the
mechanical result would not support it.

The Session Orchestrator consults the Narrative Director before routing to the
Rules Agent when narrative intent may affect the outcome. The Narrative
Director does not call the Rules Agent directly. Narrative override authority
flows through the Session Orchestrator, which validates and applies it.

The Narrative Director's personality, tone, Rule of Cool threshold, and
storytelling preferences are configured from campaign canon authored during
campaign creation. The details of how DM personality is represented, loaded,
and applied are deferred until the Campaign Orchestrator is implemented.

### Rules Agent

The Rules Agent owns mechanical interpretation.

It receives structured adjudication requests from the Encounter Orchestrator
and returns structured mechanical results. It should know or retrieve relevant
rules and compendium data, but it must not mutate state directly.

### Narrator Agent

The Narrator Agent owns player-facing expression. It is a thin, reactive
component that converts resolved facts and narration frames into descriptive
prose and dialogue.

It receives narration frames from the Encounter Orchestrator. It may write
descriptions and dialogue, but it must not invent mechanics, mutate state,
make story-direction decisions, or directly call the Rules Agent or Narrative
Director.

### Repositories

Repositories hide storage layout and provide domain-oriented reads and writes.
Files on disk are acceptable for the current stage. Each repository owns one
data category:

- Rules repository: curated SRD rule source and generated indexes
- Compendium repository: structured content for spells, monsters, equipment, and character options
- State repository: mutable runtime truth including encounter, player character, world state, and campaign state
- Memory repository: derived artifacts including the append-only event log and session summaries
- Narrative repository: canonical campaign and narrative data

### Tool Layer

Tools perform deterministic operations such as dice rolling and state update
application. Tools should be invoked by the Encounter Orchestrator or by
narrowly scoped application services, not directly by agents.

## Authority Boundaries

- The Application Orchestrator owns top-level routing and startup.
- The Session Orchestrator owns the play window lifecycle and narrative flow.
- The Encounter Orchestrator owns encounter phase and tactical resolution.
- The Narrative Director owns story-level intent and may veto mechanical outcomes through the Session Orchestrator.
- The Rules Agent owns mechanical interpretation within the bounds set by the orchestrator.
- The Narrator Agent owns player-facing prose only.
- Repositories own storage access.
- Tools own deterministic mechanical execution.
- OpenAI may recommend structured decisions, but production code validates and applies them.

These boundaries are intended to prevent prompt text or generated prose from
becoming the source of truth for game state, and to prevent any single
component from accumulating control it does not own.

## Lifecycle Boundaries

Sessions and encounters have independent lifecycles and must not be conflated.

A **session** is a real-world play window bounded by player availability. The
system has no authority over when a session starts or ends. A player may end a
session at any point, including mid-encounter. The Session Orchestrator tracks
what occurred during a play window for recap and memory purposes.

An **encounter** is a game-world state machine with its own phase transitions,
rules calls, dice handling, and completion logic. Encounter state persists
independently. An encounter may start and complete within a single session, or
it may span multiple sessions. A session may contain multiple encounters, and a
session may end mid-encounter as a deliberate cliff-hanger.

Session events and encounter events are recorded as independent streams in the
event log:

- Session events: session started, session ended (with what occurred summary)
- Encounter events: encounter started, encounter saved, encounter completed

## Interaction Model

The current interaction boundary is CLI `STDIN` and `STDOUT`.

Acceptance tests act as scripted players by piping input into the CLI process
and asserting output from `STDOUT`. This keeps tests on the same interaction
path as a real user.

A future UI should replace the CLI boundary without changing the orchestrator
or agent contracts.

## State Model

Runtime state distinguishes:

- player-visible facts
- hidden narrator or world facts
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

The current implementation is intentionally constrained to:

- one encounter template
- one player character
- Fighter support required at a minimum
- goblin support required if available in the corpus
- basic dialogue
- basic skill checks
- basic combat
- basic equipment and potion handling
- deterministic acceptance tests

These constraints define the current implementation slice, not permanent product
limits.

## Open Design Questions Not Yet At LRM

### Durable Persistence

In-memory encounter state is acceptable for the current cut. File-backed
encounter persistence is in progress. Durable save and resume behavior should
be fully validated through acceptance tests before the Session Orchestrator
is implemented.

### Retrieval And Storage Strategy

Files on disk remain acceptable for current corpus and fixture data. Database,
document-store, and vector-store decisions are deferred until retrieval needs
exceed simple file-backed access. The Rules Agent currently relies on base model
knowledge rather than active retrieval from the rules corpus. Corpus retrieval
should be addressed before the project expands to a second encounter type.

### Narrative Director Personality

The Narrative Director's personality, tone, Rule of Cool threshold, and
storytelling style are configured from campaign canon. How DM personality is
represented, validated, loaded, and applied to Narrative Director behavior is
deferred until the Campaign Orchestrator is implemented.

### User Interface

The CLI is the current UI boundary. A richer UI is expected later, but its
shape is not yet at the last responsible moment.

### Player-Interactive Dice

The system must preserve roll ownership and visibility so player-facing rolls
can later become interactive. The current cut may still roll automatically.

### Session Orchestrator And Between-Encounter Flow

Between encounters within a session, the player may eventually explore, rest,
take downtime actions, or engage in narrative dialogue. The Session
Orchestrator's routing for these flows is deferred until a second encounter
type or explicit between-encounter activity is needed.
