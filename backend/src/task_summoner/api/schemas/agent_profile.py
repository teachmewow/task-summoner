"""Agent profile response/payload schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AgentProfileOut(BaseModel):
    name: str
    model: str
    max_turns: int
    max_budget_usd: float
    tools: list[str]
    enabled: bool = True


class AgentProfilesResponse(BaseModel):
    agent_provider: str
    available_models: list[str]
    profiles: list[AgentProfileOut]


class AgentProfilePayload(BaseModel):
    model: str
    max_turns: int = Field(ge=1)
    max_budget_usd: float = Field(gt=0)
    tools: list[str]
    enabled: bool = True


class AgentProfileSaveResponse(BaseModel):
    ok: bool
    profile: AgentProfileOut


__all__ = [
    "AgentProfileOut",
    "AgentProfilePayload",
    "AgentProfileSaveResponse",
    "AgentProfilesResponse",
]
