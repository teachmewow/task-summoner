"""Web-based setup endpoints — alternative to the CLI wizard.

Serves the static setup page from dashboard_ui/static/ and exposes two APIs:
`POST /api/config/test` (validation only) and `POST /api/config` (writes config.yaml).
Both share the wizard's renderer so the CLI and web outputs stay in lockstep.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

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
from task_summoner.setup_wizard import _render_config_yaml

_STATIC_DIR = (
    Path(__file__).resolve().parent.parent / "dashboard_ui" / "static"
)
_SETUP_HTML = _STATIC_DIR / "setup.html"


class ConfigPayload(BaseModel):
    """Incoming config from the web setup form."""

    board_type: str
    board_config: dict[str, Any]
    agent_type: str
    agent_config: dict[str, Any]
    repos: dict[str, str] = {}
    default_repo: str = ""
    polling_interval_sec: int = 10
    workspace_root: str = "/tmp/task-summoner-workspaces"


def create_setup_router(config_path: Path) -> APIRouter:
    """Return a FastAPI router serving the setup page + save/test endpoints."""
    router = APIRouter()

    @router.get("/setup", response_class=HTMLResponse)
    async def setup_page() -> str:
        return _SETUP_HTML.read_text()

    @router.post("/api/config/test")
    async def test_config(payload: ConfigPayload) -> dict[str, Any]:
        try:
            _build_provider_config(payload)
            return {"ok": True, "message": "Config shape is valid."}
        except Exception as e:
            return {"ok": False, "message": str(e)}

    @router.post("/api/config")
    async def save_config(payload: ConfigPayload) -> dict[str, Any]:
        try:
            provider_config = _build_provider_config(payload)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

        yaml_text = _render_config_yaml(
            board_type=provider_config.board,
            board_config=provider_config.board_config,
            agent_type=provider_config.agent,
            agent_config=provider_config.agent_config,
            repos=payload.repos,
            default_repo=payload.default_repo,
            polling_interval_sec=payload.polling_interval_sec,
            workspace_root=payload.workspace_root,
        )
        config_path.write_text(yaml_text)
        return {"ok": True, "path": str(config_path.resolve())}

    return router


def _build_provider_config(payload: ConfigPayload) -> ProviderConfig:
    board_type = BoardProviderType(payload.board_type)
    agent_type = AgentProviderType(payload.agent_type)

    if board_type == BoardProviderType.JIRA:
        board_config: JiraConfig | LinearConfig = JiraConfig(**payload.board_config)
    else:
        board_config = LinearConfig(**payload.board_config)

    if agent_type == AgentProviderType.CLAUDE_CODE:
        agent_config: ClaudeCodeConfig | CodexConfig = ClaudeCodeConfig(
            **payload.agent_config
        )
    else:
        agent_config = CodexConfig(**payload.agent_config)

    provider_config = ProviderConfig(
        board=board_type,
        board_config=board_config,
        agent=agent_type,
        agent_config=agent_config,
    )
    BoardProviderFactory.create(provider_config)  # shape validation
    return provider_config
