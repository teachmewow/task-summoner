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
from task_summoner.core.state_machine import InvalidTransitionError
from task_summoner.gates import (
    GateSignals,
    GateState,
    LinearSignal,
    PrSignal,
    fetch_pr_signals,
    infer_gate_state,
    merge_pr,
    request_changes,
)
from task_summoner.models import TicketState
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


async def _resolve_target_repo_slug(
    config: TaskSummonerConfig,
    labels: list[str] | None = None,
) -> str | None:
    """Best-effort ``owner/name`` for the PR scope.

    When ``labels`` is provided we resolve per-ticket via ``repo:*`` label —
    essential because one issue's code PR may live on a different repo than
    ``default_repo``. Without a label we fall back to the configured default,
    and finally to ``None`` which makes ``gh search prs`` scan everything the
    authenticated user can see.
    """
    repo_path: str | None = None
    if labels:
        try:
            _repo_name, repo_path = config.resolve_repo(labels)
        except ValueError:
            repo_path = None

    if repo_path is None:
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

    target_slug = await _resolve_target_repo_slug(config, ticket.labels)
    doc_pr, code_pr = await fetch_pr_signals(
        ticket_key,
        docs_repo_path=get_docs_repo(),
        target_repo_slug=target_slug,
    )

    snapshot = infer_gate_state(GateSignals(linear=linear, doc_pr=doc_pr, code_pr=code_pr))
    ctx = _load_context(request, ticket_key)
    summary = ctx.get_meta("gate_summary") if ctx else None
    orchestrator_state = ctx.state.value if ctx else None
    orchestrator_pr_url = _orchestrator_pr_url(ctx) if ctx else None
    has_plan = bool(ctx.get_meta("has_plan")) if ctx else False

    # If the FSM is at the plan-review gate, the UI needs to know this is
    # a gate even though inference (no plan PR) reports a different state.
    # Surface it via ``state`` directly so the chip reads correctly.
    gate_state_value = snapshot.state.value
    if orchestrator_state == TicketState.WAITING_PLAN_REVIEW.value:
        gate_state_value = GateState.IN_PLAN_REVIEW.value

    return GateResponse(
        issue_key=ticket_key,
        state=gate_state_value,
        active_pr=_pr_to_info(snapshot.active_pr),
        retry_skill=(
            "ticket-plan"
            if orchestrator_state == TicketState.WAITING_PLAN_REVIEW.value
            else snapshot.retry_skill
        ),
        reason=snapshot.reason,
        related_prs=[p for p in (_pr_to_info(pr) for pr in snapshot.related_prs) if p],
        linear_status_type=status_type,
        linear_status_name=ticket.status,
        summary=summary or None,
        orchestrator_state=orchestrator_state,
        orchestrator_pr_url=orchestrator_pr_url,
        has_plan=has_plan,
    )


def _load_context(request: Request, ticket_key: str):
    """Best-effort read of the orchestrator's TicketContext.

    Returns ``None`` for any failure (missing store, unknown ticket, corrupt
    state.json). Callers degrade gracefully — this is a read-only enrichment
    of the gate response, never the source of 500s.
    """
    store = getattr(request.app.state, "store", None)
    if store is None:
        return None
    try:
        return store.load(ticket_key)
    except Exception as e:  # noqa: BLE001 — best-effort read
        log.warning("Ticket context lookup failed", ticket=ticket_key, error=str(e))
        return None


# Which ``ctx.metadata`` key carries the PR URL for each FSM gate state.
# ``WAITING_PLAN_REVIEW`` is deliberately absent — the plan gate has no
# backing PR (plan lives as a local artifact), so nothing to look up.
_ORCHESTRATOR_PR_META_KEY: dict[str, str] = {
    "WAITING_DOC_REVIEW": "rfc_pr_url",
    "WAITING_MR_REVIEW": "mr_url",
}


def _orchestrator_pr_url(ctx) -> str | None:
    """Look up the PR URL the orchestrator stashed for the current state.

    Falls back to ``ctx.mr_url`` for ``WAITING_MR_REVIEW`` because the
    ImplementingState stores it on the context directly, not in metadata.
    """
    state_name = ctx.state.value if ctx.state else None
    if not state_name:
        return None
    key = _ORCHESTRATOR_PR_META_KEY.get(state_name)
    if not key:
        return None
    value = ctx.get_meta(key) if key != "mr_url" else (ctx.mr_url or ctx.get_meta(key))
    return value or None


@router.post("/{ticket_key}/approve", response_model=GateActionResponse)
async def post_approve(
    ticket_key: str,
    payload: GateApprovePayload,
    request: Request,
    config_path: Path = Depends(get_config_path),
) -> GateActionResponse:
    # ``lgtm`` in task-summoner means "advance the FSM". For the code gate
    # that also runs ``gh pr merge --squash`` so GitHub reflects the
    # approval; for the plan gate it's purely local — the plan lives as
    # ``artifacts/<key>/plan.md`` with no backing PR, so there is nothing
    # to merge on GitHub.
    config = _load_config(config_path)
    current_state = _current_state(request, ticket_key)
    is_plan_gate = current_state == TicketState.WAITING_PLAN_REVIEW

    out = ""
    if is_plan_gate:
        out = f"Plan approved locally for {ticket_key} (no PR required)"
    else:
        if not payload.pr_url:
            raise HTTPException(status_code=400, detail="pr_url is required")
        try:
            out = await merge_pr(payload.pr_url)
        except RuntimeError as e:
            raise HTTPException(status_code=502, detail=f"gh pr merge failed: {e}") from e

    # The (logical) merge went through — advance the FSM and drag Linear
    # to match. The FSM is the single source of truth; we tell Linear
    # what it is.
    new_state = _advance_fsm_after_approve(request, ticket_key)
    if new_state is not None:
        await _align_linear_to_fsm(config, ticket_key, new_state)

    log.info(
        "Gate approved",
        ticket=ticket_key,
        pr=payload.pr_url,
        plan_gate=is_plan_gate,
        new_state=new_state.value if new_state else None,
    )
    return GateActionResponse(
        ok=True,
        message=("Plan approved" if is_plan_gate else f"Merged {payload.pr_url}"),
        gh_output=out,
    )


