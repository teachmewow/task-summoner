"""Setup form schemas — pre-save lookups + combined state prefill + save."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# Sentinel that the frontend echoes back for unchanged secrets. The backend
# treats this literal as "keep the current value" rather than overwriting the
# on-disk secret with the mask string.
MASKED_SECRET_SENTINEL = "********"


class LinearTeamsRequest(BaseModel):
    api_key: str


class LinearTeamSummary(BaseModel):
    id: str
    name: str
    key: str


class LinearTeamsResponse(BaseModel):
    ok: bool
    message: str = ""
    teams: list[LinearTeamSummary] = []


class SetupBoardSection(BaseModel):
    """Board section of the combined setup state.

    ``api_key_masked`` is True when a secret is persisted but intentionally
    omitted from the response. The frontend renders the mask glyph and lets
    the user opt in to replacing the value.
    """

    provider: Literal["linear", "jira", ""] = ""
    api_key_masked: bool = False
    api_key: str | None = None
    email: str | None = None
    team_id: str = ""
    team_name: str = ""
    watch_label: str = ""


class SetupAgentSection(BaseModel):
    provider: Literal["claude_code", "codex", ""] = ""
    auth_method: Literal["personal_session", "api_key", ""] = ""
    api_key_masked: bool = False
    api_key: str | None = None
    plugin_mode: Literal["installed", "local", ""] = ""
    plugin_path: str = ""


class SetupRepoEntry(BaseModel):
    name: str
    path: str


class SetupGeneralSection(BaseModel):
    default_repo: str = ""
    polling_interval_sec: int = 10
    workspace_root: str = ""
    docs_repo: str = ""


class SetupStateResponse(BaseModel):
    """Combined prefill payload — merges ``config.yaml`` and user config."""

    board: SetupBoardSection = Field(default_factory=SetupBoardSection)
    agent: SetupAgentSection = Field(default_factory=SetupAgentSection)
    repos: list[SetupRepoEntry] = Field(default_factory=list)
    general: SetupGeneralSection = Field(default_factory=SetupGeneralSection)


class SetupSavePayload(BaseModel):
    """Save request shape — mirrors ``SetupStateResponse`` with writable fields.

    ``api_key`` equal to :data:`MASKED_SECRET_SENTINEL` (``"********"``) tells
    the backend to preserve the currently persisted secret instead of
    overwriting with the mask literal.
    """

    board: dict[str, Any] = Field(default_factory=dict)
    agent: dict[str, Any] = Field(default_factory=dict)
    repos: list[SetupRepoEntry] = Field(default_factory=list)
    general: SetupGeneralSection = Field(default_factory=SetupGeneralSection)


class SetupSaveResponse(BaseModel):
    ok: bool
    config_path: str = ""
    docs_repo_saved: bool = False
    errors: list[str] = Field(default_factory=list)


__all__ = [
    "MASKED_SECRET_SENTINEL",
    "LinearTeamSummary",
    "LinearTeamsRequest",
    "LinearTeamsResponse",
    "SetupAgentSection",
    "SetupBoardSection",
    "SetupGeneralSection",
    "SetupRepoEntry",
    "SetupSavePayload",
    "SetupSaveResponse",
    "SetupStateResponse",
]
