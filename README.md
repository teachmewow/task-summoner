# Task Summoner

[![CI](https://github.com/teachmewow/task-summoner/actions/workflows/ci.yml/badge.svg)](https://github.com/teachmewow/task-summoner/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Local-first agentic board management.** Connect your board (Jira or Linear), point it at a code agent (Claude Code or Codex), and Task Summoner drives the full development lifecycle — from design doc to code review — with human approval at every gate.

```
Label 'task-summoner' ──→ [DESIGN DOC] ──lgtm──→ [PLAN] ──lgtm──→ [CODE] ──lgtm──→ Done
                               │                    │                 │
                          Agent writes         Agent plans       Agent implements
                          design doc           approach          + opens PR
```

## Why

Existing agentic SDLC tools are cloud services that dispatch thousands of tasks against managed LLMs. Task Summoner is the opposite: it runs on **your** machine, uses **your** CLI billing (Claude Code, Codex), and gives **you** a gate at every phase. Open-source, provider-agnostic, build-in-public.

## Repo layout

```
task-summoner/
├── backend/     # Python orchestrator + FastAPI (pytest, ruff)
└── frontend/    # React 19 + TS + Vite + TanStack Router (pnpm, biome, vitest)
```

## Quick start

```bash
# Clone
git clone https://github.com/teachmewow/task-summoner.git
cd task-summoner

# Backend
cd backend
uv venv ../.venv && source ../.venv/bin/activate
uv pip install -e ".[dev]"

# Frontend (first run: build the UI bundle)
cd ../frontend
pnpm install
pnpm build

# Run
task-summoner setup   # one-time config
task-summoner run     # http://localhost:8420
```

### Dev mode (hot reload on both sides)

```bash
task-summoner run --dev     # uvicorn :8420 + vite :5173
# open http://localhost:5173 — vite proxies /api/* back to uvicorn
```

## Architecture

Three abstraction layers — the core knows nothing about specific providers:

```
┌──────────────────────────────────┐
│       task-summoner core         │
│   (FSM, states, orchestrator)    │
└───────┬──────────────┬───────────┘
        │              │
┌───────▼───────┐ ┌────▼──────────┐
│ BoardProvider │ │ AgentProvider │
│  (protocol)   │ │  (protocol)   │
└───────┬───────┘ └────┬──────────┘
   ┌────┴────┐    ┌────┴──────┐
   │Jira│Linear│ │Claude│Codex│
   └────┴─────┘ │ Code │    │
                └──────┴────┘
```

- **Board Provider**: Jira or Linear (more coming)
- **Agent CLI Provider**: Claude Code or Codex (more coming)
- **Core**: deterministic FSM, state handlers, orchestrator — pure Python, no provider imports

The abstraction boundary is enforced at test time (`tests/test_provider_isolation.py`): no file under `core/`, `states/`, `runtime/`, or `models/` may import from a concrete provider module.

## How it works

1. You label a ticket `task-summoner` on your board.
2. The orchestrator picks it up, creates a git worktree, and runs through the state machine:

   ```
   QUEUED -> CHECKING_DOC -> CREATING_DOC -> WAITING_DOC_REVIEW
          -> PLANNING     -> WAITING_PLAN_REVIEW
          -> IMPLEMENTING -> WAITING_MR_REVIEW -> DONE
   ```
3. At each review gate, reply `lgtm` to approve or `retry` with feedback.
4. The agent posts tagged comments (`[ts:TICKET:state:id]`) so approval tracking survives restarts.

## Configuration

```yaml
providers:
  board:
    type: linear
    linear:
      api_key: ${LINEAR_API_KEY}
      team_id: "your-team-id-uuid"
      watch_label: task-summoner
  agent:
    type: claude_code
    claude_code:
      auth_method: personal_session  # uses your logged-in Claude Code session
      # or: auth_method: api_key + api_key: ${ANTHROPIC_API_KEY}
      plugin_mode: installed

repos:
  my-project: ~/code/my-project
default_repo: my-project

agent_profiles:
  doc_checker: { model: haiku,  max_turns: 20,  max_budget_usd: 5 }
  standard:    { model: sonnet, max_turns: 200, max_budget_usd: 50 }
  heavy:       { model: opus,   max_turns: 500, max_budget_usd: 50 }

polling_interval_sec: 10
```

See [`backend/config.yaml.example`](backend/config.yaml.example) for the full annotated schema.

## Testing

```bash
# Backend
cd backend
pytest                 # all tests
ruff check src tests   # lint

# Frontend
cd frontend
pnpm test              # vitest
pnpm build             # tsc --noEmit + vite build
pnpm lint              # biome
```

CI runs both pipelines on every PR (Python 3.11 + 3.12, Node 22).

## Project

Part of the [TeachMeWoW](https://github.com/teachmewow) ecosystem. Licensed under [MIT](LICENSE). See [CONTRIBUTING.md](CONTRIBUTING.md) to get involved.
