# Board Dispatcher

**From Jira ticket to Merge Request — without touching the terminal.**

Board Dispatcher is an autonomous SDLC orchestrator that polls Jira for tickets, spawns Claude agents to plan and implement solutions, and delivers merge requests — with the developer approving at every step.

## How it works

1. Developer labels a Jira ticket `claudio`
2. System autonomously:
   - Checks if architecture documentation is needed
   - Creates an implementation plan
   - Writes code and opens a Merge Request
3. Developer reviews each step via Jira comments — from anywhere

The developer is the thinker. The system executes.

## Architecture

```
Label 'claudio' ──→ [ARCHITECTURE] ──lgtm──→ [PLAN] ──lgtm──→ [CODE] ──lgtm──→ Done
                     Needs doc?               Create plan      Write code + MR
                     Write / Skip             Revise plan      Fix feedback
                     Developer reviews        Developer reviews Developer reviews
```

Each phase has an approval gate where the developer can approve (`lgtm`) or request changes (`retry`). The system handles everything in between.

See [docs/lifecycle-flow.md](docs/lifecycle-flow.md) for the full state machine diagram.

## Prerequisites

| Dependency | Version | Purpose |
|------------|---------|---------|
| Python | >= 3.11 | Runtime |
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | >= 2.x | Agent SDK (`claude-agent-sdk`) |
| [acli](https://developer.atlassian.com/cloud/acli/guides/install-acli/) | >= 1.3 | Jira/Confluence CLI |
| git | any | Worktree management |
| [task-summoner plugins](https://github.com/teachmewow/task-summoner) | latest | Claude Code skills — installed in Claude Code, or cloned locally (see `plugin_mode`) |

You also need:
- An [Anthropic API key](https://console.anthropic.com/)
- Atlassian API token (for Jira + Confluence access)
- At least one git repo cloned locally (the repo your tickets target)

## Setup

### 1. Clone and install

```bash
git clone https://github.com/teachmewow/task-summoner.git
cd task-summoner
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

### 2. Environment variables

```bash
cp .env.example .env
```

Edit `.env` and fill in your credentials:

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-...        # Your Anthropic API key
ATLASSIAN_EMAIL=you@company.com     # Your Atlassian account email
ATLASSIAN_TOKEN=ATATT3x...          # Atlassian API token (https://id.atlassian.com/manage-profile/security/api-tokens)

# Optional
SLACK_BOT_TOKEN=xoxb-...            # Slack bot token for notifications
SLACK_USER_ID=U0...                 # Your Slack user ID
```

### 3. Configuration

```bash
cp config.yaml.example config.yaml
```

Edit `config.yaml` — the key things to configure:

**repos** — Map repo names to local paths. These are the repositories your Jira tickets target. The dispatcher creates git worktrees here.

```yaml
repos:
  my-service: "~/Projects/my-service"
```

**default_repo** — Used when a ticket has no `repo:<name>` label.

**plugin_mode** — How the aiops-workflows plugin is loaded. Two options:

- `"installed"` (default) — you already have the plugin installed in your Claude Code setup. No extra config needed.
- `"local"` — load from a directory path. Set `plugin_path` as well:

```yaml
plugin_mode: "local"
plugin_path: "~/Projects/aiops-claude-code/plugins/aiops-workflows"
```

If you don't have the plugin installed, clone it first:
```bash
git clone https://github.com/teachmewow/task-summoner.git ~/Projects/task-summoner
```

### 4. Verify acli

Make sure `acli` is in your PATH and authenticated:

```bash
acli --version
acli jira issue view SOME-TICKET   # test that it works
```

If not installed, follow the [acli installation guide](https://developer.atlassian.com/cloud/acli/guides/install-acli/).

### 5. Validate configuration

```bash
board-dispatcher status
```

If config is valid, it will show "No tracked tickets." Any configuration errors will be printed.

## Running

### Start the orchestrator + dashboard

```bash
board-dispatcher run
```

This starts:
- **Orchestrator** — polls Jira every 10 seconds for tickets with the `claudio` label
- **Dashboard** — real-time web UI at [http://localhost:8420](http://localhost:8420)

Options:
```bash
board-dispatcher run --port 9000        # Custom dashboard port
board-dispatcher run --no-ui            # Disable the web dashboard
board-dispatcher run -c my-config.yaml  # Custom config file
```

### Check ticket status

```bash
board-dispatcher status
```

## Usage

1. Create a Jira ticket with clear acceptance criteria
2. Add the label `claudio` to the ticket
3. (Optional) Add a `repo:<name>` label if not using the default repo
4. Watch the dashboard at http://localhost:8420
5. Review and approve each step via Jira comments:
   - Reply `lgtm` to approve and proceed to the next phase
   - Reply `retry` (or describe changes) to request improvements

## Dashboard

The web dashboard shows real-time progress of all tracked tickets:

- **Ticket list** — state, cost, retry count per ticket
- **Event log** — agent messages, tool calls, state transitions (filterable)
- **Live updates** — events stream in real-time via SSE

## Project structure

```
board-dispatcher/
  src/board_dispatcher/
    __main__.py          # Entry point
    cli.py               # CLI commands (run, status)
    config.py            # YAML + .env config loader
    constants.py         # Shared constants
    agents/              # Claude Agent SDK wrapper
      runner.py          # AgentRunner — runs agents, streams events
      options.py         # AgentOptionsFactory — builds agent config
      plugin_resolver.py # PluginResolver — installed vs local plugin strategy
    api/                 # FastAPI web dashboard
      app.py             # Endpoints + SSE stream
    core/                # State machine + persistence
      state_machine.py   # Deterministic FSM transitions
      state_store.py     # Atomic JSON state persistence
    dashboard_ui/        # Web UI (HTML/CSS/JS)
    events/              # Async event system
      bus.py             # EventBus (pub/sub)
      models.py          # Event types
    models/              # Domain models
      enums.py           # TicketState enum
      ticket.py          # Jira ticket model
      context.py         # Per-ticket persisted state
      agent.py           # Agent result model
    runtime/             # Orchestrator + dispatcher
      orchestrator.py    # Main polling loop
      dispatcher.py      # Task scheduling + state transitions
      sync.py            # Jira <-> local state sync
    states/              # State handlers (one per lifecycle state)
    tracker/             # Jira integration
      jira_client.py     # Async acli wrapper
      message_tracker.py # Comment tagging for approval polling
      reactions.py       # Approval keyword detection
      adf.py             # Atlassian Document Format models
      adf_converter.py   # Markdown -> ADF converter
    workspace/           # Git worktree management
      manager.py         # Create/remove worktrees per ticket
  tests/                 # Test suite
  config.yaml.example    # Configuration template
  .env.example           # Environment variables template
  docs/                  # Architecture diagrams
```

## Tests

```bash
pytest
pytest --cov                # With coverage
pytest tests/test_config.py # Single test file
```

## License

MIT License — TeachMeWoW
