"""Skills editor endpoints — list, read, and save SKILL.md files.

Skills are discovered from the active Claude Code plugin path. In `local`
plugin mode we read `plugin_path/skills/*/SKILL.md` directly and writes
are allowed. In `installed` mode we best-effort discover the plugin from
`~/.claude/plugins/*/task-summoner-workflows`; writes are disabled there because
touching an installed plugin is confusing and the user should fork to
local first.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import structlog
import yaml
from fastapi import APIRouter, Depends, HTTPException

from task_summoner.api.deps import get_config_path
from task_summoner.api.schemas import (
    SkillDetail,
    SkillSavePayload,
    SkillSaveResponse,
    SkillsResponse,
    SkillSummary,
)
from task_summoner.config import TaskSummonerConfig
from task_summoner.providers.config import ClaudeCodeConfig
from task_summoner.utils import atomic_write

log = structlog.get_logger()

router = APIRouter(prefix="/api/skills", tags=["skills"])


def _load_config(config_path: Path) -> TaskSummonerConfig:
    if not config_path.exists():
        raise HTTPException(status_code=409, detail="No config.yaml — run setup first.")
    try:
        return TaskSummonerConfig.load(config_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load config: {e}") from e


def _resolve_plugin_root(config: TaskSummonerConfig) -> tuple[Path | None, str, bool, str | None]:
    """Return (plugin_root, resolved_from, editable, reason_if_not_editable)."""
    if not isinstance(config.providers.agent_config, ClaudeCodeConfig):
        return (
            None,
            "",
            False,
            "Skills editor only supports the claude_code provider.",
        )
    mode = config.plugin_mode
    if mode == "local":
        raw = config.plugin_path
        if not raw:
            return (
                None,
                "",
                False,
                "plugin_mode=local but no plugin_path set in config.yaml.",
            )
        root = Path(raw).expanduser().resolve()
        if not root.is_dir():
            return None, str(root), False, f"Plugin path does not exist: {root}"
        return root, f"local:{root}", True, None
    candidates = [
        Path.home() / ".claude" / "plugins" / "task-summoner-workflows",
        Path.home() / ".config" / "claude" / "plugins" / "task-summoner-workflows",
    ]
    for c in candidates:
        if c.is_dir():
            return (
                c,
                f"installed:{c}",
                False,
                "plugin_mode=installed — editing the shared copy is disabled. "
                "Switch to plugin_mode=local and point plugin_path at a forked copy to edit.",
            )
    return (
        None,
        "",
        False,
        "plugin_mode=installed but task-summoner-workflows was not found under ~/.claude/plugins.",
    )


def _skills_dir(plugin_root: Path) -> Path:
    return plugin_root / "skills"


def _skill_file(plugin_root: Path, name: str) -> Path:
    # Reject names with separators — keep the write path trivially safe.
    if "/" in name or ".." in name or name == "" or name.startswith("."):
        raise HTTPException(status_code=400, detail=f"Invalid skill name: {name!r}")
    return _skills_dir(plugin_root) / name / "SKILL.md"


def _parse_frontmatter(text: str) -> dict:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end == -1:
        return {}
    try:
        data = yaml.safe_load(text[4:end]) or {}
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def _summary(name: str, file_path: Path) -> SkillSummary:
    content = file_path.read_text()
    fm = _parse_frontmatter(content)
    modified = datetime.fromtimestamp(file_path.stat().st_mtime, tz=UTC).isoformat()
    return SkillSummary(
        name=str(fm.get("name", name)),
        description=str(fm.get("description", "")),
        user_invocable=bool(fm.get("user-invocable", False)),
        path=str(file_path),
        modified_at=modified,
    )


@router.get("", response_model=SkillsResponse)
async def list_skills(config_path: Path = Depends(get_config_path)) -> SkillsResponse:
    config = _load_config(config_path)
    plugin_root, resolved_from, editable, reason = _resolve_plugin_root(config)
    if plugin_root is None:
        return SkillsResponse(
            plugin_mode=config.plugin_mode,
            plugin_path=config.plugin_path,
            resolved_from=resolved_from,
            editable=False,
            reason=reason,
            skills=[],
        )

    skills_dir = _skills_dir(plugin_root)
    skills: list[SkillSummary] = []
    if skills_dir.is_dir():
        for entry in sorted(skills_dir.iterdir()):
            f = entry / "SKILL.md"
            if f.is_file():
                skills.append(_summary(entry.name, f))

    return SkillsResponse(
        plugin_mode=config.plugin_mode,
        plugin_path=config.plugin_path,
        resolved_from=resolved_from,
        editable=editable,
        reason=reason,
        skills=skills,
    )


@router.get("/{name}", response_model=SkillDetail)
async def get_skill(name: str, config_path: Path = Depends(get_config_path)) -> SkillDetail:
    config = _load_config(config_path)
    plugin_root, _, _, reason = _resolve_plugin_root(config)
    if plugin_root is None:
        raise HTTPException(status_code=409, detail=reason or "Plugin not resolved")
    file_path = _skill_file(plugin_root, name)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"Skill {name!r} not found")
    summary = _summary(name, file_path)
    return SkillDetail(**summary.model_dump(), content=file_path.read_text())


@router.put("/{name}", response_model=SkillSaveResponse)
async def save_skill(
    name: str,
    payload: SkillSavePayload,
    config_path: Path = Depends(get_config_path),
) -> SkillSaveResponse:
    config = _load_config(config_path)
    plugin_root, _, editable, reason = _resolve_plugin_root(config)
    if plugin_root is None:
        raise HTTPException(status_code=409, detail=reason or "Plugin not resolved")
    if not editable:
        raise HTTPException(status_code=403, detail=reason or "Plugin is read-only")
    file_path = _skill_file(plugin_root, name)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"Skill {name!r} not found")
    atomic_write(file_path, payload.content)
    return SkillSaveResponse(ok=True, skill=_summary(name, file_path))
