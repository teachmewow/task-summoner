"""Pre-save lookups used by the /setup form."""

from __future__ import annotations

from pydantic import BaseModel


class LinearTeamsRequest(BaseModel):
    api_key: str


class LinearTeamSummary(BaseModel):
    id: str
    name: str
    key: str


class LinearTeamsResponse(BaseModel):
    ok: bool
    message: str = ""
    teams: list[LinearTeamSummary] = []


__all__ = ["LinearTeamSummary", "LinearTeamsRequest", "LinearTeamsResponse"]
