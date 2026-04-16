"""Agent execution result model."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AgentResult(BaseModel):
    """Return value from any agent run."""

    success: bool
    output: str = ""
    artifact_path: str | None = None
    cost_usd: float = Field(default=0.0, ge=0.0)
    num_turns: int = Field(default=0, ge=0)
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
