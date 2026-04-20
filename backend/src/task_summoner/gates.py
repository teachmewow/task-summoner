"""Gate inference for the harness flow — pure functions over (Linear, GitHub PRs).

Per the 2026-04 flow-gap-analysis decision, all three human gates are
*uniform GitHub PR reviews*:

  - ``G-A`` Doc review   -> PR in the configured ``docs_repo`` on branch ``rfc/<issue-id>``
  - ``G-B`` Plan review  -> draft PR on the feature branch whose first commit is ``plan.md``
  - ``G-C`` Code review  -> non-draft PR with the implementation diff

The inference combines three signals (Linear state + doc PR + code PR) and
returns one of eight gate states, or ``manual_check`` when they disagree.
``lgtm`` and ``retry`` actions are thin wrappers over ``gh pr review`` and the
surrounding skill dispatch — we never introduce a proprietary approval layer.

This module is deliberately I/O-agnostic: it accepts dataclass snapshots and
returns a dataclass. The API router in ``api/routers/gates.py`` is responsible
for fetching the Linear issue and running ``gh`` to populate the inputs.
"""

from __future__ import annotations

import asyncio
import json
import re
import shlex
from dataclasses import dataclass, field
from enum import Enum

import structlog

from task_summoner.utils import run_cli

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# Public state enum — must match the UI chip labels 1:1
# ---------------------------------------------------------------------------


class GateState(str, Enum):
    """The eight gate states the UI must render."""

    NEEDS_DOC = "needs_doc"
    WRITING_DOC = "writing_doc"
    IN_DOC_REVIEW = "in_doc_review"
    PLANNING = "planning"
    IN_PLAN_REVIEW = "in_plan_review"
    CODING = "coding"
    IN_CODE_REVIEW = "in_code_review"
    DONE = "done"
    # Fallback — the three signals disagree. Don't guess; ask the human.
    MANUAL_CHECK = "manual_check"


# ---------------------------------------------------------------------------
# Input snapshots — fetched once, passed to the pure inference function
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LinearSignal:
    """What Linear says about the issue — state + completion + child counts."""

    # Canonical Linear ``statusType`` ("backlog", "unstarted", "started",
    # "completed", "canceled", "triage"). We don't hard-code English names
    # because Linear workspaces customise state labels freely.
    status_type: str
    status_name: str
    # True iff every child (sub-issue) is in a ``completed`` state.
    all_children_done: bool = True


@dataclass(frozen=True)
class PrSignal:
    """A single PR that may back a gate."""

    url: str
    number: int
    state: str  # "OPEN" | "CLOSED" | "MERGED"
    is_draft: bool
    # True if the PR body or any commit message mentions ``plan.md`` / contains
    # ``plan.md`` in the diff — used to tell plan PRs from code PRs on the same
    # feature branch.
    has_plan_file: bool = False
    # True if the PR has any non-``plan.md`` file changes. Lets us distinguish
    # a plan-only draft from a plan+code PR that's been converted to ready.
    has_code_diff: bool = False
    head_branch: str = ""


@dataclass(frozen=True)
class GateSignals:
    """All three signals consumed by ``infer_gate_state``."""

    linear: LinearSignal
    # Doc PR lives in the docs repo on branch ``rfc/<issue-id>``.
    doc_pr: PrSignal | None = None
    # Code / plan PR lives in the target repo on branch ``<issue-id>-*``.
    code_pr: PrSignal | None = None


@dataclass(frozen=True)
class GateSnapshot:
    """Result of ``infer_gate_state`` — state + the PR that currently gates."""

    state: GateState
    # The PR the ``lgtm`` / ``retry`` buttons act on. None when no PR applies
    # (e.g. ``needs_doc``, ``writing_doc``, ``planning``, ``coding``) or the
    # state machine is ambiguous (``manual_check``).
    active_pr: PrSignal | None
    # The skill name to re-summon on retry. None when no retry action makes
    # sense at the current state.
    retry_skill: str | None
    # Human-readable reason for ``manual_check`` states. Empty otherwise.
    reason: str = ""
    # All PRs we considered — useful for the UI to show "also saw: ..." lines
    # without another round-trip. Deliberately plural in case we extend later.
    related_prs: list[PrSignal] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pure inference — no I/O, fully unit-testable
