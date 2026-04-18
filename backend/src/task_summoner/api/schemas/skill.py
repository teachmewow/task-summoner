"""Skills editor schemas."""

from __future__ import annotations

from pydantic import BaseModel


class SkillSummary(BaseModel):
    name: str
    description: str
    user_invocable: bool
    path: str
    modified_at: str


class SkillsResponse(BaseModel):
    plugin_mode: str
    plugin_path: str
    resolved_from: str
    editable: bool
    reason: str | None = None
    skills: list[SkillSummary]


class SkillDetail(SkillSummary):
    content: str


class SkillSavePayload(BaseModel):
    content: str


class SkillSaveResponse(BaseModel):
    ok: bool
    skill: SkillSummary


__all__ = [
    "SkillDetail",
    "SkillSavePayload",
    "SkillSaveResponse",
    "SkillSummary",
    "SkillsResponse",
]
