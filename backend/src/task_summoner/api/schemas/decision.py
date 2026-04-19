"""Decisions sidebar API schemas (ENG-96)."""

from __future__ import annotations

from pydantic import BaseModel


class DecisionSummary(BaseModel):
    filename: str
    path: str
    relative_path: str
    title: str
    summary: str
    tags: list[str] = []
    committed_at: str | None = None


class DecisionsResponse(BaseModel):
    ok: bool
    configured: bool
    docs_repo: str | None = None
    # ``template_readme_url`` is surfaced for the empty-state CTA link.
    template_readme_url: str
    decisions: list[DecisionSummary] = []
    reason: str | None = None


class OpenEditorPayload(BaseModel):
    """Shared payload for both decision + RFC open-editor endpoints."""

    path: str


class OpenEditorResponse(BaseModel):
    ok: bool
    launcher: str
    message: str


__all__ = [
    "DecisionSummary",
    "DecisionsResponse",
    "OpenEditorPayload",
    "OpenEditorResponse",
]
