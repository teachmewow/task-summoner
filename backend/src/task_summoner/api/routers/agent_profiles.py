"""Agent profile endpoints — read the 3 profiles and edit one at a time."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request

from task_summoner.api.deps import get_config_path
from task_summoner.api.schemas import (
    AgentProfileOut,
    AgentProfilePayload,
    AgentProfileSaveResponse,
    AgentProfilesResponse,
)
from task_summoner.config import AgentConfig, TaskSummonerConfig
from task_summoner.providers.config import AgentProviderType
from task_summoner.setup_wizard import _render_config_yaml
from task_summoner.utils import atomic_write

router = APIRouter(prefix="/api/agent-profiles", tags=["agent-profiles"])

_PROFILE_NAMES = ("doc_checker", "standard", "heavy")

_MODELS_BY_PROVIDER: dict[str, list[str]] = {
    "claude_code": ["haiku", "sonnet", "opus"],
    "codex": ["gpt-4o", "gpt-4o-mini", "o1", "o1-mini"],
}


def _profile_out(name: str, config: AgentConfig) -> AgentProfileOut:
    return AgentProfileOut(
        name=name,
        model=config.model,
        max_turns=config.max_turns,
        max_budget_usd=config.max_budget_usd,
        tools=list(config.tools),
        enabled=config.enabled,
    )


def _load_config(config_path: Path) -> TaskSummonerConfig:
    if not config_path.exists():
        raise HTTPException(
            status_code=409,
            detail="No config.yaml — run setup first.",
        )
    try:
        return TaskSummonerConfig.load(config_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load config: {e}") from e


@router.get("", response_model=AgentProfilesResponse)
async def list_profiles(
    config_path: Path = Depends(get_config_path),
) -> AgentProfilesResponse:
    config = _load_config(config_path)
    provider = config.providers.agent.value
    return AgentProfilesResponse(
        agent_provider=provider,
        available_models=_MODELS_BY_PROVIDER.get(provider, []),
        profiles=[
            _profile_out("doc_checker", config.doc_checker),
            _profile_out("standard", config.standard),
            _profile_out("heavy", config.heavy),
        ],
    )


@router.post("/{name}", response_model=AgentProfileSaveResponse)
async def save_profile(
    name: str,
    payload: AgentProfilePayload,
    request: Request,
    config_path: Path = Depends(get_config_path),
) -> AgentProfileSaveResponse:
    if name not in _PROFILE_NAMES:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown profile {name!r}. Known: {list(_PROFILE_NAMES)}",
        )

    config = _load_config(config_path)

    provider_key = config.providers.agent.value
    allowed = _MODELS_BY_PROVIDER.get(provider_key, [])
    if allowed and payload.model not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Model {payload.model!r} not supported by {provider_key}. "
            f"Pick one of: {allowed}",
        )

    updated = AgentConfig(
        enabled=payload.enabled,
        model=payload.model,
        max_turns=payload.max_turns,
        max_budget_usd=payload.max_budget_usd,
        tools=list(payload.tools),
    )
    setattr(config, name, updated)

    profiles_dict = {
        "doc_checker": _profile_to_yaml(config.doc_checker),
        "standard": _profile_to_yaml(config.standard),
        "heavy": _profile_to_yaml(config.heavy),
    }

    yaml_text = _render_config_yaml(
        board_type=config.providers.board,
        board_config=config.providers.board_config,
        agent_type=config.providers.agent,
        agent_config=config.providers.agent_config,
        repos=config.repos,
        default_repo=config.default_repo,
        polling_interval_sec=config.polling_interval_sec,
        workspace_root=config.workspace_root,
        agent_profiles=profiles_dict,
        monthly_budget_usd=config.monthly_budget_usd,
    )
    atomic_write(config_path, yaml_text)

    from task_summoner.api.app import reload_orchestrator

    await reload_orchestrator(request.app)

    return AgentProfileSaveResponse(ok=True, profile=_profile_out(name, updated))


def _profile_to_yaml(profile: AgentConfig) -> dict:
    return {
        "enabled": profile.enabled,
        "model": profile.model,
        "max_turns": profile.max_turns,
        "max_budget_usd": profile.max_budget_usd,
        "tools": list(profile.tools),
    }


# Consumed by tests / downstream tools that need the provider → models map.
AVAILABLE_MODELS = dict(_MODELS_BY_PROVIDER)

__all__ = ["AgentProviderType", "AVAILABLE_MODELS", "router"]
