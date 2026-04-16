"""Tests for the LinearClient GraphQL wrapper."""

from __future__ import annotations

import httpx
import pytest

from task_summoner.providers.board.linear.client import LinearAPIError, LinearClient


class TestLinearClient:
    @pytest.mark.asyncio
    async def test_query_returns_data_field(self, monkeypatch):
        async def mock_post(self, url, json=None, headers=None):  # noqa: A002
            return httpx.Response(
                status_code=200,
                json={"data": {"issue": {"id": "x"}}},
                request=httpx.Request("POST", url),
            )

        monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)
        client = LinearClient(api_key="k")
        result = await client.query("query { issue { id } }")
        assert result == {"issue": {"id": "x"}}

    @pytest.mark.asyncio
    async def test_query_raises_on_http_error(self, monkeypatch):
        async def mock_post(self, url, json=None, headers=None):  # noqa: A002
            return httpx.Response(
                status_code=500,
                text="server error",
                request=httpx.Request("POST", url),
            )

        monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)
        client = LinearClient(api_key="k")
        with pytest.raises(LinearAPIError, match="HTTP 500"):
            await client.query("query { x }")

    @pytest.mark.asyncio
    async def test_query_raises_on_graphql_errors(self, monkeypatch):
        async def mock_post(self, url, json=None, headers=None):  # noqa: A002
            return httpx.Response(
                status_code=200,
                json={"errors": [{"message": "bad query"}]},
                request=httpx.Request("POST", url),
            )

        monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)
        client = LinearClient(api_key="k")
        with pytest.raises(LinearAPIError, match="GraphQL errors"):
            await client.query("query { x }")

    @pytest.mark.asyncio
    async def test_query_sends_auth_header(self, monkeypatch):
        captured: dict = {}

        async def mock_post(self, url, json=None, headers=None):  # noqa: A002
            captured["headers"] = headers
            captured["json"] = json
            return httpx.Response(
                status_code=200,
                json={"data": {}},
                request=httpx.Request("POST", url),
            )

        monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)
        client = LinearClient(api_key="my-key")
        await client.query("query { x }", {"var": "value"})
        assert captured["headers"]["Authorization"] == "my-key"
        assert captured["json"]["variables"] == {"var": "value"}
