"""Board Health — operational view over the configured providers + local state."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request

from task_summoner.api.deps import get_config_path, get_store
from task_summoner.api.schemas import (
    AgentHealth,
    BoardHealth,
    CleanResponse,
    HealthResponse,
    LocalStateHealth,
    TestBoardResponse,
)
from task_summoner.config import TaskSummonerConfig
from task_summoner.core import StateStore
from task_summoner.core.state_machine import TERMINAL_STATES
from task_summoner.providers.agent import claude_code as claude_code_module
from task_summoner.providers.board import BoardNotFoundError, BoardProviderFactory
from task_summoner.providers.config import (
    ClaudeCodeConfig,
    CodexConfig,
    JiraConfig,
    LinearConfig,
)

log = structlog.get_logger()

router = APIRouter(prefix="/api/health", tags=["health"])


def _load_config(config_path: Path) -> TaskSummonerConfig:
    if not config_path.exists():
        raise HTTPException(status_code=409, detail="No config.yaml — run setup first.")
    try:
        return TaskSummonerConfig.load(config_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load config: {e}") from e


def _dir_size_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for entry in path.rglob("*"):
        try:
            if entry.is_file(follow_symlinks=False):
                total += entry.stat().st_size
        except (OSError, ValueError):
            continue
    return total


def _board_health(config: TaskSummonerConfig, request: Request) -> BoardHealth:
    bc = config.providers.board_config
    if isinstance(bc, LinearConfig):
        provider, label, ident = "linear", bc.watch_label, bc.team_id
    elif isinstance(bc, JiraConfig):
        provider, label, ident = "jira", bc.watch_label, bc.email
    else:
        provider, label, ident = config.providers.board.value, "", ""
    last_ok = getattr(request.app.state, "board_last_ok_at", None)
    last_err = getattr(request.app.state, "board_last_error", None)
    return BoardHealth(
        provider=provider,
        configured=bool(ident),
        watch_label=label,
        identifier=ident,
        last_ok_at=last_ok,
        last_error=last_err,
    )


def _agent_health(config: TaskSummonerConfig) -> AgentHealth:
    ac = config.providers.agent_config
    if isinstance(ac, ClaudeCodeConfig):
        mode = ac.plugin_mode
        plugin_path = ac.plugin_path or ""
        resolved = True
        reason: str | None = None
        if mode == "local":
            if not plugin_path:
                resolved = False
                reason = "plugin_mode=local but no plugin_path set"
            elif not Path(plugin_path).expanduser().is_dir():
                resolved = False
                reason = f"Plugin path does not exist: {plugin_path}"
        return AgentHealth(
            provider="claude_code",
            session_available=claude_code_module.claude_code_session_available(),
            plugin_mode=mode,
            plugin_path=plugin_path,
            plugin_resolved=resolved,
            plugin_reason=reason,
        )
    if isinstance(ac, CodexConfig):
        return AgentHealth(
            provider="codex",
            session_available=False,
            plugin_reason="Codex provider is not fully implemented yet.",
        )
    return AgentHealth(provider=config.providers.agent.value, session_available=False)


def _local_state_health(config: TaskSummonerConfig, store: StateStore) -> LocalStateHealth:
    contexts = store.list_all()
    terminal = sum(1 for c in contexts if c.state in TERMINAL_STATES)
    active = len(contexts) - terminal
    ws_root = Path(config.workspace_root).expanduser()
    artifacts = Path(config.artifacts_dir).expanduser()
    return LocalStateHealth(
        total_tickets=len(contexts),
        active_tickets=active,
        terminal_tickets=terminal,
        workspace_root=str(ws_root),
        workspace_bytes=_dir_size_bytes(ws_root),
        artifacts_dir=str(artifacts),
        artifacts_bytes=_dir_size_bytes(artifacts),
    )


@router.get("", response_model=HealthResponse)
async def health(
    request: Request,
    store: StateStore = Depends(get_store),
    config_path: Path = Depends(get_config_path),
) -> HealthResponse:
    config = _load_config(config_path)
    return HealthResponse(
        board=_board_health(config, request),
        agent=_agent_health(config),
        local=_local_state_health(config, store),
    )


@router.post("/test-board", response_model=TestBoardResponse)
async def test_board(
    request: Request,
    config_path: Path = Depends(get_config_path),
) -> TestBoardResponse:
    config = _load_config(config_path)
    board = BoardProviderFactory.create(config.build_provider_config())
    try:
        tickets = await board.search_eligible()
        request.app.state.board_last_ok_at = datetime.now(UTC).isoformat()
        request.app.state.board_last_error = None
        return TestBoardResponse(
            ok=True,
            message=f"Found {len(tickets)} eligible ticket(s).",
            sample_count=len(tickets),
        )
    except Exception as e:
        request.app.state.board_last_error = str(e)
        log.warning("Board test failed", error=str(e))
        return TestBoardResponse(ok=False, message=str(e))


@router.post("/clean", response_model=CleanResponse)
async def clean(
    config_path: Path = Depends(get_config_path),
    store: StateStore = Depends(get_store),
) -> CleanResponse:
    config = _load_config(config_path)
    board = BoardProviderFactory.create(config.build_provider_config())
    contexts = store.list_all()
    removed: list[str] = []
    for ctx in contexts:
        try:
            await board.fetch_ticket(ctx.ticket_key)
        except BoardNotFoundError:
            store.delete(ctx.ticket_key)
            removed.append(ctx.ticket_key)
        except Exception as e:
            log.warning("Skipping ticket during clean", ticket=ctx.ticket_key, error=str(e))
    return CleanResponse(
        ok=True,
        scanned=len(contexts),
        removed=removed,
        message=(
            f"Removed {len(removed)} ticket(s)."
            if removed
            else "Nothing to clean — all local tickets are reachable on the board."
        ),
    )