def _current_state(request: Request, ticket_key: str) -> TicketState | None:
    """Best-effort read of the ticket's current FSM state from the store."""
    store = getattr(request.app.state, "store", None)
    if store is None:
        return None
    try:
        ctx = store.load(ticket_key)
    except Exception:  # noqa: BLE001 — best-effort read
        return None
    return ctx.state if ctx else None


def _advance_fsm_after_approve(request: Request, ticket_key: str) -> TicketState | None:
    """Fire the ``approved`` trigger on the store. Returns the new state, or ``None``.

    We go via the orchestrator's store (installed on ``app.state.store``)
    rather than fabricating a new one so the ctx and the orchestrator poll
    loop agree on what state the ticket is in. A missing store, missing ctx,
    or invalid trigger degrades to ``None`` — the merge already happened, the
    orchestrator's own BaseApprovalState polling will catch up next tick.
    """
    store = getattr(request.app.state, "store", None)
    if store is None:
        return None
    try:
        updated = store.do_transition(ticket_key, "approved")
    except (ValueError, InvalidTransitionError) as e:
        log.warning("FSM advance skipped", ticket=ticket_key, error=str(e))
        return None
    except Exception as e:  # noqa: BLE001 — best-effort
        log.warning("FSM advance failed", ticket=ticket_key, error=str(e))
        return None
    return updated.state


# Which Linear status name each FSM state should be mirrored to after a
# successful ``/approve``. Left-hand side is ``TicketState``; right-hand
# side is a status *name* (boards customise the exact ID). The board
# provider resolves the name to an ID at call time.
#
# Terminal state ``FAILED`` is intentionally absent — a failing ticket is
# a human-decision moment and we don't want to silently push Linear into
# a ``Canceled`` bucket without a review.
_FSM_TO_LINEAR_STATUS: dict[TicketState, str] = {
    TicketState.CREATING_DOC: "In Progress",
    TicketState.WAITING_DOC_REVIEW: "In Progress",
    TicketState.IMPROVING_DOC: "In Progress",
    TicketState.PLANNING: "In Progress",
    TicketState.WAITING_PLAN_REVIEW: "In Progress",
    TicketState.IMPLEMENTING: "In Progress",
    TicketState.WAITING_MR_REVIEW: "In Progress",
    TicketState.FIXING_MR: "In Progress",
    TicketState.DONE: "Done",
}


async def _align_linear_to_fsm(
    config: TaskSummonerConfig, ticket_key: str, fsm_state: TicketState
) -> None:
    """Set the Linear status to match the FSM's authoritative phase.

    Best-effort: the merge already succeeded and the FSM already advanced.
    A Linear transition failure logs and continues so the orchestrator's
    own poll loop can reconcile on the next tick.
    """
    target = _FSM_TO_LINEAR_STATUS.get(fsm_state)
    if target is None:
        log.info("Skipping Linear transition", ticket=ticket_key, fsm_state=fsm_state.value)
        return
    try:
        board = BoardProviderFactory.create(config.build_provider_config())
        await board.transition(ticket_key, target)
    except Exception as e:  # noqa: BLE001 — best-effort
        log.warning(
            "Linear transition failed",
            ticket=ticket_key,
            target=target,
            fsm_state=fsm_state.value,
            error=str(e),
        )


@router.post("/{ticket_key}/request-changes", response_model=GateActionResponse)
async def post_request_changes(
    ticket_key: str,
    payload: GateRequestChangesPayload,
    request: Request,
    config_path: Path = Depends(get_config_path),
) -> GateActionResponse:
    config = _load_config(config_path)
    if not payload.feedback.strip():
        raise HTTPException(status_code=400, detail="feedback is required")

    current_state = _current_state(request, ticket_key)
    is_plan_gate = current_state == TicketState.WAITING_PLAN_REVIEW

    out = ""
    if is_plan_gate:
        # Plan lives as a local artifact (no PR, no GitHub review thread).
        # Feedback is stored in ctx.metadata.latest_feedback and the
        # orchestrator re-runs ``ticket-plan`` with that feedback threaded
        # into the prompt. Zero ``gh`` calls.
        out = f"Plan feedback stored locally for {ticket_key}"
    else:
        if not payload.pr_url:
            raise HTTPException(status_code=400, detail="pr_url is required")
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
        plan_gate=is_plan_gate,
        resummoned_skill=resummoned,
    )
    return GateActionResponse(
        ok=True,
        message=(
            "Plan feedback stored"
            if is_plan_gate
            else f"Change-requested {payload.pr_url}"
        ),
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
