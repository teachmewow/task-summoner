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
    state: str  # GateState enum value — inferred from PR + Linear signals
    active_pr: PrInfo | None
    retry_skill: str | None
    reason: str = ""
    related_prs: list[PrInfo] = []
    # Echo of Linear state so the UI can show "Linear: In Progress" without
    # a second fetch.
    linear_status_type: str
    linear_status_name: str
    # One-sentence human-readable rationale emitted by the pre-gate skill as
    # ``GATE_SUMMARY:<text>``. Populated from ``ctx.metadata["gate_summary"]``
    # — the state handler stashes it there right after posting the tagged
    # Linear comment. ``None`` when the context is not yet persisted or the
    # skill forgot to emit the contract line.
    summary: str | None = None
    # FSM state read directly from the orchestrator's TicketContext. This is
    # the authoritative "is this a gate?" signal — every ``WAITING_*_REVIEW``
    # is a gate, independent of whether PR inference found the underlying PR.
    # ``None`` before the first dispatch persists a context for the ticket.
    orchestrator_state: str | None = None
    # PR URL the orchestrator stashed in metadata for the current state
    # (``rfc_pr_url`` for doc, ``mr_url`` for code). ``None`` when the
    # state has no PR — plan gate is always ``None`` by design.
    orchestrator_pr_url: str | None = None
    # True when ``artifacts/<key>/plan.md`` exists on disk. Drives the
    # "Preview Plan" button on the UI.
    has_plan: bool = False


class GateApprovePayload(BaseModel):
    """Payload for ``POST /api/gates/{key}/approve``.

    ``pr_url`` is optional: plan gates have no backing PR (plan lives as a
    local artifact), so the UI omits the field. The endpoint enforces
    presence only for gates that actually need a merge.
    """

    pr_url: str | None = None


class GateRequestChangesPayload(BaseModel):
    """Payload for ``POST /api/gates/{key}/request-changes``.

    ``pr_url`` is optional: plan gates store feedback locally and re-run
    the ``ticket-plan`` skill with no GitHub review call. Code gates still
    require it (we post a ``gh pr review --request-changes``).
    """

    pr_url: str | None = None
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
