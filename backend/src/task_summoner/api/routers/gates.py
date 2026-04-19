"""Gate-inference + approval routers (ENG-95).

Three endpoints, all on ``/api/gates/{ticket_key}``:

- ``GET``                           current state + active PR + retry skill
- ``POST /approve``                 ``gh pr review --approve``
- ``POST /request-changes``         ``gh pr review --request-changes`` + re-summon

Inference is polled, not event-driven — the UI can call ``GET`` after each
action or on a short interval. Keeping it polled avoids a webhook receiver
and matches the Cluster 1 contract that "GitHub PR reviews ARE the gate".
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request

from task_summoner.api.deps import get_config_path
from task_summoner.api.schemas import (
    GateActionResponse,
    GateApprovePayload,
    GateRequestChangesPayload,
    GateResponse,
    PrInfo,
)
from task_summoner.config import TaskSummonerConfig
from task_summoner.gates import (
    GateSignals,
    GateState,
    LinearSignal,
    PrSignal,
    approve_pr,
    fetch_pr_signals,
    infer_gate_state,
    request_changes,
)
from task_summoner.providers.board import BoardNotFoundError, BoardProviderFactory
from task_summoner.user_config import get_docs_repo

log = structlog.get_logger()

router = APIRouter(prefix="/api/gates", tags=["gates"])


def _load_config(config_path: Path) -> TaskSummonerConfig:
    if not config_path.exists():
        raise HTTPException(status_code=409, detail="No config.yaml — run setup first.")
    try:
        return TaskSummonerConfig.load(config_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load config: {e}") from e


def _status_type_for(status_name: str) -> str:
    """Map a Linear ``state.name`` to its canonical ``statusType`` bucket.

    Linear workspaces customise names freely (``"In Review"`` vs ``"In PR"``)
    so we rely on keyword buckets. This matches the bucket names used in the
    inference rules — ``started``, ``unstarted``, ``completed``, ``canceled``.
    """
    name = (status_name or "").strip().lower()
    if not name:
        return "unstarted"
    if name in {"done", "completed", "closed", "released"}:
        return "completed"
    if name in {"canceled", "cancelled", "abandoned"}:
        return "canceled"
    if name in {"backlog", "todo", "to do", "open", "new"}:
        return "unstarted"
    # "In Progress", "In Review", "In Plan Review", "Doing" etc. all map to
    # the ``started`` bucket — the gate inference further disambiguates via
    # the PR signals.
    if any(kw in name for kw in ("progress", "review", "doing", "implement", "started", "wip")):
        return "started"
    return "unstarted"


def _pr_to_info(pr: PrSignal | None) -> PrInfo | None:
    if pr is None:
        return None
    return PrInfo(
        url=pr.url,
        number=pr.number,
        state=pr.state,
        is_draft=pr.is_draft,
        head_branch=pr.head_branch,
    )


async def _resolve_target_repo_slug(config: TaskSummonerConfig) -> str | None:
    """Best-effort ``owner/name`` for the default code repo.

    We can't always know it — users may work across multiple repos per issue.
    Returning ``None`` falls back to ``gh search prs`` which scans everything
    the authenticated user can see.
    """
    default_repo = config.default_repo
    if not default_repo:
        return None
    repo_path = (config.repos or {}).get(default_repo)
    if not repo_path:
        return None
    try:
        from task_summoner.gates import _resolve_origin_slug  # local helper reuse

        return await _resolve_origin_slug(repo_path)
    except Exception:
        return None


@router.get("/{ticket_key}", response_model=GateResponse)
async def get_gate(
    ticket_key: str,
    request: Request,
    config_path: Path = Depends(get_config_path),
) -> GateResponse:
    """Return the gate snapshot for ``ticket_key``.

    The ``summary`` field reads ``TicketContext.metadata['gate_summary']``,
    which the pre-gate state handlers stash immediately after posting the
    tagged Linear comment. Contract: skills emit a final ``GATE_SUMMARY:<text>``
    line; ``_extract_gate_summary`` in ``states/base.py`` parses it; the
    handler writes it to ``ctx.metadata`` via ``ctx.set_meta``. When the
    context is not yet persisted (first dispatch hasn't completed) or the
    skill skipped the contract, ``summary`` is ``None`` and the UI renders a
    dimmed fallback.
    """
    config = _load_config(config_path)
    board = BoardProviderFactory.create(config.build_provider_config())

    try:
        ticket = await board.fetch_ticket(ticket_key)
    except BoardNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Board lookup failed: {e}") from e

    status_type = _status_type_for(ticket.status)
    linear = LinearSignal(
        status_type=status_type,
        status_name=ticket.status,
        # We don't walk sub-issues here to keep the call cheap. If a user has
        # child issues they'll still see DONE correctly once Linear's own
        # automation flips the parent. Expose ``all_children_done`` True so
        # the terminal transition works in the common single-issue case.
        all_children_done=True,
    )

    target_slug = await _resolve_target_repo_slug(config)
    doc_pr, code_pr = await fetch_pr_signals(
        ticket_key,
        docs_repo_path=get_docs_repo(),
        target_repo_slug=target_slug,
    )

    snapshot = infer_gate_state(GateSignals(linear=linear, doc_pr=doc_pr, code_pr=code_pr))
    summary = _load_gate_summary(request, ticket_key)

    return GateResponse(
        issue_key=ticket_key,
        state=snapshot.state.value,
        active_pr=_pr_to_info(snapshot.active_pr),
        retry_skill=snapshot.retry_skill,
        reason=snapshot.reason,
        related_prs=[p for p in (_pr_to_info(pr) for pr in snapshot.related_prs) if p],
        linear_status_type=status_type,
        linear_status_name=ticket.status,
        summary=summary,
    )


def _load_gate_summary(request: Request, ticket_key: str) -> str | None:
    """Pull the skill-emitted GATE_SUMMARY sentence from the ticket context.

    Best-effort: a missing store or a not-yet-persisted context returns
    ``None`` rather than 500-ing the gate endpoint.
    """
    store = getattr(request.app.state, "store", None)
    if store is None:
        return None
    try:
        ctx = store.load(ticket_key)
    except Exception as e:  # noqa: BLE001 — best-effort read
        log.warning("Gate summary lookup failed", ticket=ticket_key, error=str(e))
        return None
    if ctx is None:
        return None
    summary = ctx.get_meta("gate_summary")
    return summary or None


@router.post("/{ticket_key}/approve", response_model=GateActionResponse)
async def post_approve(
    ticket_key: str,
    payload: GateApprovePayload,
    config_path: Path = Depends(get_config_path),
) -> GateActionResponse:
    # The ``ticket_key`` is currently informational — ``gh pr review`` acts on
    # the URL directly. Keeping it in the path means the UI can audit which
    # issue the approval belonged to via the request log.
    _load_config(config_path)  # config must exist; we don't read more from it
    if not payload.pr_url:
        raise HTTPException(status_code=400, detail="pr_url is required")
    try:
        out = await approve_pr(payload.pr_url)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=f"gh pr review failed: {e}") from e
    log.info("Gate approved", ticket=ticket_key, pr=payload.pr_url)
    return GateActionResponse(
        ok=True,
        message=f"Approved {payload.pr_url}",
        gh_output=out,
    )


@router.post("/{ticket_key}/request-changes", response_model=GateActionResponse)
async def post_request_changes(
    ticket_key: str,
    payload: GateRequestChangesPayload,
    request: Request,
    config_path: Path = Depends(get_config_path),
) -> GateActionResponse:
    config = _load_config(config_path)
    if not payload.pr_url:
        raise HTTPException(status_code=400, detail="pr_url is required")
    if not payload.feedback.strip():
        raise HTTPException(status_code=400, detail="feedback is required")

    try:
        out = await request_changes(payload.pr_url, payload.feedback)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=f"gh pr review failed: {e}") from e

    resummoned: str | None = None
    if payload.resummon_skill:
        resummoned = await _resummon_skill(
            request=request,
            config=config,
            ticket_key=ticket_key,
            feedback=payload.feedback,
        )

    log.info(
        "Gate change-requested",
        ticket=ticket_key,
        pr=payload.pr_url,
        resummoned_skill=resummoned,
    )
    return GateActionResponse(
        ok=True,
        message=f"Change-requested {payload.pr_url}",
        gh_output=out,
        resummoned_skill=resummoned,
    )


async def _resummon_skill(
    *,
    request: Request,
    config: TaskSummonerConfig,
    ticket_key: str,
    feedback: str,
) -> str | None:
    """Mark the ticket for retry so the orchestrator picks up the feedback.

    We *don't* invoke the skill directly from the HTTP handler — the FSM is
    the single scheduler. Instead we:

      1. Look up the current ``TicketContext``
      2. Stash the feedback in ``metadata['latest_feedback']``
      3. Bump ``retry_count`` and reset ``updated_at`` so the dispatcher picks
         it up on the next poll

    The orchestrator's retry handler already knows how to thread feedback into
    the re-dispatched skill via the ``latest_feedback`` metadata key.
    """
    store = getattr(request.app.state, "store", None)
    if store is None:
        return None

    try:
        ctx = store.load(ticket_key)
    except Exception as e:
        log.warning("Could not load ticket for resummon", ticket=ticket_key, error=str(e))
        return None
    if ctx is None:
        return None

    ctx.set_meta("latest_feedback", feedback)
    ctx.retry_count = (ctx.retry_count or 0) + 1
    # The skill name is inferred from the current state — the UI showed the
    # same name on the retry button. Keep the mapping here for auditability.
    skill_by_state: dict[str, str] = {
        "DOC_REVIEW": "address-doc-feedback",
        "PLAN_REVIEW": "ticket-plan",
        "CODE_REVIEW": "address-code-feedback",
    }
    resummoned = skill_by_state.get(str(ctx.state).split(".")[-1])
    try:
        store.save(ctx)
    except Exception as e:
        log.warning("Could not persist resummon state", ticket=ticket_key, error=str(e))
        return None

    # Yield so the orchestrator can pick it up promptly.
    await asyncio.sleep(0)
    # Quiet typing — ``config`` is unused for now but kept so we can add a
    # provider-specific skill mapping in a follow-up.
    _ = config
    return resummoned


@router.get("/{ticket_key}/states/list", response_model=list[str])
async def list_states(ticket_key: str) -> list[str]:
    """Static list of states — used by the UI to render the chip gallery."""
    _ = ticket_key  # not actually used; path kept for symmetry
    return [s.value for s in GateState]
