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

## Quick start

```bash
# Install
git clone https://github.com/teachmewow/task-summoner.git
cd task-summoner
uv venv .venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# Configure interactively
task-summoner setup

# Run
task-summoner run      # orchestrator + dashboard on :8420
task-summoner status   # show tracked tickets
```

No `config.yaml` yet? `task-summoner run` launches the setup wizard for you.

Prefer a web form? Once the dashboard is running, open [http://localhost:8420/setup](http://localhost:8420/setup).

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
      api_key: ${ANTHROPIC_API_KEY}
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

See [`config.yaml.example`](config.yaml.example) for the full annotated schema.

## Testing

```bash
pytest                 # all tests
pytest --cov           # with coverage
ruff check src tests   # lint
ruff format src tests  # format
```

CI runs ruff + pytest on Python 3.11 and 3.12 for every PR.

## Project

Part of the [TeachMeWoW](https://github.com/teachmewow) ecosystem. Licensed under [MIT](LICENSE). See [CONTRIBUTING.md](CONTRIBUTING.md) to get involved.
