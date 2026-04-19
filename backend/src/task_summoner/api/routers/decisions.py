"""Decisions sidebar router (ENG-96)."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException, Query

from task_summoner.api.schemas import (
    DecisionsResponse,
    DecisionSummary,
    OpenEditorPayload,
    OpenEditorResponse,
)
from task_summoner.docs_repo import (
    DocsRepoError,
    list_decisions,
    open_in_editor,
)
from task_summoner.user_config import get_docs_repo

log = structlog.get_logger()

router = APIRouter(prefix="/api/decisions", tags=["decisions"])

_TEMPLATE_README_URL = "https://github.com/teachmewow/task-summoner-docs-template#decisions"


@router.get("", response_model=DecisionsResponse)
async def get_decisions(
    limit: int = Query(default=10, ge=1, le=100),
) -> DecisionsResponse:
    docs_repo = get_docs_repo()
    if not docs_repo:
        return DecisionsResponse(
            ok=True,
            configured=False,
            docs_repo=None,
            template_readme_url=_TEMPLATE_README_URL,
            reason=(
                "docs_repo is not configured. Run `task-summoner config set docs_repo <path>`."
            ),
        )
    try:
        decisions = await list_decisions(limit=limit)
    except DocsRepoError as e:
        return DecisionsResponse(
            ok=False,
            configured=True,
            docs_repo=docs_repo,
            template_readme_url=_TEMPLATE_README_URL,
            reason=str(e),
        )
    return DecisionsResponse(
        ok=True,
        configured=True,
        docs_repo=docs_repo,
        template_readme_url=_TEMPLATE_README_URL,
        decisions=[
            DecisionSummary(
                filename=d.filename,
                path=d.path,
                relative_path=d.relative_path,
                title=d.title,
                summary=d.summary,
                tags=d.tags,
                committed_at=d.committed_at,
            )
            for d in decisions
        ],
    )


@router.post("/open-editor", response_model=OpenEditorResponse)
async def post_open_editor(payload: OpenEditorPayload) -> OpenEditorResponse:
    if not payload.path:
        raise HTTPException(status_code=400, detail="path is required")
    try:
        launcher = open_in_editor(payload.path)
    except DocsRepoError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return OpenEditorResponse(
        ok=True,
        launcher=launcher,
        message=f"Opened with {launcher}",
    )
