"""Tests for state handler classes (provider-agnostic)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from task_summoner.config import TaskSummonerConfig
from task_summoner.core.state_machine import AGENT_STATES, APPROVAL_STATES
from task_summoner.models import TicketContext, TicketState
from task_summoner.providers.agent import AgentResult
from task_summoner.providers.board import ApprovalDecision, ApprovalResult
from task_summoner.states import build_state_registry
from task_summoner.states import creating_doc as creating_doc_module


class TestStateRegistry:
    def test_all_states_registered(self, config: TaskSummonerConfig):
        registry = build_state_registry(config)
        for state in TicketState:
            assert state in registry, f"Missing handler for {state}"

    def test_agent_states_have_config(self, config: TaskSummonerConfig):
        registry = build_state_registry(config)
        for state in AGENT_STATES:
            handler = registry[state]
            assert handler.requires_agent is True
            assert handler.agent_config is not None

    def test_approval_states(self, config: TaskSummonerConfig):
        registry = build_state_registry(config)
        for state in APPROVAL_STATES:
            assert registry[state].requires_approval is True


class TestQueuedState:
    async def test_handle_creates_workspace_and_claims(self, config, sample_ticket, mock_services):
        registry = build_state_registry(config)
        handler = registry[TicketState.QUEUED]
        ctx = TicketContext(ticket_key="LLMOPS-42", state=TicketState.QUEUED)
        mock_services.workspace.create = AsyncMock(return_value="/tmp/ws/LLMOPS-42")

        trigger = await handler.handle(ctx, sample_ticket, mock_services)

        assert trigger == "start"
        assert ctx.workspace_path == "/tmp/ws/LLMOPS-42"
        mock_services.board.assign.assert_called_once()
        mock_services.board.transition.assert_called_once()


class TestCheckingDocState:
    async def test_doc_exists(self, config, sample_ticket, mock_services):
        registry = build_state_registry(config)
        handler = registry[TicketState.CHECKING_DOC]
        ctx = TicketContext(
            ticket_key="LLMOPS-42",
            state=TicketState.CHECKING_DOC,
            workspace_path="/tmp/ws",
            branch_name="LLMOPS-42-test",
        )
        mock_services.agent.run = AsyncMock(
            return_value=AgentResult(success=True, output="DOC_EXISTS", cost_usd=0.1)
        )
        mock_services.board.post_tagged_comment = AsyncMock(return_value="tag-x")

        trigger = await handler.handle(ctx, sample_ticket, mock_services)
        assert trigger == "doc_exists"

    async def test_doc_not_needed(self, config, sample_ticket, mock_services):
        registry = build_state_registry(config)
        handler = registry[TicketState.CHECKING_DOC]
        ctx = TicketContext(
            ticket_key="LLMOPS-42",
            state=TicketState.CHECKING_DOC,
            workspace_path="/tmp/ws",
            branch_name="LLMOPS-42-test",
        )
        mock_services.agent.run = AsyncMock(
            return_value=AgentResult(success=True, output="DOC_NOT_NEEDED", cost_usd=0.1)
        )
        mock_services.board.post_tagged_comment = AsyncMock(return_value="tag-x")

        trigger = await handler.handle(ctx, sample_ticket, mock_services)
        assert trigger == "doc_not_needed"

    async def test_doc_needed(self, config, sample_ticket, mock_services):
        registry = build_state_registry(config)
        handler = registry[TicketState.CHECKING_DOC]
        ctx = TicketContext(
            ticket_key="LLMOPS-42",
            state=TicketState.CHECKING_DOC,
            workspace_path="/tmp/ws",
            branch_name="LLMOPS-42-test",
        )
        mock_services.agent.run = AsyncMock(
            return_value=AgentResult(success=True, output="DOC_NEEDED", cost_usd=0.1)
        )
        mock_services.board.post_tagged_comment = AsyncMock(return_value="tag-x")

        trigger = await handler.handle(ctx, sample_ticket, mock_services)
        assert trigger == "doc_needed"
        mock_services.board.post_tagged_comment.assert_called_once()
        call_args = mock_services.board.post_tagged_comment.call_args
        body = call_args.args[2] if len(call_args.args) >= 3 else call_args.kwargs["body"]
        assert "Design doc required" in body
        assert ctx.metadata.get("doc_comment_id") == "tag-x"


class TestCreatingDocState:
    """CreatingDocState advances only when the RFC branch really exists."""

    def _make_ctx(self) -> TicketContext:
        return TicketContext(
            ticket_key="LLMOPS-42",
            state=TicketState.CREATING_DOC,
            workspace_path="/tmp/ws",
            branch_name="LLMOPS-42-test",
        )

    def _patch_verify(self, *, branch_present: bool, detail: str = ""):
        check = creating_doc_module._BranchCheck(
            branch_present=branch_present,
            method="ls-remote",
            detail=detail or ("present" if branch_present else "missing"),
        )
        return patch.object(
            creating_doc_module,
            "_verify_rfc_branch",
            AsyncMock(return_value=check),
        )

    async def test_doc_created_when_branch_exists(self, config, sample_ticket, mock_services):
        registry = build_state_registry(config)
        handler = registry[TicketState.CREATING_DOC]
        ctx = self._make_ctx()
        mock_services.agent.run = AsyncMock(
            return_value=AgentResult(
                success=True,
                output=(
                    "RFC opened: https://github.com/teachmewow/tmw-docs/pull/99\n"
                    "Branch: rfc/llmops-42"
                ),
                cost_usd=0.1,
            )
        )
        mock_services.board.post_comment = AsyncMock(return_value="cid")

        with self._patch_verify(branch_present=True):
            trigger = await handler.handle(ctx, sample_ticket, mock_services)

        assert trigger == "doc_created"
        assert ctx.error is None
        assert ctx.get_meta("rfc_branch") == "rfc/llmops-42"
        assert ctx.get_meta("rfc_pr_url") == "https://github.com/teachmewow/tmw-docs/pull/99"
        mock_services.board.post_comment.assert_not_called()

    async def test_missing_branch_marks_failure_and_notifies(
        self, config, sample_ticket, mock_services
    ):
        registry = build_state_registry(config)
        handler = registry[TicketState.CREATING_DOC]
        ctx = self._make_ctx()
        # Retry budget is 2 in the fixture, so max_retries collapses to doc_failed
        # once we've burned the last retry.
        ctx.retry_count = config.retry.max_retries - 1
        mock_services.agent.run = AsyncMock(
            return_value=AgentResult(
                success=True,
                output="Skill finished without producing anything.",
                cost_usd=0.09,
            )
        )
        mock_services.board.post_comment = AsyncMock(return_value="cid")

        with self._patch_verify(
            branch_present=False, detail="rfc/llmops-42 not found on origin or locally"
        ):
            trigger = await handler.handle(ctx, sample_ticket, mock_services)

        assert trigger == "doc_failed"
        assert ctx.error is not None
        assert "no RFC artifact" in ctx.error
        assert "rfc/llmops-42" in ctx.error
        mock_services.board.post_comment.assert_awaited_once()
        comment_body = mock_services.board.post_comment.await_args.args[1]
        assert "Automated doc creation failed" in comment_body

    async def test_missing_branch_retries_within_budget(self, config, sample_ticket, mock_services):
        registry = build_state_registry(config)
        handler = registry[TicketState.CREATING_DOC]
        ctx = self._make_ctx()
        mock_services.agent.run = AsyncMock(
            return_value=AgentResult(success=True, output="", cost_usd=0.01)
        )
        mock_services.board.post_comment = AsyncMock(return_value="cid")

        with self._patch_verify(branch_present=False):
            trigger = await handler.handle(ctx, sample_ticket, mock_services)

        assert trigger == "_retry"
        assert ctx.retry_count == 1
        mock_services.board.post_comment.assert_awaited_once()

    async def test_agent_error_short_circuits_verification(
        self, config, sample_ticket, mock_services
    ):
        registry = build_state_registry(config)
        handler = registry[TicketState.CREATING_DOC]
        ctx = self._make_ctx()
        mock_services.agent.run = AsyncMock(
            return_value=AgentResult(
                success=False,
                error="SDK blew up",
                output="",
                cost_usd=0.0,
            )
        )
        mock_services.board.post_comment = AsyncMock(return_value="cid")

        verify_mock = AsyncMock()
        with patch.object(creating_doc_module, "_verify_rfc_branch", verify_mock):
            trigger = await handler.handle(ctx, sample_ticket, mock_services)

        assert trigger == "_retry"
        assert ctx.retry_count == 1
        # Verification should not even run when the agent itself failed.
        verify_mock.assert_not_awaited()

    def test_prompt_references_renamed_skill(self, config, sample_ticket):
        registry = build_state_registry(config)
        handler = registry[TicketState.CREATING_DOC]
        prompt = handler.build_prompt(sample_ticket)
        assert "task-summoner-workflows:create-design-doc" in prompt
        # Guardrail against re-introducing the broken name.
        assert 'task-summoner-workflows:create-design"' not in prompt


class TestVerifyRfcBranch:
    """Direct tests for the branch-verification helper."""

    async def test_remote_hit_returns_true(self, tmp_path):
        async def fake_run_cli(cmd, *, timeout_sec, env=None):
            if "ls-remote" in cmd:
                return "abcdef1234\trefs/heads/rfc/llmops-42\n"
            raise AssertionError(f"unexpected cmd: {cmd}")

        with (
            patch.object(creating_doc_module, "require_docs_repo", return_value=tmp_path),
            patch.object(creating_doc_module, "run_cli", fake_run_cli),
        ):
            result = await creating_doc_module._verify_rfc_branch("rfc/llmops-42")

        assert result.branch_present is True
        assert result.method == "ls-remote"

    async def test_local_fallback_catches_unpushed_branch(self, tmp_path):
        calls: list[list[str]] = []

        async def fake_run_cli(cmd, *, timeout_sec, env=None):
            calls.append(list(cmd))
            if "ls-remote" in cmd:
                return ""  # nothing on origin
            if "show-ref" in cmd:
                return ""  # local branch present (exit 0 -> no raise)
            raise AssertionError(f"unexpected cmd: {cmd}")

        with (
            patch.object(creating_doc_module, "require_docs_repo", return_value=tmp_path),
            patch.object(creating_doc_module, "run_cli", fake_run_cli),
        ):
            result = await creating_doc_module._verify_rfc_branch("rfc/llmops-42")

        assert result.branch_present is True
        assert result.method == "show-ref"
        assert any("ls-remote" in c for c in calls)
        assert any("show-ref" in c for c in calls)

    async def test_both_checks_fail_reports_missing(self, tmp_path):
        async def fake_run_cli(cmd, *, timeout_sec, env=None):
            if "ls-remote" in cmd:
                return ""
            if "show-ref" in cmd:
                raise RuntimeError("Subprocess failed (exit 1)")
            raise AssertionError(f"unexpected cmd: {cmd}")

        with (
            patch.object(creating_doc_module, "require_docs_repo", return_value=tmp_path),
            patch.object(creating_doc_module, "run_cli", fake_run_cli),
        ):
            result = await creating_doc_module._verify_rfc_branch("rfc/llmops-42")

        assert result.branch_present is False
        assert "not found" in result.detail

    async def test_missing_docs_repo_fails_gracefully(self):
        def boom():
            raise creating_doc_module.DocsRepoError("docs_repo not configured")

        with patch.object(creating_doc_module, "require_docs_repo", side_effect=boom):
            result = await creating_doc_module._verify_rfc_branch("rfc/llmops-42")

        assert result.branch_present is False
        assert "docs_repo" in result.detail


class TestApprovalStates:
    """All three approval states share BaseApprovalState — test the pattern."""

    @pytest.mark.parametrize(
        "state,meta_key",
        [
            (TicketState.WAITING_DOC_REVIEW, "doc_comment_id"),
            (TicketState.WAITING_PLAN_REVIEW, "plan_comment_id"),
            (TicketState.WAITING_MR_REVIEW, "mr_comment_id"),
        ],
    )
    async def test_approved(self, config, sample_ticket, mock_services, state, meta_key):
        registry = build_state_registry(config)
        handler = registry[state]
        tag = "[ts:LLMOPS-42:test:abc12345]"
        ctx = TicketContext(ticket_key="LLMOPS-42", state=state, metadata={meta_key: tag})
        mock_services.board.check_approval = AsyncMock(
            return_value=ApprovalResult(decision=ApprovalDecision.APPROVED)
        )

        trigger = await handler.handle(ctx, sample_ticket, mock_services)
        assert trigger == "approved"

    @pytest.mark.parametrize(
        "state,meta_key",
        [
            (TicketState.WAITING_DOC_REVIEW, "doc_comment_id"),
            (TicketState.WAITING_PLAN_REVIEW, "plan_comment_id"),
            (TicketState.WAITING_MR_REVIEW, "mr_comment_id"),
        ],
    )
    async def test_retry(self, config, sample_ticket, mock_services, state, meta_key):
        registry = build_state_registry(config)
        handler = registry[state]
        tag = "[ts:LLMOPS-42:test:abc12345]"
        ctx = TicketContext(ticket_key="LLMOPS-42", state=state, metadata={meta_key: tag})
        mock_services.board.check_approval = AsyncMock(
            return_value=ApprovalResult(decision=ApprovalDecision.RETRY)
        )
        mock_services.board.post_tagged_comment = AsyncMock(return_value="new-tag")

        trigger = await handler.handle(ctx, sample_ticket, mock_services)
        assert trigger == "retry"

    @pytest.mark.parametrize(
        "state,meta_key",
        [
            (TicketState.WAITING_DOC_REVIEW, "doc_comment_id"),
            (TicketState.WAITING_PLAN_REVIEW, "plan_comment_id"),
            (TicketState.WAITING_MR_REVIEW, "mr_comment_id"),
        ],
    )
    async def test_waiting(self, config, sample_ticket, mock_services, state, meta_key):
        registry = build_state_registry(config)
        handler = registry[state]
        ctx = TicketContext(ticket_key="LLMOPS-42", state=state, metadata={meta_key: "12345"})
        mock_services.board.check_approval = AsyncMock(
            return_value=ApprovalResult(decision=ApprovalDecision.PENDING)
        )

        trigger = await handler.handle(ctx, sample_ticket, mock_services)
        assert trigger == "_wait"

    async def test_no_comment_id_waits_when_no_tag_in_comments(
        self, config, sample_ticket, mock_services
    ):
        registry = build_state_registry(config)
        handler = registry[TicketState.WAITING_PLAN_REVIEW]
        ctx = TicketContext(
            ticket_key="LLMOPS-42",
            state=TicketState.WAITING_PLAN_REVIEW,
            metadata={},
        )
        mock_services.board.list_comments = AsyncMock(return_value=[])

        trigger = await handler.handle(ctx, sample_ticket, mock_services)
        assert trigger == "_wait"


class TestPlanningState:
    async def test_handle_success(self, config, sample_ticket, mock_services):
        registry = build_state_registry(config)
        handler = registry[TicketState.PLANNING]
        ctx = TicketContext(
            ticket_key="LLMOPS-42",
            state=TicketState.PLANNING,
            workspace_path="/tmp/ws",
            branch_name="LLMOPS-42-test",
        )
        plan_dir = Path(config.artifacts_dir) / "LLMOPS-42"
        plan_dir.mkdir(parents=True, exist_ok=True)
        (plan_dir / "plan.md").write_text("## Plan\nDo it")

        mock_services.agent.run = AsyncMock(
            return_value=AgentResult(success=True, output="thinking...", cost_usd=1.0)
        )
        mock_services.board.post_tagged_comment = AsyncMock(side_effect=lambda tid, tag, body: tag)

        trigger = await handler.handle(ctx, sample_ticket, mock_services)

        assert trigger == "plan_complete"
        assert ctx.get_meta("plan_comment_id").startswith("[ts:LLMOPS-42:planning:")
        posted_call = mock_services.board.post_tagged_comment.call_args
        body = posted_call.args[2]
        assert "## Plan" in body

    async def test_handle_failure_retries(self, config, sample_ticket, mock_services):
        registry = build_state_registry(config)
        handler = registry[TicketState.PLANNING]
        ctx = TicketContext(
            ticket_key="LLMOPS-42",
            state=TicketState.PLANNING,
            workspace_path="/tmp/ws",
            branch_name="LLMOPS-42-test",
        )
        mock_services.agent.run = AsyncMock(
            return_value=AgentResult(success=False, error="SDK error")
        )

        trigger = await handler.handle(ctx, sample_ticket, mock_services)
        assert trigger == "_retry"
        assert ctx.retry_count == 1


class TestImplementingState:
    async def test_handle_success_with_pr(self, config, sample_ticket, mock_services):
        registry = build_state_registry(config)
        handler = registry[TicketState.IMPLEMENTING]
        ctx = TicketContext(
            ticket_key="LLMOPS-42",
            state=TicketState.IMPLEMENTING,
            workspace_path="/tmp/ws",
            branch_name="LLMOPS-42-test",
        )
        artifacts = Path(config.artifacts_dir) / "LLMOPS-42"
        artifacts.mkdir(parents=True)
        (artifacts / "implementation_report.md").write_text("Report")

        mock_services.agent.run = AsyncMock(
            return_value=AgentResult(
                success=True,
                output="PR: https://github.com/teachmewow/task-summoner/pull/42",
                cost_usd=5.0,
            )
        )
        mock_services.board.post_tagged_comment = AsyncMock(side_effect=lambda tid, tag, body: tag)

        trigger = await handler.handle(ctx, sample_ticket, mock_services)
        assert trigger == "mr_created"
        assert "42" in ctx.mr_url
        assert ctx.get_meta("mr_comment_id").startswith("[ts:LLMOPS-42:implementing:")


class TestTerminalStates:
    async def test_done_transitions_board(self, config, sample_ticket, mock_services):
        registry = build_state_registry(config)
        ctx = TicketContext(ticket_key="LLMOPS-42", state=TicketState.DONE)
        trigger = await registry[TicketState.DONE].handle(ctx, sample_ticket, mock_services)
        assert trigger == "_noop"
        mock_services.board.transition.assert_called_once_with("LLMOPS-42", "Done")

    async def test_failed_is_noop(self, config, sample_ticket, mock_services):
        registry = build_state_registry(config)
        ctx = TicketContext(ticket_key="LLMOPS-42", state=TicketState.FAILED)
        trigger = await registry[TicketState.FAILED].handle(ctx, sample_ticket, mock_services)
        assert trigger == "_noop"
