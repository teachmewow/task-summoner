"""Plan render router.

Read-only view onto ``artifacts/<issue-key>/plan.md``. Parallels ``rfcs.py``
(docs-repo RFCs) so the frontend can share the same ``MarkdownArtifactPanel``
across both gates. Authoring happens in the user's editor via the same
``open-editor`` contract, with the plan path as target.
"""

from __future__ import annotations

import re
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, HTTPException

from task_summoner.api.deps import get_config_path
from task_summoner.api.schemas import (
    OpenEditorPayload,
    OpenEditorResponse,
    PlanResponse,
)
from task_summoner.config import TaskSummonerConfig
from task_summoner.docs_repo import DocsRepoError, open_in_editor

log = structlog.get_logger()

router = APIRouter(prefix="/api/plans", tags=["plans"])


_VALID_KEY_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")

# First-line heading (``# Title``) if the plan author wrote one. We trim the
# hash prefix + whitespace and use that as the UI title.
_TITLE_PATTERN = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


def _validate_key(issue_key: str) -> None:
    if not issue_key or any(c not in _VALID_KEY_CHARS for c in issue_key):
        raise HTTPException(status_code=400, detail=f"Invalid issue key: {issue_key!r}")


def _load_config(config_path: Path) -> TaskSummonerConfig | None:
    if not config_path.exists():
        return None
    try:
        return TaskSummonerConfig.load(config_path)
    except Exception:  # noqa: BLE001 — surfacing as "not configured" for the UI
        return None


def _plan_path(config: TaskSummonerConfig, issue_key: str) -> Path:
    return Path(config.artifacts_dir).resolve() / issue_key / "plan.md"


@router.get("/{issue_key}", response_model=PlanResponse)
async def get_plan(
    issue_key: str,
    config_path: Path = Depends(get_config_path),
) -> PlanResponse:
    _validate_key(issue_key)
    config = _load_config(config_path)
    if config is None:
        return PlanResponse(
            ok=False,
            exists=False,
            issue_key=issue_key,
            reason="Task-summoner is not configured. Run setup first.",
        )
    path = _plan_path(config, issue_key)
    if not path.exists():
        return PlanResponse(ok=True, exists=False, issue_key=issue_key)
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as e:
        log.warning("Plan read failed", issue=issue_key, error=str(e))
        return PlanResponse(
            ok=False,
            exists=False,
            issue_key=issue_key,
            reason=f"Could not read plan.md: {e}",
        )
    title_match = _TITLE_PATTERN.search(content)
    title = title_match.group(1).strip() if title_match else f"Plan for {issue_key}"
    return PlanResponse(
        ok=True,
        exists=True,
        issue_key=issue_key,
        title=title,
        content=content,
        plan_path=str(path),
    )


@router.post("/{issue_key}/open-editor", response_model=OpenEditorResponse)
async def post_open_editor(
    issue_key: str,
    payload: OpenEditorPayload,
    config_path: Path = Depends(get_config_path),
) -> OpenEditorResponse:
    _validate_key(issue_key)
    config = _load_config(config_path)
    if config is None:
        raise HTTPException(status_code=409, detail="task-summoner is not configured")
    target = payload.path or str(_plan_path(config, issue_key))
    if not Path(target).exists():
        raise HTTPException(status_code=404, detail=f"No plan.md found for {issue_key}")
    try:
        launcher = open_in_editor(target)
    except DocsRepoError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return OpenEditorResponse(
        ok=True,
        launcher=launcher,
        message=f"Opened with {launcher}",
    )
