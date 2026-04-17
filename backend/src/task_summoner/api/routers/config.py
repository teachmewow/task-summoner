"""Config endpoints — status / test / save. The setup UI is a React route."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from task_summoner.api.deps import get_config_path, get_config_status
from task_summoner.api.schemas import (
    ConfigPayload,
    ConfigSaveResponse,
    ConfigStatus,
    ConfigTestResponse,
)
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
from task_summoner.utils import atomic_write

router = APIRouter(tags=["config"])


@router.get("/api/config/status", response_model=ConfigStatus)
async def config_status(
    status: ConfigStatus = Depends(get_config_status),
) -> ConfigStatus:
    return status


@router.post("/api/config/test", response_model=ConfigTestResponse)
async def test_config(payload: ConfigPayload) -> ConfigTestResponse:
    try:
        _build_provider_config(payload)
        return ConfigTestResponse(ok=True, message="Config shape is valid.")
    except Exception as e:
        return ConfigTestResponse(ok=False, message=str(e))


@router.post("/api/config", response_model=ConfigSaveResponse)
async def save_config(
    payload: ConfigPayload,
    config_path: Path = Depends(get_config_path),
) -> ConfigSaveResponse:
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
    atomic_write(config_path, yaml_text)
    return ConfigSaveResponse(ok=True, path=str(config_path.resolve()))


def _build_provider_config(payload: ConfigPayload) -> ProviderConfig:
    board_type = BoardProviderType(payload.board_type)
    agent_type = AgentProviderType(payload.agent_type)

    if board_type == BoardProviderType.JIRA:
        board_config: JiraConfig | LinearConfig = JiraConfig(**payload.board_config)
    else:
        board_config = LinearConfig(**payload.board_config)

    if agent_type == AgentProviderType.CLAUDE_CODE:
        agent_config: ClaudeCodeConfig | CodexConfig = ClaudeCodeConfig(**payload.agent_config)
    else:
        agent_config = CodexConfig(**payload.agent_config)

    provider_config = ProviderConfig(
        board=board_type,
        board_config=board_config,
        agent=agent_type,
        agent_config=agent_config,
    )
    BoardProviderFactory.create(provider_config)
    return provider_config
