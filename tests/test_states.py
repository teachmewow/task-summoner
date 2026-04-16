"""Tests for state handler classes."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from task_summoner.config import TaskSummonerConfig
from task_summoner.models import AgentResult, Ticket, TicketContext, TicketState
from task_summoner.tracker import ReactionDecision, ReactionResult
from task_summoner.states import build_state_registry
from task_summoner.states.base import StateServices


class TestStateRegistry:
    def test_all_states_registered(self, config: TaskSummonerConfig):
        registry = build_state_registry(config)
        for state in TicketState:
            assert state in registry, f"Missing handler for {state}"

    def test_agent_states_have_config(self, config: TaskSummonerConfig):
        from task_summoner.core.state_machine import AGENT_STATES
        registry = build_state_registry(config)
        for state in AGENT_STATES:
            handler = registry[state]
            assert handler.requires_agent is True
            assert handler.agent_config is not None

    def test_approval_states(self, config: TaskSummonerConfig):
        from task_summoner.core.state_machine import APPROVAL_STATES
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
        mock_services.jira.assign.assert_called_once()
        mock_services.jira.transition.assert_called_once()


class TestCheckingDocState:
    async def test_doc_exists(self, config, sample_ticket, mock_services):
        registry = build_state_registry(config)
        handler = registry[TicketState.CHECKING_DOC]
        ctx = TicketContext(
            ticket_key="LLMOPS-42", state=TicketState.CHECKING_DOC,
            workspace_path="/tmp/ws", branch_name="LLMOPS-42-test",
        )
        mock_services.agent_runner.run = AsyncMock(
            return_value=AgentResult(success=True, output="DOC_EXISTS", cost_usd=0.1)
        )

        trigger = await handler.handle(ctx, sample_ticket, mock_services)
        assert trigger == "doc_exists"

    async def test_doc_not_needed(self, config, sample_ticket, mock_services):
        registry = build_state_registry(config)
        handler = registry[TicketState.CHECKING_DOC]
        ctx = TicketContext(
            ticket_key="LLMOPS-42", state=TicketState.CHECKING_DOC,
            workspace_path="/tmp/ws", branch_name="LLMOPS-42-test",
        )
        mock_services.agent_runner.run = AsyncMock(
            return_value=AgentResult(success=True, output="DOC_NOT_NEEDED", cost_usd=0.1)
        )

        trigger = await handler.handle(ctx, sample_ticket, mock_services)
        assert trigger == "doc_not_needed"

    async def test_doc_needed(self, config, sample_ticket, mock_services):
        registry = build_state_registry(config)
        handler = registry[TicketState.CHECKING_DOC]
        ctx = TicketContext(
            ticket_key="LLMOPS-42", state=TicketState.CHECKING_DOC,
            workspace_path="/tmp/ws", branch_name="LLMOPS-42-test",
        )
        mock_services.agent_runner.run = AsyncMock(
            return_value=AgentResult(success=True, output="DOC_NEEDED", cost_usd=0.1)
        )

        trigger = await handler.handle(ctx, sample_ticket, mock_services)
        assert trigger == "doc_needed"


class TestApprovalStates:
    """All three approval states share BaseApprovalState — test the pattern."""

    @pytest.mark.parametrize("state,meta_key", [
        (TicketState.WAITING_DOC_REVIEW, "doc_comment_id"),
        (TicketState.WAITING_PLAN_REVIEW, "plan_comment_id"),
        (TicketState.WAITING_MR_REVIEW, "mr_comment_id"),
    ])
    async def test_approved(self, config, sample_ticket, mock_services, state, meta_key):
        registry = build_state_registry(config)
        handler = registry[state]
        tag = "[ts:LLMOPS-42:test:abc12345]"
        ctx = TicketContext(
            ticket_key="LLMOPS-42", state=state,
            metadata={meta_key: tag},
        )
        # list_comments must return a comment containing the tag so it's not treated as orphan
        mock_services.jira.list_comments = AsyncMock(return_value=[{"body": f"text {tag}"}])

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("task_summoner.states.base.check_reaction",
                        AsyncMock(return_value=ReactionResult(decision=ReactionDecision.APPROVED)))
            trigger = await handler.handle(ctx, sample_ticket, mock_services)

        assert trigger == "approved"

    @pytest.mark.parametrize("state,meta_key", [
        (TicketState.WAITING_DOC_REVIEW, "doc_comment_id"),
        (TicketState.WAITING_PLAN_REVIEW, "plan_comment_id"),
        (TicketState.WAITING_MR_REVIEW, "mr_comment_id"),
    ])
    async def test_retry(self, config, sample_ticket, mock_services, state, meta_key):
        registry = build_state_registry(config)
        handler = registry[state]
        tag = "[ts:LLMOPS-42:test:abc12345]"
        ctx = TicketContext(
            ticket_key="LLMOPS-42", state=state,
            metadata={meta_key: tag},
        )
        mock_services.jira.list_comments = AsyncMock(return_value=[{"body": f"text {tag}"}])

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("task_summoner.states.base.check_reaction",
                        AsyncMock(return_value=ReactionResult(decision=ReactionDecision.RETRY)))
            trigger = await handler.handle(ctx, sample_ticket, mock_services)

        assert trigger == "retry"

    @pytest.mark.parametrize("state,meta_key", [
        (TicketState.WAITING_DOC_REVIEW, "doc_comment_id"),
        (TicketState.WAITING_PLAN_REVIEW, "plan_comment_id"),
        (TicketState.WAITING_MR_REVIEW, "mr_comment_id"),
    ])
    async def test_waiting(self, config, sample_ticket, mock_services, state, meta_key):
        registry = build_state_registry(config)
        handler = registry[state]
        ctx = TicketContext(
            ticket_key="LLMOPS-42", state=state,
            metadata={meta_key: "12345"},
        )

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("task_summoner.states.base.check_reaction",
                        AsyncMock(return_value=ReactionResult(decision=ReactionDecision.WAITING)))
            trigger = await handler.handle(ctx, sample_ticket, mock_services)

        assert trigger == "_wait"

    async def test_no_comment_id_waits(self, config, sample_ticket, mock_services):
        registry = build_state_registry(config)
        handler = registry[TicketState.WAITING_PLAN_REVIEW]
        ctx = TicketContext(
            ticket_key="LLMOPS-42", state=TicketState.WAITING_PLAN_REVIEW,
            metadata={},  # No comment ID
        )

        trigger = await handler.handle(ctx, sample_ticket, mock_services)
        assert trigger == "_wait"


class TestPlanningState:
    async def test_handle_success(self, config, sample_ticket, mock_services):
        registry = build_state_registry(config)
        handler = registry[TicketState.PLANNING]
        ctx = TicketContext(
            ticket_key="LLMOPS-42", state=TicketState.PLANNING,
            workspace_path="/tmp/ws", branch_name="LLMOPS-42-test",
        )

        # Agent must write the plan file — simulate that
        plan_dir = Path(config.artifacts_dir) / "LLMOPS-42"
        plan_dir.mkdir(parents=True, exist_ok=True)
        (plan_dir / "plan.md").write_text("## Plan\nDo it")

        mock_services.agent_runner.run = AsyncMock(
            return_value=AgentResult(success=True, output="thinking...", cost_usd=1.0)
        )

        trigger = await handler.handle(ctx, sample_ticket, mock_services)

        assert trigger == "plan_complete"
        assert ctx.get_meta("plan_comment_id").startswith("[ts:LLMOPS-42:planning:")
        # Verify the Jira comment was posted as ADF JSON
        posted = mock_services.jira.post_comment.call_args[0][1]
        import json
        adf = json.loads(posted)
        assert adf["version"] == 1
        assert adf["type"] == "doc"
        assert len(adf["content"]) >= 2  # plan nodes + approval + bd tag

    async def test_handle_failure_retries(self, config, sample_ticket, mock_services):
        registry = build_state_registry(config)
        handler = registry[TicketState.PLANNING]
        ctx = TicketContext(
            ticket_key="LLMOPS-42", state=TicketState.PLANNING,
            workspace_path="/tmp/ws", branch_name="LLMOPS-42-test",
        )
        mock_services.agent_runner.run = AsyncMock(
            return_value=AgentResult(success=False, error="SDK error")
        )

        trigger = await handler.handle(ctx, sample_ticket, mock_services)
        assert trigger == "_retry"
        assert ctx.retry_count == 1


class TestImplementingState:
    async def test_handle_success_with_mr(self, config, sample_ticket, mock_services):
        registry = build_state_registry(config)
        handler = registry[TicketState.IMPLEMENTING]
        ctx = TicketContext(
            ticket_key="LLMOPS-42", state=TicketState.IMPLEMENTING,
            workspace_path="/tmp/ws", branch_name="LLMOPS-42-test",
        )
        plan_dir = Path(config.artifacts_dir) / "LLMOPS-42"
        plan_dir.mkdir(parents=True)
        (plan_dir / "plan.md").write_text("Plan")

        mock_services.agent_runner.run = AsyncMock(
            return_value=AgentResult(
                success=True,
                output="MR: https://github.com/teachmewow/task-summoner/pull/42",
                cost_usd=5.0,
            )
        )
        mock_services.jira.list_comments = AsyncMock(return_value=[{"id": "888"}])

        trigger = await handler.handle(ctx, sample_ticket, mock_services)
        assert trigger == "mr_created"
        assert "42" in ctx.mr_url
        assert ctx.get_meta("mr_comment_id").startswith("[ts:LLMOPS-42:implementing:")


class TestTerminalStates:
    async def test_done_transitions_jira(self, config, sample_ticket, mock_services):
        registry = build_state_registry(config)
        ctx = TicketContext(ticket_key="LLMOPS-42", state=TicketState.DONE)
        trigger = await registry[TicketState.DONE].handle(ctx, sample_ticket, mock_services)
        assert trigger == "_noop"
        mock_services.jira.transition.assert_called_once_with("LLMOPS-42", "Done")

    async def test_failed_is_noop(self, config, sample_ticket, mock_services):
        registry = build_state_registry(config)
        ctx = TicketContext(ticket_key="LLMOPS-42", state=TicketState.FAILED)
        trigger = await registry[TicketState.FAILED].handle(ctx, sample_ticket, mock_services)
        assert trigger == "_noop"
