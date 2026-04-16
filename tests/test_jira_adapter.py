"""Tests for JiraAdapter — focus on normalization and approval logic."""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from task_summoner.models.comment import Comment
from task_summoner.models.enums import TicketState
from task_summoner.models.ticket import Ticket
from task_summoner.providers.board import ApprovalDecision, JiraAdapter
from task_summoner.providers.config import JiraConfig


@pytest.fixture
def adapter() -> JiraAdapter:
    return JiraAdapter(JiraConfig(email="e@x.com", token="t"))


class TestJiraAdapter:
    @pytest.mark.asyncio
    async def test_search_eligible_returns_normalized_tickets(self, adapter):
        payload = json.dumps([
            {"key": "LLMOPS-1", "fields": {"summary": "hello", "labels": []}}
        ])
        with patch.object(adapter, "_run_acli", AsyncMock(return_value=payload)):
            tickets = await adapter.search_eligible()
        assert len(tickets) == 1
        assert isinstance(tickets[0], Ticket)
        assert tickets[0].key == "LLMOPS-1"

    @pytest.mark.asyncio
    async def test_fetch_ticket_returns_normalized_ticket(self, adapter):
        payload = json.dumps({"key": "LLMOPS-2", "fields": {"summary": "x"}})
        with patch.object(adapter, "_run_acli", AsyncMock(return_value=payload)):
            ticket = await adapter.fetch_ticket("LLMOPS-2")
        assert isinstance(ticket, Ticket)
        assert ticket.key == "LLMOPS-2"

    @pytest.mark.asyncio
    async def test_list_comments_returns_normalized_comments(self, adapter):
        raw = json.dumps([
            {
                "id": "c1",
                "body": "hello",
                "author": {"displayName": "Matheus"},
                "created": "2026-04-16T10:00:00Z",
            }
        ])
        with patch.object(adapter, "_run_acli", AsyncMock(return_value=raw)):
            comments = await adapter.list_comments("LLMOPS-3")
        assert len(comments) == 1
        assert isinstance(comments[0], Comment)
        assert comments[0].author == "Matheus"
        assert comments[0].body == "hello"
        assert comments[0].is_bot is False

    @pytest.mark.asyncio
    async def test_list_comments_marks_tagged_comment_as_bot(self, adapter):
        raw = json.dumps([
            {
                "id": "c2",
                "body": "Plan here [ts:LLMOPS-4:planning:abc12345]",
                "author": {"displayName": "bot"},
                "created": "2026-04-16T10:00:00Z",
            }
        ])
        with patch.object(adapter, "_run_acli", AsyncMock(return_value=raw)):
            comments = await adapter.list_comments("LLMOPS-4")
        assert comments[0].is_bot is True

    @pytest.mark.asyncio
    async def test_check_approval_pending_when_no_comment_id(self, adapter):
        result = await adapter.check_approval("LLMOPS-5", "")
        assert result.decision == ApprovalDecision.PENDING

    @pytest.mark.asyncio
    async def test_check_approval_pending_when_no_replies(self, adapter):
        raw = [
            {"id": "c1", "body": "[ts:LLMOPS-5:planning:aaa]", "author": {}},
        ]
        with patch.object(adapter, "_raw_list_comments", AsyncMock(return_value=raw)):
            result = await adapter.check_approval(
                "LLMOPS-5", "[ts:LLMOPS-5:planning:aaa]"
            )
        assert result.decision == ApprovalDecision.PENDING

    @pytest.mark.asyncio
    async def test_check_approval_detects_lgtm(self, adapter):
        raw = [
            {"id": "c1", "body": "Plan [ts:LLMOPS-6:planning:bbb]"},
            {"id": "c2", "body": "lgtm go for it"},
        ]
        with patch.object(adapter, "_raw_list_comments", AsyncMock(return_value=raw)):
            result = await adapter.check_approval(
                "LLMOPS-6", "[ts:LLMOPS-6:planning:bbb]"
            )
        assert result.decision == ApprovalDecision.APPROVED
        assert result.feedback == "go for it"

    @pytest.mark.asyncio
    async def test_check_approval_detects_retry(self, adapter):
        raw = [
            {"id": "c1", "body": "Plan [ts:LLMOPS-7:planning:ccc]"},
            {"id": "c2", "body": "retry tests failing"},
        ]
        with patch.object(adapter, "_raw_list_comments", AsyncMock(return_value=raw)):
            result = await adapter.check_approval(
                "LLMOPS-7", "[ts:LLMOPS-7:planning:ccc]"
            )
        assert result.decision == ApprovalDecision.RETRY
        assert result.feedback == "tests failing"

    @pytest.mark.asyncio
    async def test_check_approval_skips_tagged_replies(self, adapter):
        raw = [
            {"id": "c1", "body": "Plan [ts:LLMOPS-8:planning:ddd]"},
            {"id": "c2", "body": "Ack [ts:LLMOPS-8:planning:eee]"},
            {"id": "c3", "body": "lgtm"},
        ]
        with patch.object(adapter, "_raw_list_comments", AsyncMock(return_value=raw)):
            result = await adapter.check_approval(
                "LLMOPS-8", "[ts:LLMOPS-8:planning:ddd]"
            )
        assert result.decision == ApprovalDecision.APPROVED

    @pytest.mark.asyncio
    async def test_set_state_label_formats_ts_prefix(self, adapter):
        with patch.object(adapter, "add_label", AsyncMock()) as mock_add:
            await adapter.set_state_label("LLMOPS-9", TicketState.PLANNING)
        mock_add.assert_awaited_once_with("LLMOPS-9", "ts:planning")

    @pytest.mark.asyncio
    async def test_post_tagged_comment_returns_tag(self, adapter):
        """post_tagged_comment returns the tag itself (robust ID for approval tracking)."""
        tag = "[ts:LLMOPS-10:planning:fff]"
        with patch.object(
            adapter, "post_comment", AsyncMock(return_value="comment-id")
        ) as mock_post:
            result = await adapter.post_tagged_comment("LLMOPS-10", tag, "body")
        assert result == tag
        mock_post.assert_awaited_once_with("LLMOPS-10", f"body\n\n{tag}")
