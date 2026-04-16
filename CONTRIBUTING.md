# Contributing to Task Summoner

Thanks for your interest in contributing! Task Summoner is a local-first, open-source agentic board orchestrator. Contributions of all sizes are welcome — bug fixes, new providers, docs, or UI improvements.

## Dev environment

Requirements:
- Python 3.11 or 3.12
- [uv](https://docs.astral.sh/uv/) (recommended) or plain `pip`
- `git`

Clone and install:

```bash
git clone https://github.com/teachmewow/task-summoner.git
cd task-summoner
uv venv .venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

Run the suite to confirm setup:

```bash
pytest
```

## Architecture overview

Task Summoner separates concerns into three abstraction layers:

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

Key directories:

| Path | What lives here |
|------|-----------------|
| `src/task_summoner/core/` | FSM + state store. Pure data structures, no I/O. |
| `src/task_summoner/states/` | Handlers for each lifecycle state. Call providers through protocols. |
| `src/task_summoner/runtime/` | Orchestrator, dispatcher, sync service. Owns the polling loop. |
| `src/task_summoner/providers/board/` | `BoardProvider` protocol + Jira/Linear adapters. |
| `src/task_summoner/providers/agent/` | `AgentProvider` protocol + Claude Code/Codex adapters. |
| `src/task_summoner/providers/config.py` | Pydantic config models for providers. |
| `src/task_summoner/models/` | Normalized domain models (Ticket, Comment, TicketContext). |

### Abstraction boundary

Files under `core/`, `states/`, `runtime/`, and `models/` **must not** import from concrete provider modules (`providers.board.jira`, `providers.board.linear`, `providers.agent.claude_code`, `providers.agent.codex`, or `claude_agent_sdk`). This is enforced by `tests/test_provider_isolation.py`. Use the protocol modules and `providers.config` instead.

## Adding a new board provider

1. Create `src/task_summoner/providers/board/<name>/adapter.py`. Implement every method on `BoardProvider` (see `protocol.py`).
2. Comment bodies you receive are **Markdown** — convert to the native format inside the adapter.
3. `post_tagged_comment` should return the tag itself (not the native comment ID) so approval tracking survives state recovery.
4. Add a typed config class in `providers/config.py` (e.g. `GitHubIssuesConfig`) and register a new `BoardProviderType` enum value.
5. Wire it up in `providers/board/factory.py`.
6. Add unit tests mirroring `tests/test_linear_adapter.py`.
7. Document the YAML block in `config.yaml.example` and extend the setup wizard (`setup_wizard.py`) to prompt for the new provider.

## Adding a new agent CLI provider

1. Create `src/task_summoner/providers/agent/<name>/adapter.py`. Implement `AgentProvider.run()`, `supports_streaming()`, and `supports_tool_use()`.
2. Map the incoming `AgentProfile` to whatever options the CLI expects.
3. Emit generic `AgentEvent`s through `event_callback` — never leak SDK-specific types upward.
4. Add a typed config class and enum value in `providers/config.py`; wire it into `providers/agent/factory.py`.
5. Mirror the test approach used by `tests/test_claude_code_adapter.py`.

## Code style

- Formatting: `ruff format` (enforced in CI)
- Linting: `ruff check` (enforced in CI)
- Line length: 100 chars
- Type hints on every public function
- Prefer `str | None` over `Optional[str]`
- Protocols (structural subtyping) over ABCs for the provider contracts

Before pushing:

```bash
ruff format src tests
ruff check src tests
pytest
```

## Commit conventions

Format: `{type}({ticket-id}): {Description starting with capital}`

Allowed types: `feat`, `fix`, `perf`, `chore`, `refactor`, `test`, `docs`.

Example: `feat(ENG-64): Add GitHub Issues board provider`

## Pull request process

1. Fork, branch off `main` (`git checkout -b {ticket-id}-{short-slug}`).
2. Make your change plus tests.
3. Run `ruff format`, `ruff check`, and `pytest` locally.
4. Open a PR against `main`. CI runs ruff + pytest on Python 3.11 and 3.12.
5. A maintainer reviews. Squash-merge is the default.

## Where to find things

- [Architecture & golden rules](CLAUDE.md)
- [Example config](config.yaml.example)
- [Issue tracker](https://github.com/teachmewow/task-summoner/issues)

Questions? Open an issue or discussion — we're happy to help.
