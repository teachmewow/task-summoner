"""Config-related request/response schemas.

`ConfigPayload` — shape that both CLI wizard and web form produce.
`ConfigStatus` — startup state: is the app configured and polling?
`ConfigTestResponse` / `ConfigSaveResponse` — outcomes of test/save flows.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ConfigPayload(BaseModel):
    """Config submitted from the setup form (web or CLI)."""

    board_type: str
    board_config: dict[str, Any]
    agent_type: str
    agent_config: dict[str, Any]
    repos: dict[str, str] = {}
    default_repo: str = ""
    polling_interval_sec: int = 10
    workspace_root: str = "/tmp/task-summoner-workspaces"


class ConfigStatus(BaseModel):
    """Whether the running server has a valid config + orchestrator active."""

    configured: bool
    errors: list[str] = []


class ConfigTestResponse(BaseModel):
    ok: bool
    message: str


class ConfigSaveResponse(BaseModel):
    ok: bool
    path: str
