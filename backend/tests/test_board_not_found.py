"""Tests for BoardNotFoundError propagation from Jira + Linear adapters."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from task_summoner.providers.board import BoardNotFoundError, JiraAdapter, LinearAdapter
from task_summoner.providers.board.linear.client import LinearAPIError, LinearClient
from task_summoner.providers.config import JiraConfig, LinearConfig


class TestJiraAdapterNotFound:
    @pytest.mark.asyncio
    async def test_fetch_ticket_raises_board_not_found_on_acli_404(self):
        adapter = JiraAdapter(JiraConfig(email="e@x.com", token="t"))
        with patch.object(
            adapter,
            "_run_acli",
            AsyncMock(
                side_effect=RuntimeError("acli failed (exit 1): Issue does not exist: LLMOPS-999")
            ),
        ):
            with pytest.raises(BoardNotFoundError, match="LLMOPS-999"):
                await adapter.fetch_ticket("LLMOPS-999")

    @pytest.mark.asyncio
    async def test_fetch_ticket_reraises_transient_errors(self):
        adapter = JiraAdapter(JiraConfig(email="e@x.com", token="t"))
        with patch.object(
            adapter,
            "_run_acli",
            AsyncMock(side_effect=RuntimeError("acli failed: network timeout")),
        ):
            with pytest.raises(RuntimeError, match="network timeout"):
                await adapter.fetch_ticket("LLMOPS-1")


class TestLinearAdapterNotFound:
    def _make_adapter(self, response_or_error) -> LinearAdapter:
        client = LinearClient(api_key="k")
        if isinstance(response_or_error, Exception):
            client.query = AsyncMock(side_effect=response_or_error)  # type: ignore[assignment]
        else:
            client.query = AsyncMock(return_value=response_or_error)  # type: ignore[assignment]
        return LinearAdapter(LinearConfig(api_key="k", team_id="t"), client=client)

    @pytest.mark.asyncio
    async def test_fetch_ticket_raises_on_entity_not_found_graphql_error(self):
        adapter = self._make_adapter(
            LinearAPIError("Linear GraphQL errors: [{'message': 'Entity not found: Issue'}]")
        )
        with pytest.raises(BoardNotFoundError, match="LLMOPS-999"):
            await adapter.fetch_ticket("LLMOPS-999")

    @pytest.mark.asyncio
    async def test_fetch_ticket_raises_on_null_issue_field(self):
        adapter = self._make_adapter({"issue": None})
        with pytest.raises(BoardNotFoundError, match="ENG-404"):
            await adapter.fetch_ticket("ENG-404")

    @pytest.mark.asyncio
    async def test_fetch_ticket_reraises_other_graphql_errors(self):
        adapter = self._make_adapter(
            LinearAPIError("Linear GraphQL errors: [{'message': 'rate limit exceeded'}]")
        )
        with pytest.raises(LinearAPIError, match="rate limit"):
            await adapter.fetch_ticket("ENG-1")
