"""RFC render router (ENG-98).

Read-only. Authoring (editing) happens in a real editor via ``open-editor``.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from task_summoner.api.schemas import (
    OpenEditorPayload,
    OpenEditorResponse,
    RfcResponse,
)
from task_summoner.docs_repo import (
    DocsRepoError,
    open_in_editor,
    read_rfc,
    rfc_image_path,
)
from task_summoner.user_config import get_docs_repo

log = structlog.get_logger()

router = APIRouter(prefix="/api/rfcs", tags=["rfcs"])


_VALID_KEY_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")


def _validate_key(issue_key: str) -> None:
    if not issue_key or any(c not in _VALID_KEY_CHARS for c in issue_key):
        raise HTTPException(status_code=400, detail=f"Invalid issue key: {issue_key!r}")


@router.get("/{issue_key}", response_model=RfcResponse)
async def get_rfc(issue_key: str) -> RfcResponse:
    _validate_key(issue_key)
    if not get_docs_repo():
        return RfcResponse(
            ok=False,
            exists=False,
            issue_key=issue_key,
            reason=(
                "docs_repo is not configured. Run `task-summoner config set docs_repo <path>`."
            ),
        )
    try:
        bundle = read_rfc(issue_key)
    except DocsRepoError as e:
        return RfcResponse(
            ok=False,
            exists=False,
            issue_key=issue_key,
            reason=str(e),
        )
    if bundle is None:
        return RfcResponse(
            ok=True,
            exists=False,
            issue_key=issue_key,
        )
    return RfcResponse(
        ok=True,
        exists=True,
        issue_key=bundle.issue_key,
        title=bundle.title,
        content=bundle.content,
        readme_path=bundle.readme_path,
        images=bundle.images,
    )


@router.get("/{issue_key}/image/{name}")
async def get_rfc_image(issue_key: str, name: str) -> FileResponse:
    _validate_key(issue_key)
    try:
        path = rfc_image_path(issue_key, name)
    except DocsRepoError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return FileResponse(path)


@router.post("/{issue_key}/open-editor", response_model=OpenEditorResponse)
async def post_open_editor(
    issue_key: str,
    payload: OpenEditorPayload,
) -> OpenEditorResponse:
    _validate_key(issue_key)
    # If no explicit path, fall back to the RFC README.
    target = payload.path
    if not target:
        try:
            bundle = read_rfc(issue_key)
        except DocsRepoError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        if bundle is None:
            raise HTTPException(status_code=404, detail=f"No RFC found for {issue_key}")
        target = bundle.readme_path
    try:
        launcher = open_in_editor(target)
    except DocsRepoError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return OpenEditorResponse(
        ok=True,
        launcher=launcher,
        message=f"Opened with {launcher}",
    )
