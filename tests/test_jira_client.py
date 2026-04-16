"""Tests for Jira client (acli subprocess wrapper)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from task_summoner.config import TaskSummonerConfig
from task_summoner.tracker import JiraClient
from task_summoner.tracker.adf_converter import extract_text_from_adf


class TestExtractTextFromAdf:
    def test_none_returns_empty(self):
        assert extract_text_from_adf(None) == ""

    def test_string_passthrough(self):
        assert extract_text_from_adf("hello") == "hello"

    def test_simple_adf(self):
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Hello world"}],
                }
            ],
        }
        assert "Hello world" in extract_text_from_adf(adf)

    def test_nested_adf(self):
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "First "},
                        {"type": "text", "text": "Second"},
                    ],
                },
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Third"}],
                },
            ],
        }
        result = extract_text_from_adf(adf)
        assert "First" in result
        assert "Second" in result
        assert "Third" in result

    def test_empty_dict(self):
        assert extract_text_from_adf({}) == ""


class TestJiraClient:
    @pytest.fixture
    def client(self, config: TaskSummonerConfig) -> JiraClient:
        return JiraClient(config)

    @pytest.fixture
    def mock_subprocess(self):
        with patch("task_summoner.tracker.jira_client.asyncio.create_subprocess_exec") as mock:
            proc = AsyncMock()
            proc.returncode = 0
            proc.communicate = AsyncMock()
            mock.return_value = proc
            yield proc

    async def test_search_eligible(self, client, mock_subprocess):
        tickets_json = json.dumps([
            {
                "key": "LLMOPS-42",
                "fields": {
                    "summary": "Test ticket",
                    "status": {"name": "To Do"},
                    "labels": [{"name": "task-summoner"}],
                },
            }
        ])
        mock_subprocess.communicate.return_value = (tickets_json.encode(), b"")

        tickets = await client.search_eligible()
        assert len(tickets) == 1
        assert tickets[0].key == "LLMOPS-42"

    async def test_search_eligible_empty(self, client, mock_subprocess):
        mock_subprocess.communicate.return_value = (b"[]", b"")
        tickets = await client.search_eligible()
        assert tickets == []

    async def test_fetch_ticket(self, client, mock_subprocess):
        ticket_json = json.dumps({
            "key": "LLMOPS-42",
            "fields": {
                "summary": "Test",
                "status": {"name": "In Progress"},
                "labels": [],
            },
        })
        mock_subprocess.communicate.return_value = (ticket_json.encode(), b"")

        ticket = await client.fetch_ticket("LLMOPS-42")
        assert ticket.key == "LLMOPS-42"
        assert ticket.status == "In Progress"

    async def test_post_comment(self, client, mock_subprocess):
        mock_subprocess.communicate.return_value = (b'{"id": "12345"}', b"")
        comment_id = await client.post_comment("LLMOPS-42", "Test comment")
        assert comment_id == "12345"

    async def test_list_comments(self, client, mock_subprocess):
        response = json.dumps({
            "comments": [
                {"id": "1", "body": "First comment"},
                {"id": "2", "body": "approved"},
            ],
            "total": 2,
        })
        mock_subprocess.communicate.return_value = (response.encode(), b"")

        comments = await client.list_comments("LLMOPS-42")
        assert len(comments) == 2
        assert comments[1]["body"] == "approved"

    async def test_acli_failure_raises(self, client, mock_subprocess):
        mock_subprocess.returncode = 1
        mock_subprocess.communicate.return_value = (b"", b"Error: not found")

        with pytest.raises(RuntimeError, match="acli failed"):
            await client.fetch_ticket("BAD-1")

    async def test_acli_timeout_raises(self, client):
        import asyncio

        async def slow_communicate():
            await asyncio.sleep(10)
            return b"", b""

        with patch("task_summoner.tracker.jira_client.asyncio.create_subprocess_exec") as mock:
            proc = AsyncMock()
            proc.returncode = 0
            proc.communicate = slow_communicate
            proc.kill = lambda: None
            mock.return_value = proc

            with pytest.raises(RuntimeError, match="timed out"):
                await client._run_acli("test", timeout=0.01)