# ---------------------------------------------------------------------------


_LINEAR_IN_PROGRESS = {"started", "inprogress", "in_progress"}
_LINEAR_TODO = {"unstarted", "todo", "backlog"}
_LINEAR_DONE = {"completed"}


def infer_gate_state(signals: GateSignals) -> GateSnapshot:
    """Collapse (Linear + doc PR + code PR) into one gate state + active PR.

    Rules mirror section 4 of ``tmw-docs/decisions/2026-04-harness-flow-gap-analysis.md``:

    1. Code PR merged + all children done -> ``DONE``.
    2. Non-draft code PR open + doc PR merged (or absent) -> ``IN_CODE_REVIEW``.
    3. Draft code PR with ``plan.md`` + doc PR merged (or absent) -> ``IN_PLAN_REVIEW``.
    4. Open doc PR + Linear "In Progress" -> ``IN_DOC_REVIEW``.
    5. No PRs yet + Linear state tells us the phase heuristically.
    6. Anything that contradicts the above -> ``MANUAL_CHECK``.
    """
    linear = signals.linear
    doc_pr = signals.doc_pr
    code_pr = signals.code_pr
    related = [pr for pr in (doc_pr, code_pr) if pr is not None]

    status_type = linear.status_type.lower()
    is_in_progress = status_type in _LINEAR_IN_PROGRESS
    is_todo = status_type in _LINEAR_TODO
    is_linear_done = status_type in _LINEAR_DONE

    # --- Terminal: code PR merged + children done ---------------------------
    if code_pr and code_pr.state == "MERGED":
        if linear.all_children_done and is_linear_done:
            return GateSnapshot(
                state=GateState.DONE,
                active_pr=None,
                retry_skill=None,
                related_prs=related,
            )
        # Code merged but Linear hasn't caught up or children are still open.
        return GateSnapshot(
            state=GateState.MANUAL_CHECK,
            active_pr=None,
            retry_skill=None,
            reason=(
                "Code PR is merged but Linear state is "
                f"{linear.status_name!r} (children_done={linear.all_children_done})."
            ),
            related_prs=related,
        )

    # --- Code review: non-draft code PR with real diff ----------------------
    if code_pr and code_pr.state == "OPEN" and not code_pr.is_draft and code_pr.has_code_diff:
        if doc_pr is not None and doc_pr.state == "OPEN":
            # Doc still open while code is up for review — something's off.
            return GateSnapshot(
                state=GateState.MANUAL_CHECK,
                active_pr=code_pr,
                retry_skill=None,
                reason="Code PR open for review while doc PR is still open.",
                related_prs=related,
            )
        return GateSnapshot(
            state=GateState.IN_CODE_REVIEW,
            active_pr=code_pr,
            retry_skill="address-code-feedback",
            related_prs=related,
        )

    # --- Plan review: draft code PR that contains plan.md -------------------
    if code_pr and code_pr.state == "OPEN" and code_pr.is_draft and code_pr.has_plan_file:
        if doc_pr is not None and doc_pr.state == "OPEN":
            return GateSnapshot(
                state=GateState.MANUAL_CHECK,
                active_pr=code_pr,
                retry_skill=None,
                reason="Plan PR is open while the doc PR is still open.",
                related_prs=related,
            )
        return GateSnapshot(
            state=GateState.IN_PLAN_REVIEW,
            active_pr=code_pr,
            retry_skill="ticket-plan",
            related_prs=related,
        )

    # --- Doc review: open doc PR ------------------------------------------
    if doc_pr and doc_pr.state == "OPEN":
        if is_in_progress or is_todo:
            return GateSnapshot(
                state=GateState.IN_DOC_REVIEW,
                active_pr=doc_pr,
                retry_skill="address-doc-feedback",
                related_prs=related,
            )
        return GateSnapshot(
            state=GateState.MANUAL_CHECK,
            active_pr=doc_pr,
            retry_skill=None,
            reason=(
                f"Doc PR is open but Linear state is {linear.status_name!r}, "
                "which should be In Progress / Todo during doc review."
            ),
            related_prs=related,
        )

    # --- No PRs yet — pick a phase by Linear state heuristic ---------------
    if code_pr is None and doc_pr is None:
        if is_todo:
            # Could be ``needs_doc`` (pre-classification) or ``writing_doc``
            # once the agent started. We can't tell from outside — default to
            # ``needs_doc`` (the first state) so the UI shows the right chip
            # before the agent wakes up.
            return GateSnapshot(
                state=GateState.NEEDS_DOC,
                active_pr=None,
                retry_skill=None,
                related_prs=related,
            )
        if is_in_progress:
            # In Progress with no PRs means the agent is writing *something*.
            # We can't disambiguate writing-doc vs planning vs coding without
            # more state — default to writing_doc (earliest phase). The agent
            # will post a PR shortly and we'll re-infer.
            return GateSnapshot(
                state=GateState.WRITING_DOC,
                active_pr=None,
                retry_skill=None,
                related_prs=related,
            )
        if is_linear_done:
            return GateSnapshot(
                state=GateState.DONE,
                active_pr=None,
                retry_skill=None,
                related_prs=related,
            )

    # --- Doc PR merged, no code PR yet -> between phases -------------------
    # Doc merged is an unambiguous "move to planning" signal. We used to gate
    # this on ``is_in_progress``, but Linear's own workflow automation flips
    # the issue to Done the moment the linked PR merges — leaving the UI
    # stuck on "Unclassified combination" until the orchestrator's
    # restore-in-progress kicks in. Trust the PR signal; the Linear state
    # gets corrected asynchronously.
    if doc_pr and doc_pr.state == "MERGED" and code_pr is None:
        return GateSnapshot(
            state=GateState.PLANNING,
            active_pr=None,
            retry_skill=None,
            related_prs=related,
        )

    # --- Doc PR merged + code PR closed (not merged) is stuck --------------
    if code_pr and code_pr.state == "CLOSED":
        return GateSnapshot(
            state=GateState.MANUAL_CHECK,
            active_pr=None,
            retry_skill=None,
            reason="Code PR was closed without merging.",
            related_prs=related,
        )

    # --- Draft code PR with NO plan.md — treat as plain coding -------------
    if code_pr and code_pr.state == "OPEN" and code_pr.is_draft and not code_pr.has_plan_file:
        return GateSnapshot(
            state=GateState.CODING,
            active_pr=code_pr,
            retry_skill=None,
            related_prs=related,
        )

    # Anything we haven't covered above is genuinely unusual. Don't guess.
    return GateSnapshot(
        state=GateState.MANUAL_CHECK,
        active_pr=None,
        retry_skill=None,
        reason=(
            f"Unclassified combination: linear={linear.status_type}, "
            f"doc_pr={_pr_summary(doc_pr)}, code_pr={_pr_summary(code_pr)}."
        ),
        related_prs=related,
    )


