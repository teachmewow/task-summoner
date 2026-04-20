"""Unit tests for gate-state inference (ENG-95).

We only test the pure ``infer_gate_state`` function plus the tiny status-type
coercion in the router. The ``gh`` and Linear calls are integration-tested
implicitly via the existing provider test suite; here we focus on the rules
that encode the decision doc.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from task_summoner.api.routers.gates import _load_context, _orchestrator_pr_url, _status_type_for
from task_summoner.gates import (
    GateSignals,
    GateState,
    LinearSignal,
    PrSignal,
    format_doc_branch,
    infer_gate_state,
)
from task_summoner.models import TicketContext, TicketState


def _linear(status_type: str, name: str = "", all_children_done: bool = True) -> LinearSignal:
    return LinearSignal(
        status_type=status_type,
        status_name=name or status_type.capitalize(),
        all_children_done=all_children_done,
    )


def _pr(
    *,
    state: str = "OPEN",
    is_draft: bool = False,
    has_plan_file: bool = False,
    has_code_diff: bool = True,
    url: str = "https://github.com/o/r/pull/1",
    head: str = "",
) -> PrSignal:
    return PrSignal(
        url=url,
        number=1,
        state=state,
        is_draft=is_draft,
        has_plan_file=has_plan_file,
        has_code_diff=has_code_diff,
        head_branch=head,
    )


class TestInferAllSevenStates:
    def test_needs_doc_when_todo_no_prs(self):
        snap = infer_gate_state(GateSignals(linear=_linear("unstarted")))
        assert snap.state is GateState.NEEDS_DOC
        assert snap.active_pr is None
        assert snap.retry_skill is None

    def test_writing_doc_when_started_no_prs(self):
        snap = infer_gate_state(GateSignals(linear=_linear("started")))
        assert snap.state is GateState.WRITING_DOC
        assert snap.active_pr is None

    def test_in_doc_review_when_doc_pr_open_and_in_progress(self):
        doc = _pr()
        snap = infer_gate_state(GateSignals(linear=_linear("started"), doc_pr=doc))
        assert snap.state is GateState.IN_DOC_REVIEW
        assert snap.active_pr is doc
        assert snap.retry_skill == "address-doc-feedback"

    def test_planning_when_doc_merged_in_progress_no_code_pr(self):
        doc = _pr(state="MERGED")
        snap = infer_gate_state(GateSignals(linear=_linear("started"), doc_pr=doc))
        assert snap.state is GateState.PLANNING
        assert snap.active_pr is None

    def test_planning_when_doc_merged_and_linear_auto_flipped_done(self):
        """Linear's own automation moves to Done on PR merge; don't stall there.

        Regression: clicking lgtm on the doc PR merged it, Linear fired its
        workflow rule → state became ``completed``, and the inference fell
        through to ``MANUAL_CHECK`` with the useless "Unclassified" message
        even though the path forward is obvious (advance to PLANNING).
        """
        doc = _pr(state="MERGED")
        snap = infer_gate_state(GateSignals(linear=_linear("completed"), doc_pr=doc))
        assert snap.state is GateState.PLANNING

    def test_in_plan_review_when_draft_code_pr_has_plan_file(self):
        code = _pr(is_draft=True, has_plan_file=True, has_code_diff=False)
        snap = infer_gate_state(GateSignals(linear=_linear("started"), code_pr=code))
        assert snap.state is GateState.IN_PLAN_REVIEW
        assert snap.active_pr is code
        assert snap.retry_skill == "ticket-plan"

    def test_in_plan_review_with_merged_doc_pr(self):
        doc = _pr(state="MERGED")
        code = _pr(is_draft=True, has_plan_file=True, has_code_diff=False)
        snap = infer_gate_state(GateSignals(linear=_linear("started"), doc_pr=doc, code_pr=code))
        assert snap.state is GateState.IN_PLAN_REVIEW

    def test_coding_when_draft_code_pr_has_no_plan_file(self):
        code = _pr(is_draft=True, has_plan_file=False, has_code_diff=True)
        snap = infer_gate_state(GateSignals(linear=_linear("started"), code_pr=code))
        assert snap.state is GateState.CODING

    def test_in_code_review_when_ready_pr_has_code_diff(self):
        code = _pr(is_draft=False, has_code_diff=True)
        snap = infer_gate_state(GateSignals(linear=_linear("started"), code_pr=code))
        assert snap.state is GateState.IN_CODE_REVIEW
        assert snap.retry_skill == "address-code-feedback"

    def test_done_when_code_merged_linear_done_children_done(self):
        code = _pr(state="MERGED")
        snap = infer_gate_state(
            GateSignals(
                linear=_linear("completed", all_children_done=True),
                code_pr=code,
            )
        )
        assert snap.state is GateState.DONE
        assert snap.active_pr is None

    def test_done_via_linear_without_any_pr(self):
        """Tickets closed in Linear without a PR (e.g. cancelled work) still land on DONE."""
        snap = infer_gate_state(GateSignals(linear=_linear("completed")))
        assert snap.state is GateState.DONE


class TestManualCheckFallback:
    def test_code_merged_but_linear_not_done(self):
        code = _pr(state="MERGED")
        snap = infer_gate_state(GateSignals(linear=_linear("started"), code_pr=code))
        assert snap.state is GateState.MANUAL_CHECK
        assert "merged" in snap.reason.lower()

    def test_code_merged_but_children_not_done(self):
        code = _pr(state="MERGED")
        snap = infer_gate_state(
            GateSignals(
                linear=_linear("completed", all_children_done=False),
                code_pr=code,
            )
        )
        assert snap.state is GateState.MANUAL_CHECK
        assert "children" in snap.reason.lower()

    def test_code_pr_closed_without_merge(self):
        code = _pr(state="CLOSED")
        snap = infer_gate_state(GateSignals(linear=_linear("started"), code_pr=code))
        assert snap.state is GateState.MANUAL_CHECK
        assert "closed" in snap.reason.lower()

    def test_code_open_while_doc_still_open(self):
        doc = _pr()
        code = _pr(is_draft=False, url="https://github.com/o/r/pull/2")
        snap = infer_gate_state(GateSignals(linear=_linear("started"), doc_pr=doc, code_pr=code))
        assert snap.state is GateState.MANUAL_CHECK

    def test_draft_plan_pr_with_open_doc_pr(self):
        doc = _pr()
        code = _pr(
            is_draft=True,
            has_plan_file=True,
            has_code_diff=False,
            url="https://github.com/o/r/pull/2",
        )
        snap = infer_gate_state(GateSignals(linear=_linear("started"), doc_pr=doc, code_pr=code))
        assert snap.state is GateState.MANUAL_CHECK

    def test_doc_pr_open_but_linear_in_weird_state(self):
        doc = _pr()
        snap = infer_gate_state(
            GateSignals(linear=_linear("canceled", name="Canceled"), doc_pr=doc)
        )
        assert snap.state is GateState.MANUAL_CHECK


class TestRelatedPrs:
    def test_related_prs_includes_all_non_null_signals(self):
        doc = _pr(state="MERGED", url="https://github.com/o/r/pull/10")
        code = _pr(is_draft=False, url="https://github.com/o/r/pull/11")
        snap = infer_gate_state(GateSignals(linear=_linear("started"), doc_pr=doc, code_pr=code))
        urls = {p.url for p in snap.related_prs}
        assert urls == {doc.url, code.url}


class TestStatusTypeMapping:
    @pytest.mark.parametrize(
        "status,expected",
        [
            ("In Progress", "started"),
            ("In Review", "started"),
            ("In plan review", "started"),
            ("Implementing", "started"),
            ("Todo", "unstarted"),
            ("Backlog", "unstarted"),
            ("Done", "completed"),
            ("Completed", "completed"),
            ("Canceled", "canceled"),
            ("", "unstarted"),
            ("SomethingWeird", "unstarted"),
        ],
    )
    def test_mapping(self, status: str, expected: str):
        assert _status_type_for(status) == expected


class TestFetchCodePrFiltersPlanOnlyMerged:
    """``_fetch_code_pr`` must ignore the just-merged plan PR.

    Regression (ENG-151 smoke): after lgtm'ing the plan, there's a brief
    window before ``ticket-implement`` opens the code PR where the only
    matching PR on the branch is the merged plan-only PR. That used to be
    returned as ``code_pr`` and tripped the "Code PR is merged but Linear
    state is 'In Progress'" MANUAL_CHECK false positive. Filtering rules
    out the merged plan-only rows up front so subsequent gate-inference
    passes treat it as "between phases".
    """

    async def test_merged_plan_only_pr_is_filtered(self, monkeypatch):
        import json as _json

        from task_summoner import gates as gates_mod

        async def fake_run(cmd, *, timeout_sec):
            # One merged plan-only PR, no other matches.
            return _json.dumps(
                [
                    {
                        "url": "https://github.com/x/y/pull/19",
                        "number": 19,
                        "state": "MERGED",
                        "isDraft": False,
                        "headRefName": "ENG-151-doc-path",
                        "files": [{"path": "plan.md"}],
                    }
                ]
            )

        monkeypatch.setattr(gates_mod, "run_cli", fake_run)
        result = await gates_mod._fetch_code_pr("ENG-151", "teachmewow/task-summoner-plugin")
        assert result is None

    async def test_merged_code_pr_passes_through(self, monkeypatch):
        """A merged PR with real code diff is still the code PR."""
        import json as _json

        from task_summoner import gates as gates_mod

        async def fake_run(cmd, *, timeout_sec):
            return _json.dumps(
                [
                    {
                        "url": "https://github.com/x/y/pull/20",
                        "number": 20,
                        "state": "MERGED",
                        "isDraft": False,
                        "headRefName": "ENG-151-doc-path",
                        "files": [{"path": "README.md"}],
                    }
                ]
            )

        monkeypatch.setattr(gates_mod, "run_cli", fake_run)
        result = await gates_mod._fetch_code_pr("ENG-151", "teachmewow/task-summoner-plugin")
        assert result is not None
        assert result.number == 20
        assert result.has_code_diff is True

    async def test_open_code_pr_beats_merged_plan_pr(self, monkeypatch):
        """When both exist, the filter drops the plan and picks the live code PR."""
        import json as _json

        from task_summoner import gates as gates_mod

        async def fake_run(cmd, *, timeout_sec):
            return _json.dumps(
                [
                    {
                        "url": "https://github.com/x/y/pull/19",
                        "number": 19,
                        "state": "MERGED",
                        "isDraft": False,
                        "headRefName": "ENG-151-doc-path",
                        "files": [{"path": "plan.md"}],
                    },
                    {
                        "url": "https://github.com/x/y/pull/20",
                        "number": 20,
                        "state": "OPEN",
                        "isDraft": False,
                        "headRefName": "ENG-151-doc-path",
                        "files": [{"path": "README.md"}],
                    },
                ]
            )

        monkeypatch.setattr(gates_mod, "run_cli", fake_run)
        result = await gates_mod._fetch_code_pr("ENG-151", "teachmewow/task-summoner-plugin")
        assert result is not None
        assert result.number == 20


class TestBranchHelper:
    def test_format_doc_branch_lowercases(self):
        assert format_doc_branch("ENG-95") == "rfc/eng-95"
        assert format_doc_branch("eng-95") == "rfc/eng-95"


class TestMergePr:
    """``merge_pr`` is what `lgtm` triggers — a squash-merge, not an approval.

    GitHub blocks self-approval (author == runner), so task-summoner skips the
    review step entirely; the UI / Linear trail is the source of truth.
    """

    async def test_issues_ready_then_squash_merge(self, monkeypatch):
        from task_summoner import gates as gates_mod

        calls: list[list[str]] = []

        async def fake_run(cmd, *, timeout_sec):
            calls.append(list(cmd))
            return "ok" if "ready" in cmd else "merged"

        monkeypatch.setattr(gates_mod, "run_cli", fake_run)
        out = await gates_mod.merge_pr("https://github.com/tmw/x/pull/1")

        assert out == "merged"
        # Flip out of draft (safe no-op on non-drafts) then squash-merge.
        assert calls == [
            ["gh", "pr", "ready", "https://github.com/tmw/x/pull/1"],
            [
                "gh",
                "pr",
                "merge",
                "--squash",
                "--delete-branch",
                "https://github.com/tmw/x/pull/1",
            ],
        ]

    async def test_ready_already_ready_is_swallowed(self, monkeypatch):
        """``gh pr ready`` on a non-draft PR returns non-zero; treat as OK."""
        from task_summoner import gates as gates_mod

        async def fake_run(cmd, *, timeout_sec):
            if "ready" in cmd:
                raise RuntimeError(
                    "Subprocess failed (exit 1): Pull request #1 is already ready for review"
                )
            return "merged"

        monkeypatch.setattr(gates_mod, "run_cli", fake_run)
        out = await gates_mod.merge_pr("https://github.com/tmw/x/pull/1")
        assert out == "merged"

    async def test_ready_other_error_propagates(self, monkeypatch):
        from task_summoner import gates as gates_mod

        async def fake_run(cmd, *, timeout_sec):
            if "ready" in cmd:
                raise RuntimeError("Subprocess failed: HTTP 401 Unauthorized")
            return "merged"

        monkeypatch.setattr(gates_mod, "run_cli", fake_run)
        with pytest.raises(RuntimeError, match="401"):
            await gates_mod.merge_pr("https://github.com/tmw/x/pull/1")

    async def test_empty_url_raises(self):
        from task_summoner.gates import merge_pr

        with pytest.raises(ValueError, match="pr_url"):
            await merge_pr("")

    async def test_ready_is_closed_returns_early_as_success(self, monkeypatch):
        """Duplicate lgtm: PR already merged/closed → treat as success, no 502.

        Reproduces the scenario the ENG-190 smoke hit: a double-click (or
        stale UI refetch) fires a second approve *after* the first one
        already merged the PR. ``gh pr ready`` then returns a
        ``is closed`` error. Without this guard the endpoint raises 502
        and the FSM never advances — leaving the user stuck.
        """
        from task_summoner import gates as gates_mod

        calls: list[list[str]] = []

        async def fake_run(cmd, *, timeout_sec):
            calls.append(list(cmd))
            if "ready" in cmd:
                raise RuntimeError(
                    'Subprocess failed (exit 1): X Pull request '
                    'teachmewow/task-summoner#80 is closed. Only draft pull '
                    'requests can be marked as "ready for review"'
                )
            return "merged"

        monkeypatch.setattr(gates_mod, "run_cli", fake_run)
        out = await gates_mod.merge_pr("https://github.com/tmw/x/pull/80")

        # Only ``gh pr ready`` ran — the merge step is skipped because the
        # PR is already closed. The returned string signals "work done".
        assert len(calls) == 1
        assert "ready" in calls[0]
        assert "already merged or closed" in out

    async def test_merge_already_merged_race_returns_success(self, monkeypatch):
        """PR merged between our ``ready`` and ``merge`` calls → treat as success."""
        from task_summoner import gates as gates_mod

        async def fake_run(cmd, *, timeout_sec):
            if "ready" in cmd:
                return "ok"
            raise RuntimeError("Pull request is already merged")

        monkeypatch.setattr(gates_mod, "run_cli", fake_run)
        out = await gates_mod.merge_pr("https://github.com/tmw/x/pull/80")
        assert "already merged" in out

    async def test_merge_local_branch_delete_fails_but_remote_succeeded(
        self, monkeypatch
    ):
        """Remote merge + remote-branch-delete OK, local branch pinned by worktree.

        Reproduces the ENG-191 smoke: ``gh pr merge --delete-branch`` exits
        non-zero because git can't delete the local branch (still checked out
        at the orchestrator's worktree), even though the remote merge
        already succeeded. The orchestrator tears down the worktree when
        the ticket transitions to DONE — we just need to let the FSM
        advance past the gate.
        """
        from task_summoner import gates as gates_mod

        async def fake_run(cmd, *, timeout_sec):
            if "ready" in cmd:
                return "ok"
            raise RuntimeError(
                "Subprocess failed (exit 1): failed to delete local branch "
                "ENG-191-smoke-add-smoke-verified: failed to run git: error: "
                "Cannot delete branch 'ENG-191-smoke-add-smoke-verified' "
                "checked out at '/private/tmp/task-summoner-workspaces/ENG-191'"
            )

        monkeypatch.setattr(gates_mod, "run_cli", fake_run)
        out = await gates_mod.merge_pr("https://github.com/tmw/x/pull/82")
        assert "local branch cleanup deferred" in out


class TestLoadContext:
    """``_load_context`` is the shared ctx reader for gate enrichment fields."""

    def _request_with_store(self, store):
        app_state = SimpleNamespace(store=store)
        app = SimpleNamespace(state=app_state)
        return SimpleNamespace(app=app)

    def test_returns_ctx_when_present(self):
        ctx = TicketContext(
            ticket_key="ENG-95",
            state=TicketState.PLANNING,
            metadata={"gate_summary": "Plan committed."},
        )
        store = Mock()
        store.load.return_value = ctx

        loaded = _load_context(self._request_with_store(store), "ENG-95")
        assert loaded is ctx
        assert loaded.get_meta("gate_summary") == "Plan committed."

    def test_returns_none_when_context_missing(self):
        store = Mock()
        store.load.return_value = None
        assert _load_context(self._request_with_store(store), "ENG-95") is None

    def test_returns_none_when_store_missing(self):
        assert _load_context(self._request_with_store(None), "ENG-95") is None

    def test_store_exception_degrades_to_none(self):
        store = Mock()
        store.load.side_effect = RuntimeError("disk full")
        assert _load_context(self._request_with_store(store), "ENG-95") is None


class TestOrchestratorPrUrl:
    """``_orchestrator_pr_url`` picks the metadata key for the current state."""

    def test_returns_rfc_pr_for_doc_review(self):
        ctx = TicketContext(
            ticket_key="ENG-1",
            state=TicketState.WAITING_DOC_REVIEW,
            metadata={"rfc_pr_url": "https://github.com/x/y/pull/1"},
        )
        assert _orchestrator_pr_url(ctx) == "https://github.com/x/y/pull/1"

    def test_returns_plan_pr_for_plan_review(self):
        ctx = TicketContext(
            ticket_key="ENG-1",
            state=TicketState.WAITING_PLAN_REVIEW,
            metadata={"plan_pr_url": "https://github.com/x/y/pull/2"},
        )
        assert _orchestrator_pr_url(ctx) == "https://github.com/x/y/pull/2"

    def test_returns_mr_url_for_mr_review(self):
        ctx = TicketContext(
            ticket_key="ENG-1",
            state=TicketState.WAITING_MR_REVIEW,
            mr_url="https://github.com/x/y/pull/3",
        )
        assert _orchestrator_pr_url(ctx) == "https://github.com/x/y/pull/3"

    def test_returns_none_for_non_gate_state(self):
        ctx = TicketContext(ticket_key="ENG-1", state=TicketState.PLANNING)
        assert _orchestrator_pr_url(ctx) is None

    def test_returns_none_when_metadata_missing(self):
        ctx = TicketContext(ticket_key="ENG-1", state=TicketState.WAITING_PLAN_REVIEW)
        assert _orchestrator_pr_url(ctx) is None
