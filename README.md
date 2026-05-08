# CampaignNarrator

A local, LLM-assisted tabletop RPG narrator and rules adjudication system for solo D&D 5e play. The application acts as a Dungeon Master: it generates campaigns, plans encounters, adjudicates rules, rolls dice, tracks state, and narrates outcomes, all driven by a conversational CLI.

This is the final project for **CSC 7644: Applied LLM Development**.

The project addresses a known limitation of LLMs: they generate compelling content but struggle to maintain coherence and consistency across long, stateful interactions. CampaignNarrator investigates whether a multi-agent architecture with structured persistence (canonical game state, rules adjudication, and vector-backed narrative memory) can overcome these limitations. Solo D&D is the test domain because it demands a persistent Dungeon Master role: it combines long-running narrative, structured rules, and evolving state in a controlled, evaluable environment. See [docs/project/Martin_Yance_proposal.md](docs/project/Martin_Yance_proposal.md) for the full project proposal.

## Key Features

- **Full campaign generation**: creates a campaign, milestones, and a multi-encounter module from a short player backstory
- **Adaptive encounter planning**: detects narrative divergence and replans or inserts bridge encounters to keep the story coherent
- **Rules adjudication**: interprets free-text player actions against D&D 5e SRD rules, rolls dice, and applies effects to game state
- **Persistent narrative memory**: stores and retrieves session summaries via a vector store so the narrator maintains consistency across sessions
- **NPC presence tracking**: tracks named and unnamed NPCs, their interaction history, and their status across encounters
- **Save and resume**: game state is persisted after every turn; mid-encounter saves are fully supported
- **Two LLM backends**: runs entirely locally via a Dockerized Ollama instance, or against the OpenAI API with no local model required
- **LLM-assisted character creation**: drafts and refines player backstory through a guided dialogue

## Tech Stack

