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

### User-level config (`task-summoner config`)

Per-user preferences that skills need at runtime live in a separate file at
`$XDG_CONFIG_HOME/task-summoner/config.json` (defaults to
`~/.config/task-summoner/config.json`). This is distinct from the project-level
`config.yaml` above. Today the only key is `docs_repo` — the absolute path to
the git repo where your RFCs / decisions / c4s live (used by the
`create-design-doc` skill and friends).

```bash
# One-time setup: fork the docs template and point task-summoner at it.
gh repo create my-docs --template teachmewow/task-summoner-docs-template --clone
task-summoner config set docs_repo "$(pwd)/my-docs"

# Inspect
task-summoner config list
task-summoner config get docs_repo     # exits 0 if set, 1 if unset

# Remove
task-summoner config unset docs_repo
```

Set values can be overridden per-invocation via an environment variable —
useful in CI or one-off runs:

| Key         | Env var                      |
|-------------|------------------------------|
| `docs_repo` | `TASK_SUMMONER_DOCS_REPO`    |

Resolution precedence is `env > file > unset`. `config get` reports the source
it resolved from.

The `docs_repo` value is validated on `set`: it must be an absolute path, an
existing git repo, and contain `.task-summoner/config.yml` (created by the
[task-summoner-docs-template](https://github.com/teachmewow/task-summoner-docs-template)
fork — see ENG-93).

## Observability

Task Summoner ships with opt-in [LangSmith](https://smith.langchain.com/)
tracing so you can inspect the full prompt, response, and FSM path of every
agent dispatch. Tracing is **off by default** — the `@traceable` decorator is a
no-op until you set two environment variables.

### Enable tracing

```bash
export LANGCHAIN_TRACING_V2=true
export LANGCHAIN_API_KEY=<your langsmith api key>
export LANGCHAIN_PROJECT=task-summoner   # optional; defaults to "default"
```

Then run `task-summoner run` as usual. Traces appear under your project at:

```
https://smith.langchain.com/o/<your-org-slug>/projects/p/task-summoner
```

### What's traced

| Run type | Name | Where |
|----------|------|-------|
| `chain`  | `state.<phase>` | Each FSM state handler (`planning`, `implementing`, `checking_doc`, `creating_doc`, `improving_doc`, `fixing_mr`) |
| `prompt` | `prompt.<phase>` | The `build_prompt` helper for each state (system prompt + skill + ticket context) |
| `llm`    | `claude_code.dispatch` | `ClaudeCodeAdapter.run` — the top-level agent invocation |
| `chain`  | `claude_code.stream` | Nested: streamed tool-use / text deltas from the Claude SDK |

Every state trace is tagged with `issue_id`, `skill`, `repo`, `phase`, and
`retry_count` so you can slice runs by ticket, target repo, or phase in the
LangSmith UI.

### Off-by-default guarantees

- If `LANGCHAIN_TRACING_V2` or `LANGCHAIN_API_KEY` is unset, the decorator
  short-circuits before touching the `langsmith` SDK — zero behavior change,
  zero overhead.
- If `langsmith` is not installed, the decorator is still a safe no-op.
- Exceptions in traced functions are never swallowed; they propagate with the
  trace closed in error state.

### Follow-ups (out of scope for ENG-107)

- Sampling / rate limiting / cost controls for high-volume runs.
- Dashboards and alerts in LangSmith.
- Tracing the OpenAI / Anthropic providers directly (today we trace the
  subprocess dispatch, not the underlying API calls).

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
