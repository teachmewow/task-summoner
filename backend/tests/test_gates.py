"""Unit tests for gate-state inference (ENG-95).

We only test the pure ``infer_gate_state`` function plus the tiny status-type
coercion in the router. The ``gh`` and Linear calls are integration-tested
implicitly via the existing provider test suite; here we focus on the rules
that encode the decision doc.
"""

from __future__ import annotations

import pytest

from task_summoner.api.routers.gates import _status_type_for
from task_summoner.gates import (
    GateSignals,
    GateState,
    LinearSignal,
    PrSignal,
    format_doc_branch,
    infer_gate_state,
)


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


class TestBranchHelper:
    def test_format_doc_branch_lowercases(self):
        assert format_doc_branch("ENG-95") == "rfc/eng-95"
        assert format_doc_branch("eng-95") == "rfc/eng-95"
