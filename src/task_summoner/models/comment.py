"""Provider-agnostic Comment model."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Comment(BaseModel):
    """Normalized comment from any board provider."""

    id: str
    author: str
    body: str
    created_at: datetime
    is_bot: bool = False
    provider_data: dict[str, Any] = Field(default_factory=dict)
