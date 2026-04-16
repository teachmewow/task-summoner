# Board Dispatcher

Autonomous SDLC orchestrator — polls Jira for tickets labeled `claudio`, spawns Claude agents to plan and implement, delivers merge requests with human approval at every gate.

## Quick start

```bash
source venv/bin/activate
board-dispatcher run          # orchestrator + dashboard on :8420
board-dispatcher status       # show tracked tickets
pytest                        # run test suite
```

## Architecture

### State machine (deterministic, no LLM in the loop)

The core is a pure-data FSM in `core/state_machine.py`. Transitions are `(state, trigger) → next_state`. The LLM never decides flow — state handlers return trigger strings, the FSM resolves the next state.

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
├── ImplementingState    — agent writes code + opens MR
├── FixingMrState        — agent addresses MR review feedback
├── DoneState            — transitions Jira to Done
├── FailedState          — terminal error
└── BaseApprovalState (ABC)
    ├── WaitingDocReviewState
    ├── WaitingPlanReviewState
    └── WaitingMrReviewState
```

Handler contract: `async def handle(ctx, ticket, services) → str` where the return value is the trigger.

### Approval gate pattern

`BaseApprovalState` handles the lgtm/retry loop. It uses `MessageTag` (`[bd:TICKET:state:id]`) embedded in Jira comments to robustly identify which comment to poll. If the tag is lost from metadata, it recovers by scanning comments with regex. On retry, it posts an "On it..." ack with a new tag to prevent infinite retry loops.

### Plugin loading

`PluginResolver` in `agents/plugin_resolver.py` implements a strategy pattern:
- `INSTALLED` mode: plugin comes from user's Claude Code setup via `setting_sources=["user"]`
- `LOCAL` mode: plugin injected explicitly from `plugin_path`

Config field `plugin_mode` controls the strategy. `build_plugin_resolver()` on config creates the resolver.

### Dependency flow

```
Orchestrator
├── JiraSyncService (discovery)
├── TaskDispatcher (scheduling)
│   └── State handlers (via registry)
├── AgentRunner
│   └── AgentOptionsFactory
│       └── PluginResolver
├── StateStore (atomic JSON persistence)
├── JiraClient (async acli wrapper)
├── GitWorkspaceManager (worktrees)
└── EventBus (pub/sub → SSE → Dashboard)
```

`StateServices` is the DI container passed to all handlers (jira, workspace, agent_runner, store).

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

### Jira comment tracking

Always use `MessageTag` when posting agent output to Jira. The tag format `[bd:KEY:state:shortid]` enables:
- Approval polling (find the right comment to check for replies)
- State recovery (scan comments if metadata is lost)
- Distinguishing bot comments from human comments

### ADF (Atlassian Document Format)

Use the `Adf` factory in `tracker/adf.py` for rich Jira comments. Use `markdown_to_adf()` in `tracker/adf_converter.py` to convert agent markdown output to ADF.

## Testing

```bash
pytest                      # all tests
pytest -x                   # stop on first failure
pytest --cov                # with coverage (fail_under=89)
pytest tests/test_states.py # specific file
```

Tests use `conftest.py` fixtures: `config`, `store`, `sample_ticket`, `sample_context`, `mock_services`. State handler tests mock `StateServices` with `AsyncMock`.

## Key files

- `config.yaml` — local config (gitignored, copy from `config.yaml.example`)
- `.env` — secrets (gitignored, copy from `.env.example`)
- `artifacts/{TICKET}/state.json` — persisted state per ticket
- `core/state_machine.py` — the FSM transitions (read this first)
- `states/base.py` — BaseState + BaseApprovalState + StateServices
- `runtime/orchestrator.py` — main polling loop
- `runtime/dispatcher.py` — task scheduling + trigger application
