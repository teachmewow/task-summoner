"""Interactive setup wizard — produces a valid config.yaml from user prompts.

Runs automatically on first boot if no config.yaml is found, or can be invoked
directly via `task-summoner setup`. Uses `rich` for a clean terminal UI.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt

from task_summoner.providers.board import BoardProviderFactory
from task_summoner.providers.config import (
    AgentProviderType,
    BoardProviderType,
    ClaudeCodeConfig,
    CodexConfig,
    JiraConfig,
    LinearConfig,
    ProviderConfig,
)

_DEFAULT_CONFIG_PATH = Path("config.yaml")

_WELCOME = """
[bold cyan]Task Summoner[/] — Setup Wizard

This wizard will help you configure your local setup. You'll choose a board
provider (Jira or Linear) and an agent CLI (Claude Code or Codex), then add
the repos you want to work on.

Your config is written to [bold]config.yaml[/] and can be edited later.
"""


def run_wizard(config_path: Path = _DEFAULT_CONFIG_PATH) -> Path:
    """Run the interactive wizard and write the resulting config file."""
    console = Console()
    console.print(Panel.fit(_WELCOME, border_style="cyan"))

    if config_path.exists():
        overwrite = Confirm.ask(
            f"[yellow]{config_path} already exists.[/] Overwrite?",
            default=False,
        )
        if not overwrite:
            console.print("[yellow]Setup cancelled.[/]")
            return config_path

    board_type = _prompt_board_type(console)
    board_config = _prompt_board_credentials(console, board_type)

    agent_type = _prompt_agent_type(console)
    agent_config = _prompt_agent_credentials(console, agent_type)

    provider_config = ProviderConfig(
        board=board_type,
        board_config=board_config,
        agent=agent_type,
        agent_config=agent_config,
    )

    _test_board_connection(console, provider_config)

    repos = _prompt_repos(console)
    default_repo = _prompt_default_repo(console, repos)

    polling_sec = IntPrompt.ask("[cyan]Poll interval (seconds)[/]", default=10)
    workspace_root = Prompt.ask(
        "[cyan]Workspace root[/]",
        default="/tmp/task-summoner-workspaces",
    )

    yaml_text = _render_config_yaml(
        board_type=board_type,
        board_config=board_config,
        agent_type=agent_type,
        agent_config=agent_config,
        repos=repos,
        default_repo=default_repo,
        polling_interval_sec=polling_sec,
        workspace_root=workspace_root,
    )

    config_path.write_text(yaml_text)
    console.print()
    console.print(
        Panel.fit(
            f"[bold green]Setup complete![/]\n\n"
            f"Config written to [bold]{config_path.resolve()}[/]\n\n"
            f"Next: [bold cyan]task-summoner run[/] to start the orchestrator.",
            border_style="green",
        )
    )
    return config_path


def _prompt_board_type(console: Console) -> BoardProviderType:
    console.print("\n[bold]Board provider[/]")
    choice = Prompt.ask("[cyan]Which board?[/]", choices=["linear", "jira"], default="linear")
    return BoardProviderType(choice)


def _prompt_board_credentials(
    console: Console, board_type: BoardProviderType
) -> JiraConfig | LinearConfig:
    if board_type == BoardProviderType.JIRA:
        console.print("\n[bold]Jira credentials[/]")
        email = Prompt.ask(
            "[cyan]Email[/] (or ${ENV_VAR})",
            default=os.environ.get("ATLASSIAN_EMAIL", "${ATLASSIAN_EMAIL}"),
        )
        token = Prompt.ask(
            "[cyan]API token[/] (or ${ENV_VAR})",
            default="${ATLASSIAN_TOKEN}",
            password=False,
        )
        watch_label = Prompt.ask("[cyan]Watch label[/]", default="task-summoner")
        return JiraConfig(email=email, token=token, watch_label=watch_label)

    console.print("\n[bold]Linear credentials[/]")
    api_key = Prompt.ask("[cyan]API key[/] (or ${ENV_VAR})", default="${LINEAR_API_KEY}")
    team_id = Prompt.ask("[cyan]Team ID (UUID)[/]")
    watch_label = Prompt.ask("[cyan]Watch label[/]", default="task-summoner")
    return LinearConfig(api_key=api_key, team_id=team_id, watch_label=watch_label)


def _prompt_agent_type(console: Console) -> AgentProviderType:
    console.print("\n[bold]Agent CLI[/]")
    choice = Prompt.ask(
        "[cyan]Which agent?[/]",
        choices=["claude_code", "codex"],
        default="claude_code",
    )
    return AgentProviderType(choice)


def _prompt_agent_credentials(
    console: Console, agent_type: AgentProviderType
) -> ClaudeCodeConfig | CodexConfig:
    if agent_type == AgentProviderType.CLAUDE_CODE:
        return _prompt_claude_code_credentials(console)

    console.print("\n[bold]Codex credentials[/]")
    api_key = Prompt.ask(
        "[cyan]OpenAI API key[/] (or ${ENV_VAR})",
        default="${OPENAI_API_KEY}",
    )
    return CodexConfig(api_key=api_key)


def _prompt_claude_code_credentials(console: Console) -> ClaudeCodeConfig:
    from task_summoner.providers.agent.claude_code import claude_code_session_available

    console.print("\n[bold]Claude Code credentials[/]")

    session_available = claude_code_session_available()
    if session_available:
        console.print(
            "[green]✓ Detected a logged-in Claude Code session.[/] Using your existing billing."
        )
    else:
        console.print(
            "[yellow]⚠ No Claude Code session found at ~/.claude/.[/] "
            "Run `claude login` first if you want to use your personal session."
        )

    use_session = Confirm.ask(
        "[cyan]Use your Claude Code personal session for billing?[/]",
        default=session_available,
    )

    api_key: str | None = None
    auth_method = "personal_session" if use_session else "api_key"
    if not use_session:
        api_key = Prompt.ask(
            "[cyan]Anthropic API key[/] (or ${ENV_VAR})",
            default="${ANTHROPIC_API_KEY}",
        )

    plugin_mode = Prompt.ask(
        "[cyan]Plugin mode[/]",
        choices=["installed", "local"],
        default="installed",
    )
    plugin_path = ""
    if plugin_mode == "local":
        plugin_path = Prompt.ask("[cyan]Path to tmw-workflows plugin directory[/]")

    return ClaudeCodeConfig(
        auth_method=auth_method,
        api_key=api_key,
        plugin_mode=plugin_mode,
        plugin_path=plugin_path or None,
    )


def _test_board_connection(console: Console, provider_config: ProviderConfig) -> None:
    if not Confirm.ask("\n[cyan]Test board connection now?[/]", default=True):
        return
    try:
        board = BoardProviderFactory.create(provider_config)
        console.print(f"[green]✓ {provider_config.board.value} adapter instantiated.[/]")
        del board  # live API call is deferred — the factory + config shape are validated
    except Exception as e:
        console.print(f"[red]✗ Board setup failed:[/] {e}")


def _prompt_repos(console: Console) -> dict[str, str]:
    console.print("\n[bold]Repos to watch[/]")
    console.print("[dim]Enter repos one per line. Blank line to finish.[/]")
    repos: dict[str, str] = {}
    while True:
        name = Prompt.ask("[cyan]Repo name[/] (blank to finish)", default="")
        if not name:
            break
        path = Prompt.ask(f"[cyan]Path for '{name}'[/]")
        expanded = str(Path(path).expanduser().resolve())
        if not Path(expanded).is_dir():
            console.print(
                f"[yellow]⚠ Path does not exist: {expanded}[/] "
                "(adding anyway — create it before `task-summoner run`)"
            )
        repos[name] = expanded

    if not repos:
        console.print("[yellow]⚠ No repos configured — you can add them to config.yaml later.[/]")
    return repos


def _prompt_default_repo(console: Console, repos: dict[str, str]) -> str:
    if not repos:
        return ""
    if len(repos) == 1:
        return next(iter(repos))
    return Prompt.ask(
        "[cyan]Default repo[/]",
        choices=list(repos.keys()),
        default=next(iter(repos)),
    )


def _render_config_yaml(
    *,
    board_type: BoardProviderType,
    board_config: JiraConfig | LinearConfig,
    agent_type: AgentProviderType,
    agent_config: ClaudeCodeConfig | CodexConfig,
    repos: dict[str, str],
    default_repo: str,
    polling_interval_sec: int,
    workspace_root: str,
) -> str:
    data: dict = {
        "providers": {
            "board": {
                "type": board_type.value,
                board_type.value: _board_config_dict(board_config),
            },
            "agent": {
                "type": agent_type.value,
                agent_type.value: _agent_config_dict(agent_config),
            },
        },
        "repos": repos or {},
        "polling_interval_sec": polling_interval_sec,
        "workspace_root": workspace_root,
        "artifacts_dir": "./artifacts",
        "approval_timeout_hours": 24,
        "agent_profiles": {
            "doc_checker": {"model": "haiku", "max_turns": 20, "max_budget_usd": 5},
            "standard": {"model": "sonnet", "max_turns": 200, "max_budget_usd": 50},
            "heavy": {"model": "opus", "max_turns": 500, "max_budget_usd": 50},
        },
        "retry": {"max_retries": 3, "base_delay_sec": 10, "max_backoff_sec": 300},
    }
    if default_repo:
        data["default_repo"] = default_repo

    return yaml.dump(data, sort_keys=False, default_flow_style=False)


def _board_config_dict(
    config: JiraConfig | LinearConfig,
) -> dict[str, str]:
    if isinstance(config, JiraConfig):
        return {
            "email": config.email,
            "token": config.token,
            "watch_label": config.watch_label,
        }
    return {
        "api_key": config.api_key,
        "team_id": config.team_id,
        "watch_label": config.watch_label,
    }


def _agent_config_dict(
    config: ClaudeCodeConfig | CodexConfig,
) -> dict[str, str]:
    if isinstance(config, ClaudeCodeConfig):
        result: dict[str, str] = {
            "auth_method": config.auth_method,
            "plugin_mode": config.plugin_mode,
        }
        if config.auth_method == "api_key" and config.api_key:
            result["api_key"] = config.api_key
        if config.plugin_path:
            result["plugin_path"] = config.plugin_path
        return result
    return {"api_key": config.api_key}