def _pr_summary(pr: PrSignal | None) -> str:
    if pr is None:
        return "none"
    return f"{pr.state}{'/draft' if pr.is_draft else ''}"


# ---------------------------------------------------------------------------
# ``gh`` integration — the only I/O this module performs
# ---------------------------------------------------------------------------


_GH_TIMEOUT_SEC = 15

# Accept any of ``rfc/ENG-95``, ``rfc/eng-95``, ``rfcs/ENG-95``.
_DOC_BRANCH_PATTERN = re.compile(r"^rfcs?/.+$", re.IGNORECASE)


async def fetch_pr_signals(
    issue_key: str,
    *,
    docs_repo_path: str | None,
    target_repo_slug: str | None = None,
) -> tuple[PrSignal | None, PrSignal | None]:
    """Look up the doc PR (in ``docs_repo``) and code PR (by branch prefix).

    Returns ``(doc_pr, code_pr)``. Either may be ``None`` when no matching PR
    exists. Errors from ``gh`` are logged and surface as ``None`` — the caller
    (the router) decides whether to show an error banner or a stale chip.
    """
    doc_pr_task = _fetch_doc_pr(issue_key, docs_repo_path) if docs_repo_path else _none_task()
    code_pr_task = _fetch_code_pr(issue_key, target_repo_slug)
    doc_pr, code_pr = await asyncio.gather(doc_pr_task, code_pr_task)
    return doc_pr, code_pr


