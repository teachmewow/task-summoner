# Task Summoner

Local-first agentic board management. Connect it to your board (Jira or Linear), point it at a code agent (Claude Code or Codex), and it drives the full development lifecycle — from design doc to code review — with human approval at every gate.

## How it works

```
Label 'task-summoner' ──→ [DESIGN DOC] ──lgtm──→ [PLAN] ──lgtm──→ [CODE] ──lgtm──→ Done
                               │                   │                 │
                          Agent writes          Agent plans       Agent implements
                          design doc            approach          + opens PR
```

1. Developer labels a ticket `task-summoner`
2. Task Summoner picks it up, creates a worktree, and begins the lifecycle
3. At each gate (design doc, plan, PR), the developer reviews and approves via comment
4. On approval, the agent advances to the next state automatically

## Quick start

```bash
# Install
pip install -e ".[dev]"

# Configure (copy and edit)
cp config.yaml.example config.yaml

# Run
task-summoner run          # orchestrator + dashboard on :8420
task-summoner status       # show tracked tickets
```

## Architecture

### Provider-agnostic design

```
┌──────────────────────────────┐
│     task-summoner core       │
│  (FSM, states, orchestrator) │
└──────┬──────────┬────────────┘
       │          │
┌──────▼──────┐ ┌─▼────────────┐
│ BoardProvider│ │ AgentProvider │
│  (protocol)  │ │  (protocol)   │
└──────┬──────┘ └──┬────────────┘
  ┌────┴────┐   ┌──┴─────┐
  │Jira│Linear│ │Claude│Codex│
  └────┴─────┘ │ Code │    │
               └──────┴────┘
```

Three abstraction layers:
- **Board Provider**: Jira or Linear (more coming)
- **Agent CLI Provider**: Claude Code or Codex (more coming)
- **Core**: FSM, state handlers, orchestrator — knows nothing about specific providers

### Deterministic FSM

The core is a pure-data state machine. Transitions are `(state, trigger) -> next_state`. The LLM never decides flow — state handlers return trigger strings, the FSM resolves the next state.

### State handler pattern

```
BaseState (ABC)
├── QueuedState          — creates worktree, claims ticket
├── CheckingDocState     — agent checks if design doc needed
├── CreatingDocState     — agent creates design doc
├── ImprovingDocState    — agent improves doc from feedback
├── PlanningState        — agent creates implementation plan
├── ImplementingState    — agent writes code + opens PR
├── FixingMrState        — agent addresses review feedback
├── DoneState            — transitions ticket to Done
├── FailedState          — terminal error
└── BaseApprovalState (ABC)
    ├── WaitingDocReviewState
    ├── WaitingPlanReviewState
    └── WaitingMrReviewState
```

### Approval gates

Human-in-the-loop at every phase boundary. The developer replies `lgtm` to approve or `retry` to request changes. Comment tagging (`[ts:TICKET:state:id]`) enables robust polling and state recovery.

## Testing

```bash
pytest                      # all tests
pytest -x                   # stop on first failure
pytest --cov                # with coverage
```

## Project

Part of the [TeachMeWoW](https://github.com/teachmewow) ecosystem. Licensed under MIT.
