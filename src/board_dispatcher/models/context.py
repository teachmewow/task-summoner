"""Ticket processing context — persisted state per ticket."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator

from .enums import TicketState


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TicketContext(BaseModel):
    """Persisted state for a ticket being processed."""

    ticket_key: str = Field(..., pattern=r"^[A-Z]+-\d+$")
    state: TicketState
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)
    branch_name: str | None = None
    workspace_path: str | None = None
    mr_url: str | None = None
    retry_count: int = Field(default=0, ge=0)
    total_cost_usd: float = Field(default=0.0, ge=0.0)
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("mr_url")
    @classmethod
    def validate_mr_url(cls, v: str | None) -> str | None:
        if v is not None and not v.startswith("http"):
            raise ValueError(f"MR URL must start with http: {v}")
        return v

    def set_meta(self, key: str, value: Any) -> None:
        self.metadata[key] = value

    def get_meta(self, key: str, default: Any = None) -> Any:
        return self.metadata.get(key, default)

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: dict) -> TicketContext:
        return cls.model_validate(data)