async def _none_task() -> None:
    return None


async def _fetch_doc_pr(issue_key: str, docs_repo_path: str) -> PrSignal | None:
    """Find the ``rfc/<issue-id>`` PR in the local ``docs_repo`` checkout."""
    # We use ``gh pr list`` from inside the repo clone so users don't need to
    # configure the GitHub slug separately.
    head = f"rfc/{issue_key.lower()}"
    try:
        # --search with head: is the least-ambiguous selector. We also fetch
        # merged PRs so ``DONE`` can see a merged doc.
        stdout = await run_cli(
            [
                "gh",
                "pr",
                "list",
                "--state",
                "all",
                "--search",
                f"head:{head}",
                "--json",
                "url,number,state,isDraft,headRefName,files",
                "--limit",
                "5",
            ],
            timeout_sec=_GH_TIMEOUT_SEC,
            env={"GH_REPO": "", "PWD": docs_repo_path},
        )
    except RuntimeError as e:
        log.warning("Doc PR lookup failed", issue=issue_key, error=str(e))
        return None

    try:
        rows = json.loads(stdout or "[]")
    except json.JSONDecodeError:
        return None
    # ``gh`` only looks at the repo we're inside when ``-R`` is unset; force
    # that by running inside docs_repo_path via a tiny shell wrapper if needed.
    if not rows:
        # Retry using -R with the configured origin so the caller can still work
        # from outside docs_repo_path (rare but useful in dev).
        return await _fallback_doc_pr(issue_key, docs_repo_path)
    return _pick_best_pr(rows)


async def _fallback_doc_pr(issue_key: str, docs_repo_path: str) -> PrSignal | None:
    """Try again using ``gh -R <origin>`` resolved from the local clone."""
    slug = await _resolve_origin_slug(docs_repo_path)
    if not slug:
        return None
    head = f"rfc/{issue_key.lower()}"
    try:
        stdout = await run_cli(
            [
                "gh",
                "pr",
                "list",
                "-R",
                slug,
                "--state",
                "all",
                "--search",
                f"head:{head}",
                "--json",
                "url,number,state,isDraft,headRefName,files",
                "--limit",
                "5",
            ],
            timeout_sec=_GH_TIMEOUT_SEC,
        )
    except RuntimeError as e:
        log.warning("Doc PR fallback lookup failed", issue=issue_key, slug=slug, error=str(e))
        return None
    try:
        rows = json.loads(stdout or "[]")
    except json.JSONDecodeError:
        return None
    return _pick_best_pr(rows)


