"""Tests for LinearAdapter — focus on GraphQL query shape and normalization."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from task_summoner.models.comment import Comment
from task_summoner.models.enums import TicketState
from task_summoner.models.ticket import Ticket
from task_summoner.providers.board import ApprovalDecision, LinearAdapter
from task_summoner.providers.board.linear.client import LinearClient
from task_summoner.providers.config import LinearConfig


def _make_client(response: dict) -> LinearClient:
    client = LinearClient(api_key="k")
    client.query = AsyncMock(return_value=response)  # type: ignore[assignment]
    return client


@pytest.fixture
def config() -> LinearConfig:
    return LinearConfig(api_key="k", team_id="team-1")


class TestLinearAdapterTickets:
    @pytest.mark.asyncio
    async def test_search_eligible_returns_normalized_tickets(self, config):
        response = {
            "issues": {
                "nodes": [
                    {
                        "id": "uuid-1",
                        "identifier": "ENG-1",
                        "title": "hello",
                        "description": "body",
                        "state": {"name": "In Progress"},
                        "labels": {"nodes": [{"name": "task-summoner"}]},
                        "assignee": {"displayName": "Matheus", "email": "m@x"},
                    }
                ]
            }
        }
        adapter = LinearAdapter(config, client=_make_client(response))
        tickets = await adapter.search_eligible()
        assert len(tickets) == 1
        assert isinstance(tickets[0], Ticket)
        assert tickets[0].key == "ENG-1"
        assert tickets[0].labels == ["task-summoner"]
        assert tickets[0].assignee == "Matheus"

    @pytest.mark.asyncio
    async def test_fetch_ticket_returns_normalized_ticket(self, config):
        response = {
            "issue": {
                "id": "uuid-2",
                "identifier": "ENG-2",
                "title": "t",
                "description": None,
                "state": {"name": "Todo"},
                "labels": {"nodes": []},
                "assignee": None,
            }
        }
        adapter = LinearAdapter(config, client=_make_client(response))
        ticket = await adapter.fetch_ticket("ENG-2")
        assert ticket.key == "ENG-2"
        assert ticket.description == ""
        assert ticket.assignee is None

    @pytest.mark.asyncio
    async def test_fetch_ticket_raises_when_not_found(self, config):
        adapter = LinearAdapter(config, client=_make_client({"issue": None}))
        with pytest.raises(RuntimeError, match="not found"):
            await adapter.fetch_ticket("ENG-404")


class TestLinearAdapterComments:
    @pytest.mark.asyncio
    async def test_list_comments_normalizes_and_detects_bot(self, config):
        response = {
            "issue": {
                "comments": {
                    "nodes": [
                        {
                            "id": "c1",
                            "body": "plan [ts:ENG-3:planning:abc]",
                            "createdAt": "2026-04-16T10:00:00Z",
                            "user": {"displayName": "bot"},
                        },
                        {
                            "id": "c2",
                            "body": "lgtm",
                            "createdAt": "2026-04-16T10:05:00Z",
                            "user": {"displayName": "Matheus"},
                        },
                    ]
                }
            }
        }
        adapter = LinearAdapter(config, client=_make_client(response))
        comments = await adapter.list_comments("ENG-3")
        assert len(comments) == 2
        assert isinstance(comments[0], Comment)
        assert comments[0].is_bot is True
        assert comments[1].is_bot is False


class TestLinearAdapterApproval:
    @pytest.mark.asyncio
    async def test_check_approval_pending_when_no_comment_id(self, config):
        adapter = LinearAdapter(config, client=_make_client({}))
        result = await adapter.check_approval("ENG-4", "")
        assert result.decision == ApprovalDecision.PENDING

    @pytest.mark.asyncio
    async def test_check_approval_detects_lgtm(self, config):
        response = {
            "issue": {
                "comments": {
                    "nodes": [
                        {
                            "id": "c1",
                            "body": "plan [ts:ENG-5:planning:x]",
                            "createdAt": "2026-04-16T10:00:00Z",
                            "user": {"displayName": "bot"},
                        },
                        {
                            "id": "c2",
                            "body": "lgtm nice work",
                            "createdAt": "2026-04-16T10:05:00Z",
                            "user": {"displayName": "Matheus"},
                        },
                    ]
                }
            }
        }
        adapter = LinearAdapter(config, client=_make_client(response))
        result = await adapter.check_approval("ENG-5", "c1")
        assert result.decision == ApprovalDecision.APPROVED
        assert result.feedback == "nice work"

    @pytest.mark.asyncio
    async def test_check_approval_detects_retry(self, config):
        response = {
            "issue": {
                "comments": {
                    "nodes": [
                        {
                            "id": "c1",
                            "body": "plan [ts:ENG-6:planning:y]",
                            "createdAt": "2026-04-16T10:00:00Z",
                            "user": {"displayName": "bot"},
                        },
                        {
                            "id": "c2",
                            "body": "retry tests fail",
                            "createdAt": "2026-04-16T10:05:00Z",
                            "user": {"displayName": "Matheus"},
                        },
                    ]
                }
            }
        }
        adapter = LinearAdapter(config, client=_make_client(response))
        result = await adapter.check_approval("ENG-6", "c1")
        assert result.decision == ApprovalDecision.RETRY
        assert result.feedback == "tests fail"


class TestLinearAdapterMutations:
    @pytest.mark.asyncio
    async def test_post_comment_calls_create_mutation(self, config):
        response = {"commentCreate": {"success": True, "comment": {"id": "c-new"}}}
        client = _make_client(response)
        adapter = LinearAdapter(config, client=client)
        result = await adapter.post_comment("ENG-7", "hello")
        assert result == "c-new"
        client.query.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_post_comment_raises_on_failure(self, config):
        response = {"commentCreate": {"success": False, "comment": None}}
        adapter = LinearAdapter(config, client=_make_client(response))
        with pytest.raises(RuntimeError, match="comment create failed"):
            await adapter.post_comment("ENG-8", "body")

    @pytest.mark.asyncio
    async def test_set_state_label_formats_ts_prefix(self, config):
        adapter = LinearAdapter(config, client=_make_client({}))
        adapter.add_label = AsyncMock()  # type: ignore[method-assign]
        await adapter.set_state_label("ENG-9", TicketState.PLANNING)
        adapter.add_label.assert_awaited_once_with("ENG-9", "ts:planning")