| Layer | Technology |
|---|---|
| LLM (local) | [Ollama](https://ollama.com) (`orieg/gemma3-tools:12b-ft-v2` by default), served via Docker |
| LLM (cloud) | [OpenAI API](https://platform.openai.com) (`gpt-4o-mini` by default) |
| Embeddings | Ollama (`nomic-embed-text`) |
| LLM framework | [pydantic-ai](https://ai.pydantic.dev): structured agent outputs via Pydantic models |
| Vector store | [LanceDB](https://lancedb.github.io/lancedb/): on-disk vector search for narrative memory |
| Data validation | [Pydantic](https://docs.pydantic.dev) / [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) |
| Package manager | [Poetry](https://python-poetry.org) |
| Containerisation | [Docker](https://www.docker.com) (Ollama only) |
| Testing | [pytest](https://docs.pytest.org), [pytest-bdd](https://pytest-bdd.readthedocs.io) |
| Linting / security | [ruff](https://docs.astral.sh/ruff/), [bandit](https://bandit.readthedocs.io) |

### Architecture overview

The application is a multi-agent, single-process Python service with no web server:

- **Orchestration layer**: a hierarchy of orchestrators (`GameOrchestrator` → `ModuleOrchestrator` → `EncounterOrchestrator` → `CombatOrchestrator`) provides deterministic control flow; LLM agents are consulted at decision points but never control the loop.
- **Agent layer**: single-responsibility agents for narration, rules adjudication, intent classification, encounter planning, character backstory, and campaign/module generation. Each agent has a fixed output schema enforced by pydantic-ai.
- **State layer**: immutable, Pydantic-validated domain objects (`GameState`, `EncounterState`, `ActorState`, etc.) persisted as JSON after every mutation.
- **Memory layer**: completed encounter summaries stored in LanceDB; retrieved by semantic search to give the narrator relevant prior-session context.
- **Compendium**: static D&D 5e SRD data (rules, monsters, items) loaded from disk; used by the rules agent and NPC builder.

See [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md) for full design details.

## Requirements

- macOS or Linux (WSL2 supported)
- **Python 3.14+**: required by the project dependencies; see pyenv note below
- [Docker Desktop](https://docs.docker.com/desktop/) with at least 12 GB RAM allocated (20 GB recommended for the default model)
- [pyenv](https://github.com/pyenv/pyenv): recommended for installing Python 3.14 if your system ships an older version (`pyenv install 3.14.0`)
- [Poetry](https://python-poetry.org/)
- `make`

Running with OpenAI as the LLM provider (see below) reduces the Docker memory requirement to whatever Ollama needs for embeddings only (~1 GB).

### Before you run `make bootstrap`

`make bootstrap` automates everything else, but two things must be in place first:

**1. Docker Desktop must be installed and running.**

- **macOS:** Download and install [Docker Desktop for Mac](https://docs.docker.com/desktop/install/mac-install/). Start it and wait for the whale icon to appear in the menu bar before continuing.
- **WSL2 (Windows):** Install [Docker Desktop for Windows](https://docs.docker.com/desktop/install/windows-install/) and enable WSL 2 integration in Settings → Resources → WSL Integration. `make bootstrap` will exit with an error and a link if Docker is not present.
- **Linux (native):** Docker is installed automatically by `make bootstrap`. No prior action needed.

**2. Linux only: add `host.docker.internal` to `/etc/hosts`:**

```bash
echo "127.0.0.1 host.docker.internal" | sudo tee -a /etc/hosts
```

This is required for the CLI to reach the Dockerized Ollama instance. `make bootstrap` exits with an error if the entry is missing.

## Quick Start

```bash
# 1. Install dependencies
make bootstrap

# 2. Configure credentials
cp .env.secrets.example .env.secrets
# If using OpenAI: add your API key (get one at https://platform.openai.com/api-keys)
# OPENAI_API_KEY=sk-...

# 3. Run with the local Ollama model (default)
make run_local

# OR: Run with OpenAI as the LLM backend
make run_local ARGS="--env openai"
```

> **Recommended:** Use `make run_local ARGS="--env openai"` if you have an OpenAI API key. It skips the 7 GB model download, requires far less RAM, and produces noticeably better narration quality. The local Ollama path is provided for fully offline use.

On first run, `make run_local` starts a Dockerized Ollama instance, pulls the model (~7 GB), and warms it up before handing control to the game. Subsequent runs are fast because models are cached in `~/.ollama`.

## Environment Configuration

The runtime environment is controlled by three layered files. They are loaded in this order on every `make run_local` invocation:

```
.env.secrets   (loaded first, credentials never committed)
.env           (loaded second, default Ollama profile)
               OR
.env.openai    (loaded second, OpenAI profile, when --env openai is passed)
```

Later values override earlier ones, so a key in `.env` or `.env.openai` can be overridden at the shell level.

### `.env.secrets`

Contains actual secrets. **Never committed to version control.**

```bash
cp .env.secrets.example .env.secrets
```

| Key | Purpose |
|---|---|
| `OPENAI_API_KEY` | Required when `LLM_PROVIDER=openai`. Ignored by Ollama. |

The Ollama profile sets `OPENAI_API_KEY=ollama` (a placeholder) so the adapter initialises even when no real key is needed.

### `.env`: Default (Ollama) Profile

Used by `make run_local` with no arguments. Runs the LLM locally via a Dockerized Ollama instance.

```bash
# Already exists. Edit to customise, or leave as-is.
```

Key settings:

| Key | Default | Purpose |
|---|---|---|
| `DATA_ROOT` | `var/data_store` | Where all runtime state is stored |
| `LLM_PROVIDER` | `ollama` | Tells the adapter not to validate the API key |
| `OPENAI_BASE_URL` | `http://localhost:11434/v1` | Points to the local Ollama instance |
| `OPENAI_MODEL` | `orieg/gemma3-tools:12b-ft-v2` | Local model name |
| `OPENAI_API_KEY` | `ollama` | Placeholder; Ollama ignores it |
| `EMBEDDING_PROVIDER` | `ollama` | Embedding backend |
| `EMBEDDING_MODEL` | `nomic-embed-text` | Embedding model pulled automatically |

### `.env.openai`: OpenAI Profile

Used by `make run_local ARGS="--env openai"`. Uses the OpenAI API for the LLM while still running Ollama locally for embeddings.

```bash
# Already exists. No edits needed if OPENAI_API_KEY is in .env.secrets.
```

Key settings:

| Key | Value | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `openai` | Skips local model pull and warmup |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Real OpenAI endpoint |
| `OPENAI_MODEL` | `gpt-4o-mini` | OpenAI model to use |
| `EMBEDDING_PROVIDER` | `ollama` | Embeddings still run locally |

With this profile, Docker only needs to run Ollama for embeddings. The 12 GB Docker memory requirement drops significantly.

### Example Files

Each file has an `.example` counterpart that is safe to commit and shows all available keys with placeholder values:

```
.env.example
.env.openai.example
.env.secrets.example
```

If a profile file is missing when `make run_local` runs, the script automatically copies the `.example` version and prints a warning.

## Make Targets

| Target | Description |
|---|---|
| `make bootstrap` | Install system dependencies, Python, Poetry, and project packages |
| `make run_local` | Start Ollama and launch the game (Ollama LLM) |
| `make run_local ARGS="--env openai"` | Start Ollama (embeddings) and launch the game (OpenAI LLM) |
| `make control` | Run the experiment control session (see below) |
| `make stop_local` | Stop the Dockerized Ollama instance |
| `make clear_state` | Delete all runtime state in `DATA_ROOT` (actors, campaign, memory) |
| `make unit_test` | Run unit tests with coverage report |
| `make integration_test` | Run integration tests |
| `make acceptance_test` | Run acceptance tests (requires WireMock / OpenAI fake) |
| `make test` | Run unit + integration + acceptance tests |
| `make verify` | Full clean build: bootstrap → lint → security scan → all tests |
| `make analyze_code` | Run ruff (lint + format check) and bandit (security scan) |
| `make format` | Auto-format source with ruff |
| `make clean` | Remove build artifacts, Poetry env, caches |

`make verify` is the gate for all commits. It runs a clean bootstrap before the test suite, so it is slower than `make test` but guaranteed to reflect a clean state.

## Running the Game

```bash
make run_local
# or, recommended:
make run_local ARGS="--env openai"
```

The script starts Ollama in Docker, pulls any missing models, seeds static game data, and launches the CLI. Everything after `make run_local` is automatic.

### Running two instances simultaneously

Two independent game sessions can run side-by-side. The second instance reuses the already-running Ollama container automatically; only the state directory needs to differ:

```bash
# Terminal 1 — first session (default state directory)
make run_local ARGS="--env openai"

# Terminal 2 — second session (separate state directory)
DATA_ROOT=var/data_store_2 make run_local ARGS="--env openai"
```

Each instance maintains its own character, campaign, and narrative memory under its `DATA_ROOT`. `make clear_state` only clears the default `var/data_store`; to clear a custom root run `rm -rf var/data_store_2` directly.

### First run: character creation

On first launch there is no saved character, so the game walks through creation before the first encounter:

```
Please choose a class:
  1. Fighter
  2. Rogue
  3. Wizard
  ...
> 1

What are you called?
> Aldric

What is your heritage? (Human, Elf, Dwarf, Halfling, Half-Elf, Half-Orc, Gnome, Dragonborn, Tiefling)
> Human

Describe your past in your own words.
You can paste multiple lines; press Enter twice when done.
If you would like help crafting a backstory, just say 'help'.
> A retired soldier who turned to adventuring after his village was razed.

Describe your appearance.
You can write as much as you like; press Enter twice when done.
> Tall and weathered, with a scar running across his jaw.
```

If you type `help` at the backstory prompt the narrator drafts a backstory for you. It will show the draft and ask you to accept it or describe changes; it will iterate up to three times.

After character creation the system generates a campaign and the first encounter. This takes 30–90 seconds on first run.

### Returning player: startup prompt

On every subsequent run the game greets you and asks what you want to do:

```
Welcome back, Aldric. Your campaign 'The Flufflemarch Follies' awaits.
Would you like to load it, or start a new campaign?
> load
```

**Loading your campaign** resumes exactly where you left off. If you were mid-encounter, the game replays the recent exchange buffer and then generates a narrator recap before returning control to you:

```
--- Resuming session ---
[prior exchange replay]
---
[narrator recap of where you left off]
>
```

**Starting a new campaign** permanently destroys the current campaign and all its narrative memory. The game asks for explicit confirmation:

```
Starting a new campaign will permanently destroy your current story.
The threads of your past will be lost to the void.
Are you certain? (type 'yes, destroy it' to confirm, or anything else to cancel)
> yes, destroy it
```

Type `yes, destroy it` exactly to proceed; anything else cancels. Your character (class, name, race, backstory) is preserved; only the campaign and encounter history is erased. The campaign creation flow then runs from the player brief prompt.

> **Note:** If you type something unrecognised at either prompt, or cancel the destruction confirmation, the game exits silently. This is intentional: no destructive action is taken, but you will need to run `make run_local` again.

### Gameplay loop

Once inside an encounter the game presents a `>` prompt and accepts free-text input. There are no typed commands; just describe what your character does:

```
> I look around the tavern for anyone acting suspicious.
> I try to persuade the innkeeper to give us a room for free.
> I draw my sword and attack the guard.
```

The system classifies your intent automatically and routes it to narration, a skill check, NPC dialogue, or combat accordingly.

**Useful inputs the system recognises:**

| What you type (examples) | What happens |
|---|---|
| `status` / `how am I doing` | Narrator describes your HP, inventory, and visible actors |
| `recap` / `what happened` | Narrator summarises all public events so far |
| `look around` / `examine the room` | Narrator describes the current location and what is visible |
| `save and exit` / `quit` / `I need to stop` | Game is saved and the CLI exits (see below) |

### Combat

Combat starts automatically when you take a hostile action. Initiative is rolled and the turn order is displayed:

```
Initiative: Aldric 18, Guard Captain 14, Town Guard 9.
[narrator describes the combat opening]

> I attack the guard captain with my longsword.
```

During combat the prompt remains `>`. Each turn you describe your action in free text. The system determines the attack roll, applies damage, and narrates the result. NPC turns are handled automatically between your turns.

Combat ends when all enemies are dead or fled, or when you save and exit.

### Saving and exiting

At any prompt (social encounter or combat), type a natural save-and-exit phrase:

```
> save and exit
Game saved. You can resume this encounter later.
```

The game writes all state to disk before exiting. The next `make run_local` will resume exactly from this point.

### Starting a fresh game

To wipe all saved state and start over with a new character:

```bash
make clear_state
make run_local
```

`make clear_state` deletes everything under `DATA_ROOT` (character, campaign, encounter state, narrative memory). It is irreversible.

## Project Structure

```
app/campaignnarrator/
├── agents/          # LLM agents (each wraps one pydantic_ai.Agent)
├── adapters/        # Provider isolation (PydanticAI, Ollama embeddings)
├── domain/models/   # Immutable game state (GameState, ActorState, etc.)
├── orchestrators/   # Control flow (game, campaign, encounter, combat)
├── repositories/    # Storage (GameState JSON, player JSON, LanceDB memory)
├── tools/           # Deterministic logic (dice, NPC builder, CR scaling)
├── application_factory.py  # Wires all components together
├── cli.py           # Entry point
└── settings.py      # Environment-backed configuration

tests/
├── unit/            # Unit tests (counted toward coverage target: 90%)
├── integration/     # Integration tests (not counted toward coverage)
└── acceptance/      # Full-stack tests through CLI (not counted toward coverage)

bin/                 # Shell scripts backing every make target (bootstrap, run, test, etc.)
control/             # Experiment control: bare GPT narrator with no persistence
data/                # Static game data seeded into DATA_ROOT on first run

docs/
└── project/         # Original project proposal (Martin_Yance_proposal.md / .pdf)

var/data_store/      # Default runtime state (gitignored)
```

## Experiment Control

CampaignNarrator is the subject of a thesis investigating whether structured
persistence (canonical game state, rules adjudication, narrative memory, and
encounter planning) produces measurably better play quality than a raw LLM
conversation.

`make control` runs the **experimental control condition**: a bare D&D narrator
with no persistence, no rules engine, no encounter planning, and no structured
state. It is a single system prompt fed directly to the OpenAI API in a plain
chat loop. Nothing survives beyond the current conversation window.

```bash
make control
```

Prerequisites: `OPENAI_API_KEY` in `.env.secrets` and `.env.openai` present
(both created during Quick Start). No Docker, no Ollama, no local model
required.

What the control session does **not** have, compared to the full system:

| Capability | Control | CampaignNarrator |
|---|---|---|
| Persistent campaign and character state | No | Yes |
| Structured encounter planning | No | Yes |
| Rules adjudication with dice and effects | No | Yes |
| Narrative memory across sessions | No | Yes |
| NPC tracking across encounters | No | Yes |
| Save and resume mid-encounter | No | Yes |

The control isolates the contribution of the application's architecture. Side-by-side play sessions between `make control` and `make run_local ARGS="--env openai"` (same model, same provider) form the basis of qualitative and quantitative evaluation in the thesis.

The control source lives in `control/narrator.py`.

## Development

```bash
# Run unit tests only (fast)
make unit_test

# Run the full verification suite before pushing
make verify

# Format code
make format

# Watch unit tests during development
make watch_unit_tests
```

All lint violations must be fixed before commit; `# noqa` suppression is not permitted. Run `make analyze_code` to check.

## Attributions and Citations

**D&D 5e Systems Reference Document (SRD 5.1)**
The compendium data in `data/compendium/DND.SRD.Wiki-0.5.2/` is derived from the SRD 5.1 by Wizards of the Coast LLC, available at https://dnd.wizards.com/resources/systems-reference-document. Licensed under the [Creative Commons Attribution 4.0 International License](https://creativecommons.org/licenses/by/4.0/legalcode).

**DND.SRD.Wiki**
The SRD content was sourced in Markdown form from the [DND.SRD.Wiki](https://github.com/OldManUmby/DND.SRD.Wiki) project by OldManUmby (v0.5.2). No code was adapted; only the data files are used.

**pydantic-ai**
The agent and structured-output patterns follow the [pydantic-ai documentation](https://ai.pydantic.dev). No tutorial code was copied directly; the adapter and agent wrappers are original implementations.

**LanceDB**
Vector storage and retrieval follow the [LanceDB Python SDK documentation](https://lancedb.github.io/lancedb/). No example code was copied directly.