async def _fetch_code_pr(issue_key: str, target_repo_slug: str | None) -> PrSignal | None:
    """Find a PR whose head branch starts with ``<issue-id>-``.

    Searches across all PRs the authenticated user can see. If ``target_repo_slug``
    is provided we narrow the search; otherwise we rely on ``gh search prs``.
    """
    head_prefix = f"{issue_key.lower()}-"
    cmd: list[str]
    if target_repo_slug:
        cmd = [
            "gh",
            "pr",
            "list",
            "-R",
            target_repo_slug,
            "--state",
            "all",
            "--search",
            f"head:{head_prefix}",
            "--json",
            "url,number,state,isDraft,headRefName,files",
            "--limit",
            "5",
        ]
    else:
        cmd = [
            "gh",
            "search",
            "prs",
            f"head:{head_prefix}",
            "--json",
            "url,number,state,isDraft,headRefName,files",
            "--limit",
            "5",
        ]
    try:
        stdout = await run_cli(cmd, timeout_sec=_GH_TIMEOUT_SEC)
    except RuntimeError as e:
        log.warning("Code PR lookup failed", issue=issue_key, error=str(e))
        return None
    try:
        rows = json.loads(stdout or "[]")
    except json.JSONDecodeError:
        return None
    # Only accept PRs whose branch exactly starts with the prefix (avoid
    # accidental matches like ``eng-951-*`` from an issue ``ENG-95``).
    head_rx = re.compile(rf"^{re.escape(issue_key)}-", re.IGNORECASE)
    rows = [r for r in rows if head_rx.match(r.get("headRefName", ""))]
    # Drop merged plan-only PRs. ``ticket-plan`` opens a draft PR on the
    # feature branch containing just ``plan.md``; lgtm squash-merges it to
    # advance the FSM. Before ``ticket-implement`` opens the new code PR on
    # the same branch there's a brief window where the merged plan PR is
    # the only match. Returning it as the "code PR" trips the MANUAL_CHECK
    # rule ("Code PR is merged but Linear state is ...") even though we're
    # actively implementing. Filter those rows out — they're never the
    # "code PR" we care about for gate inference.
    rows = [r for r in rows if not _is_plan_only_merged(r)]
    return _pick_best_pr(rows)


def _is_plan_only_merged(row: dict) -> bool:
    """True iff ``row`` is a MERGED PR whose files are only ``plan.md``."""
    if row.get("state", "") != "MERGED":
        return False
    files = [f.get("path", "") for f in row.get("files", []) if isinstance(f, dict)]
    if not files:
        return False
    has_plan = any(p.endswith("plan.md") or p == "plan.md" for p in files)
    has_code = any(not (p.endswith("plan.md") or p == "plan.md") for p in files)
    return has_plan and not has_code


async def _resolve_origin_slug(repo_path: str) -> str | None:
    """Return ``owner/name`` of the git ``origin`` remote, or None on failure."""
    try:
        stdout = await run_cli(
            [
                "git",
                "-C",
                repo_path,
                "config",
                "--get",
                "remote.origin.url",
            ],
            timeout_sec=5,
        )
    except RuntimeError:
        return None
    url = stdout.strip()
    match = re.search(r"[:/]([^/]+/[^/]+?)(?:\.git)?$", url)
    return match.group(1) if match else None


def _pick_best_pr(rows: list[dict]) -> PrSignal | None:
    """Choose the most-relevant PR from a list — prefer OPEN, then MERGED."""
    if not rows:
        return None
    priority = {"OPEN": 0, "MERGED": 1, "CLOSED": 2}
    rows = sorted(rows, key=lambda r: priority.get(r.get("state", ""), 9))
    row = rows[0]
    files = [f.get("path", "") for f in row.get("files", []) if isinstance(f, dict)]
    has_plan = any(p.endswith("plan.md") or p.endswith("/plan.md") or p == "plan.md" for p in files)
    has_code = any(not (p.endswith("plan.md") or p == "plan.md") for p in files)
    return PrSignal(
        url=row.get("url", ""),
        number=int(row.get("number", 0)),
        state=row.get("state", ""),
        is_draft=bool(row.get("isDraft", False)),
        has_plan_file=has_plan,
        has_code_diff=has_code,
        head_branch=row.get("headRefName", ""),
    )


