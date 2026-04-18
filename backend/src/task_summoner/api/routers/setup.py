"""Setup-form-only lookups. Runs before any config is persisted."""

from __future__ import annotations

import structlog
from fastapi import APIRouter

from task_summoner.api.schemas import (
    LinearTeamsRequest,
    LinearTeamsResponse,
    LinearTeamSummary,
)
from task_summoner.providers.board.linear.client import LinearAPIError, LinearClient

log = structlog.get_logger()

router = APIRouter(prefix="/api/setup", tags=["setup"])

_TEAMS_QUERY = "{ teams { nodes { id name key } } }"


@router.post("/linear-teams", response_model=LinearTeamsResponse)
async def linear_teams(payload: LinearTeamsRequest) -> LinearTeamsResponse:
    """Return the teams visible to the given Linear API key.

    Status 200 on both success and failure so the frontend can keep a single
    happy-path handler — the `ok` field discriminates. Mirrors `/api/config/test`.
    """
    api_key = payload.api_key.strip()
    if not api_key:
        return LinearTeamsResponse(ok=False, message="API key is required.")

    try:
        data = await LinearClient(api_key).query(_TEAMS_QUERY)
    except LinearAPIError as e:
        log.warning("Linear teams lookup failed", error=str(e))
        return LinearTeamsResponse(ok=False, message=str(e))
    except Exception as e:
        log.exception("Linear teams lookup crashed")
        return LinearTeamsResponse(ok=False, message=f"Request failed: {e}")

    nodes = (data.get("teams") or {}).get("nodes") or []
    teams = [
        LinearTeamSummary(id=n["id"], name=n.get("name", ""), key=n.get("key", ""))
        for n in nodes
        if n.get("id")
    ]
    return LinearTeamsResponse(ok=True, teams=teams)
