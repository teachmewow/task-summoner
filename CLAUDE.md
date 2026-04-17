# Task Summoner

Local-first agentic board management — provider-agnostic, human-in-the-loop SDLC orchestrator.

## Repo layout

```
task-summoner/
├── backend/   # Python orchestrator + FastAPI (pytest, ruff)
│   └── src/task_summoner/
├── frontend/  # React 19 + TS + Vite + TanStack Router (pnpm, biome, vitest)
└── .venv/     # shared Python venv
```

Frontend builds to `backend/src/task_summoner/web_dist/`, which FastAPI serves from `/` with SPA fallback. Dev mode spawns vite alongside uvicorn.

## Quick start

```bash
source .venv/bin/activate
task-summoner run            # prod: serves pre-built web_dist/ on :8420
task-summoner run --dev      # dev: uvicorn + vite hot reload (open :5173)
task-summoner status         # show tracked tickets
cd backend && pytest         # backend tests
cd frontend && pnpm test     # frontend tests
```

## Architecture

### State machine (deterministic, no LLM in the loop)

The core is a pure-data FSM in `core/state_machine.py`. Transitions are `(state, trigger) -> next_state`. The LLM never decides flow — state handlers return trigger strings, the FSM resolves the next state.

Terminal states: `DONE`, `FAILED`. Special triggers: `_wait` (keep polling), `_noop` (terminal), `_retry` (increment counter, stay).

### State handler pattern

Every lifecycle state has a handler in `states/`. All extend `BaseState`:

```
BaseState (ABC)
├── QueuedState          — creates worktree, claims ticket
├── CheckingDocState     — agent checks if design doc needed
├── CreatingDocState     — agent creates design doc
├── ImprovingDocState    — agent improves doc from feedback
├── PlanningState        — agent creates implementation plan
├── ImplementingState    — agent writes code + opens PR
├── FixingMrState        — agent addresses PR review feedback
├── DoneState            — transitions ticket to Done
├── FailedState          — terminal error
└── BaseApprovalState (ABC)
    ├── WaitingDocReviewState
    ├── WaitingPlanReviewState
    └── WaitingMrReviewState
```

Handler contract: `async def handle(ctx, ticket, services) -> str` where the return value is the trigger.

### Approval gate pattern

`BaseApprovalState` handles the lgtm/retry loop. It uses `MessageTag` (`[ts:TICKET:state:id]`) embedded in comments to robustly identify which comment to poll. If the tag is lost from metadata, it recovers by scanning comments with regex. On retry, it posts an "On it..." ack with a new tag to prevent infinite retry loops.

### Plugin loading

`PluginResolver` in `agents/plugin_resolver.py` implements a strategy pattern:
- `INSTALLED` mode: plugin comes from user's Claude Code setup via `setting_sources=["user"]`
- `LOCAL` mode: plugin injected explicitly from `plugin_path`

Config field `plugin_mode` controls the strategy. `build_plugin_resolver()` on config creates the resolver.

### Provider abstraction (in progress)

Three abstraction layers being built:
- `BoardProvider` protocol — Jira, Linear (see `providers/board/`)
- `AgentProvider` protocol — Claude Code, Codex (see `providers/agent/`)
- Core uses only protocols, never concrete providers

### Dependency flow

```
Orchestrator
├── BoardSyncService (discovery)
├── TaskDispatcher (scheduling)
│   └── State handlers (via registry)
│       └── AgentProvider.run() (Claude Code / Codex via factory)
├── StateStore (atomic JSON persistence)
├── BoardProvider (async board operations)
├── GitWorkspaceManager (worktrees)
└── EventBus (pub/sub -> SSE -> Dashboard)
```

Claude Code specifics — `ClaudeAgentOptions` building, env forwarding, plugin
resolution — all live inside `providers/agent/claude_code/adapter.py` and its
`PluginResolver`. No separate `AgentRunner` / `AgentOptionsFactory` layer.

`StateServices` is the DI container passed to all handlers.

## Conventions

### Adding a new state

1. Add the state to `TicketState` enum in `models/enums.py`
2. Add transitions in `core/state_machine.py` TRANSITIONS dict
3. Create handler class in `states/` extending `BaseState` or `BaseApprovalState`
4. Register it in `states/__init__.py` `build_state_registry()`
5. Write tests in `tests/test_states.py`

### Agent profiles

Three profiles in config, used by state handlers via `self.agent_config`:
- `doc_checker` — lightweight triage (haiku/sonnet, low budget)
- `standard` — planning, doc creation, reviews (sonnet, medium budget)
- `heavy` — implementation (opus, high budget)

### Comment tracking

Always use `MessageTag` when posting agent output to the board. The tag format `[ts:KEY:state:shortid]` enables:
- Approval polling (find the right comment to check for replies)
- State recovery (scan comments if metadata is lost)
- Distinguishing bot comments from human comments

### ADF (Atlassian Document Format)

Used by the Jira adapter. `Adf` factory in `tracker/adf.py` for rich comments. `markdown_to_adf()` in `tracker/adf_converter.py` to convert agent markdown output to ADF. Linear adapter uses Markdown natively.

## Testing

```bash
cd backend
pytest                      # all tests
pytest -x                   # stop on first failure
pytest tests/test_states.py # specific file

cd ../frontend
pnpm test                   # vitest
pnpm build                  # tsc --noEmit + vite build
pnpm lint                   # biome
```

Backend tests use `conftest.py` fixtures: `config`, `store`, `sample_ticket`, `sample_context`, `mock_services`. State handler tests mock `StateServices` with `AsyncMock`.

## Key files

- `config.yaml` — local config, repo root (gitignored, copy from `backend/config.yaml.example`)
- `.env` — secrets, repo root (gitignored, copy from `backend/.env.example`)
- `artifacts/{TICKET}/state.json` — persisted state per ticket
- `backend/src/task_summoner/core/state_machine.py` — the FSM transitions (read this first)
- `backend/src/task_summoner/states/base.py` — BaseState + BaseApprovalState + StateServices
- `backend/src/task_summoner/runtime/orchestrator.py` — main polling loop
- `backend/src/task_summoner/api/app.py` — FastAPI composition + SPA fallback
- `frontend/src/routes/` — TanStack Router file-based routes
- `frontend/vite.config.ts` — dev proxy + build output path (→ `backend/.../web_dist/`)