# ---------------------------------------------------------------------------
# Actions — ``lgtm`` and ``retry with feedback``
# ---------------------------------------------------------------------------


async def merge_pr(pr_url: str) -> str:
    """Run ``gh pr ready <url>`` then ``gh pr merge --squash --delete-branch <url>``.

    ``lgtm`` in task-summoner is a *merge* action, not a GitHub review. We
    don't call ``gh pr review --approve`` because GitHub blocks self-approval
    (the PR author and the runner share ``gh`` credentials). The UI / Linear
    trail is the source of truth for approvals; GitHub only receives the
    merge.

    The ``gh pr ready`` step is mandatory because ``ticket-plan`` opens the
    plan PR in draft mode — GitHub rejects merges on drafts with
    ``GraphQL: Pull Request is still a draft (mergePullRequest)``. ``gh pr
    ready`` on an already-ready PR exits non-zero with a harmless "already
    ready" message, which we swallow so the merge proceeds.

    Idempotency: if the PR has already been merged or closed (most often
    because a prior approve call already won the race — UI double-click,
    stale polling, etc.), ``gh pr ready`` reports ``is closed`` and
    ``gh pr merge`` reports ``already merged``. Both are treated as the
    operation-already-succeeded outcome so a duplicate lgtm returns 200
    instead of a misleading 502. Without this the FSM would stay parked
    at ``WAITING_*_REVIEW`` while the PR was actually merged upstream,
    leaving the human stuck.
    """
    if not pr_url:
        raise ValueError("pr_url is required")
    try:
        await run_cli(["gh", "pr", "ready", pr_url], timeout_sec=_GH_TIMEOUT_SEC)
    except RuntimeError as e:
        msg = str(e).lower()
        # ``gh pr ready`` on a non-draft PR returns:
        #   "Pull request <url> is already ready for review"
        # which is exactly what we want — keep going.
        if "already ready" in msg:
            pass
        # ``gh pr ready`` on a closed/merged PR returns:
        #   "Pull request <url> is closed. Only draft pull requests can be
        #    marked as 'ready for review'"
        # Which means a prior approve already took the PR across the
        # finish line. No point retrying the merge — return early.
        elif "is closed" in msg:
            return f"Pull request {pr_url} already merged or closed (gh pr ready was a no-op)"
        else:
            raise
    try:
        return await run_cli(
            ["gh", "pr", "merge", "--squash", "--delete-branch", pr_url],
            timeout_sec=_GH_TIMEOUT_SEC,
        )
    except RuntimeError as e:
        msg = str(e).lower()
        # Duplicate-merge race: the PR was merged between our ``ready``
        # call (which succeeded) and our ``merge`` call. Treat as success
        # — nothing left to do.
        if "already merged" in msg or "is closed" in msg:
            return f"Pull request {pr_url} already merged"
        raise


async def request_changes(pr_url: str, feedback: str) -> str:
    """Run ``gh pr review --request-changes -b "<feedback>" <url>``."""
    if not pr_url:
        raise ValueError("pr_url is required")
    if not feedback or not feedback.strip():
        raise ValueError("feedback is required")
    return await run_cli(
        ["gh", "pr", "review", "--request-changes", "-b", feedback, pr_url],
        timeout_sec=_GH_TIMEOUT_SEC,
    )


def format_doc_branch(issue_key: str) -> str:
    """Canonical doc-PR branch name for an issue — lowercase for consistency."""
    return f"rfc/{issue_key.lower()}"


def shell_quote(arg: str) -> str:
    """Expose ``shlex.quote`` for tests that assert command safety."""
    return shlex.quote(arg)


__all__ = [
    "GateSignals",
    "GateSnapshot",
    "GateState",
    "LinearSignal",
    "PrSignal",
    "fetch_pr_signals",
    "format_doc_branch",
    "infer_gate_state",
    "merge_pr",
    "request_changes",
    "shell_quote",
]
