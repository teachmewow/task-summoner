"""Async GraphQL client for the Linear API."""

from __future__ import annotations

from typing import Any

import httpx
import structlog

log = structlog.get_logger()

_LINEAR_GRAPHQL_URL = "https://api.linear.app/graphql"
_DEFAULT_TIMEOUT_SEC = 30.0


class LinearAPIError(RuntimeError):
    """Raised when the Linear API returns an error response."""


class LinearClient:
    """Thin async wrapper around the Linear GraphQL API."""

    def __init__(
        self,
        api_key: str,
        *,
        url: str = _LINEAR_GRAPHQL_URL,
        timeout_sec: float = _DEFAULT_TIMEOUT_SEC,
    ) -> None:
        self._api_key = api_key
        self._url = url
        self._timeout_sec = timeout_sec

    async def query(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a GraphQL query or mutation. Returns the `data` field."""
        payload: dict[str, Any] = {"query": query}
        if variables is not None:
            payload["variables"] = variables

        async with httpx.AsyncClient(timeout=self._timeout_sec) as client:
            response = await client.post(
                self._url,
                json=payload,
                headers={"Authorization": self._api_key},
            )

        if response.status_code != 200:
            raise LinearAPIError(f"Linear API HTTP {response.status_code}: {response.text}")

        body = response.json()
        if "errors" in body and body["errors"]:
            raise LinearAPIError(f"Linear GraphQL errors: {body['errors']}")

        return body.get("data", {})
