"""Gate-inference API schemas (ENG-95)."""

from __future__ import annotations

from pydantic import BaseModel


class PrInfo(BaseModel):
    url: str
    number: int
    state: str  # OPEN / MERGED / CLOSED
    is_draft: bool
    head_branch: str


class GateResponse(BaseModel):
    """Current gate state for an issue + the PR the UI buttons act on."""

    issue_key: str
    state: str  # GateState enum value
    active_pr: PrInfo | None
    retry_skill: str | None
    reason: str = ""
    related_prs: list[PrInfo] = []
    # Echo of Linear state so the UI can show "Linear: In Progress" without
    # a second fetch.
    linear_status_type: str
    linear_status_name: str


class GateApprovePayload(BaseModel):
    """Payload for ``POST /api/gates/{key}/approve``."""

    pr_url: str


class GateRequestChangesPayload(BaseModel):
    """Payload for ``POST /api/gates/{key}/request-changes``."""

    pr_url: str
    feedback: str
    # When true (the default), the backend also re-summons the relevant skill
    # so the agent picks up the feedback. UI can set this false for silent
    # change-requests.
    resummon_skill: bool = True


class GateActionResponse(BaseModel):
    ok: bool
    message: str
    gh_output: str = ""
    resummoned_skill: str | None = None


__all__ = [
    "GateActionResponse",
    "GateApprovePayload",
    "GateRequestChangesPayload",
    "GateResponse",
    "PrInfo",
]
