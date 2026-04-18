"""Board Health schemas — operational view over providers + local state."""

from __future__ import annotations

from pydantic import BaseModel


class BoardHealth(BaseModel):
    provider: str
    configured: bool
    watch_label: str = ""
    identifier: str = ""  # linear team_id or jira email
    last_ok_at: str | None = None
    last_error: str | None = None


class AgentHealth(BaseModel):
    provider: str
    session_available: bool
    plugin_mode: str = ""
    plugin_path: str = ""
    plugin_resolved: bool = False
    plugin_reason: str | None = None


class LocalStateHealth(BaseModel):
    total_tickets: int
    active_tickets: int
    terminal_tickets: int
    workspace_root: str
    workspace_bytes: int
    artifacts_dir: str
    artifacts_bytes: int


class HealthResponse(BaseModel):
    board: BoardHealth
    agent: AgentHealth
    local: LocalStateHealth


class TestBoardResponse(BaseModel):
    ok: bool
    message: str
    sample_count: int = 0


class CleanResponse(BaseModel):
    ok: bool
    scanned: int
    removed: list[str]
    message: str


__all__ = [
    "AgentHealth",
    "BoardHealth",
    "CleanResponse",
    "HealthResponse",
    "LocalStateHealth",
    "TestBoardResponse",
]
