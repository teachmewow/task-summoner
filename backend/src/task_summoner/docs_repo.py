"""Shared helpers for reading the configured ``docs_repo``.

Both the decisions sidebar (ENG-96) and the RFC render panel (ENG-98) need to
locate, open, and inspect files inside the user's ``docs_repo``. Resolution
precedence lives in ``user_config`` — this module builds on that and adds:

- path helpers (``decisions_dir``, ``rfc_dir``)
- minimal YAML frontmatter parser (re-uses ``pyyaml``)
- ``git log``-based mtime (so "recent" means "recently committed", not
  "recently modified on disk" — which can be skewed by branch switches)
- ``open_in_editor`` dispatch (VSCode / Cursor / fallback)

All functions raise ``DocsRepoError`` (or return empty results) instead of
``HTTPException`` so the API layer can decide the right status code.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog
import yaml

from task_summoner.user_config import get_docs_repo
from task_summoner.utils import run_cli

log = structlog.get_logger()


class DocsRepoError(RuntimeError):
    """Raised for user-facing failures (no docs_repo set, missing file, etc.)."""


# ---------------------------------------------------------------------------
# Resolution — single source of truth for "where is docs_repo?"
# ---------------------------------------------------------------------------


def require_docs_repo() -> Path:
    """Return the configured ``docs_repo`` path or raise ``DocsRepoError``.

    The caller is expected to translate ``DocsRepoError`` into a 409 (config
    missing) or 404 (path gone). We don't leak HTTP concerns into this module.
    """
    raw = get_docs_repo()
    if not raw:
        raise DocsRepoError(
            "docs_repo is not configured. Run `task-summoner config set docs_repo <path>` "
            "or visit /setup."
        )
    path = Path(raw).expanduser()
    if not path.is_dir():
        raise DocsRepoError(f"docs_repo path is not a directory: {path}")
    return path


def decisions_dir(root: Path | None = None) -> Path:
    """``<docs_repo>/decisions`` — convention from task-summoner-docs-template."""
    base = root or require_docs_repo()
    return base / "decisions"


def rfc_dir(issue_key: str, root: Path | None = None) -> Path:
    """``<docs_repo>/rfcs/<ISSUE-KEY>`` — matches ``create-design-doc`` output."""
    base = root or require_docs_repo()
    return base / "rfcs" / issue_key


# ---------------------------------------------------------------------------
# Frontmatter parser — minimal, YAML-based, safe-load only
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParsedMarkdown:
    """Markdown file split into frontmatter + body + derived metadata."""

    frontmatter: dict[str, Any]
    body: str
    title: str  # First H1 heading, or filename fallback.
    summary: str  # ``summary:`` frontmatter, else first paragraph of body.
    tags: list[str]  # From frontmatter ``tags:`` (list or CSV), normalised.


def parse_markdown(text: str, *, fallback_title: str = "") -> ParsedMarkdown:
    """Split ``---`` YAML frontmatter + body, extract title / summary / tags.

    Silently tolerates:
      - missing frontmatter (returns empty dict)
      - malformed YAML (returns empty dict, preserves body)
      - missing H1 (uses ``fallback_title`` or first non-empty line)
    """
    frontmatter, body = _split_frontmatter(text)
    title = _extract_title(body) or fallback_title
    summary = _coerce_str(frontmatter.get("summary")) or _first_paragraph(body)
    tags = _normalize_tags(frontmatter.get("tags"))
    return ParsedMarkdown(
        frontmatter=frontmatter,
        body=body,
        title=title,
        summary=summary,
        tags=tags,
    )


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text
    # Find the closing ``---`` at the start of a line.
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    closing_idx: int | None = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            closing_idx = i
            break
    if closing_idx is None:
        return {}, text
    raw = "\n".join(lines[1:closing_idx])
    body = "\n".join(lines[closing_idx + 1 :]).lstrip("\n")
    try:
        data = yaml.safe_load(raw) or {}
    except yaml.YAMLError:
        return {}, body
    return (data if isinstance(data, dict) else {}), body


def _extract_title(body: str) -> str:
    for raw in body.splitlines():
        stripped = raw.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return ""


def _first_paragraph(body: str) -> str:
    paragraph: list[str] = []
    started = False
    for raw in body.splitlines():
        stripped = raw.strip()
        if stripped.startswith("#"):
            # Skip headings.
            continue
        if not stripped:
            if started:
                break
            continue
        started = True
        paragraph.append(stripped)
    joined = " ".join(paragraph).strip()
    # Trim to a reasonable summary length — the UI will clip further.
    return joined[:240]


def _coerce_str(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _normalize_tags(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(t).strip() for t in value if str(t).strip()]
    if isinstance(value, str):
        return [t.strip() for t in value.split(",") if t.strip()]
    return []


# ---------------------------------------------------------------------------
# Decisions listing — sorted by git commit time
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DecisionEntry:
    """One row in the sidebar."""

    path: str  # Absolute local path.
    relative_path: str  # Path relative to docs_repo root.
    filename: str
    title: str
    summary: str
    tags: list[str]
    committed_at: str | None  # ISO 8601 from ``git log``; None if untracked.


async def list_decisions(limit: int | None = None) -> list[DecisionEntry]:
    """Enumerate ``decisions/*.md``, parse frontmatter, sort by commit time.

    Files not tracked by git (e.g. untracked drafts) are included at the end
    with ``committed_at=None``. This matches the CLAUDE-Md convention: show
    what's on disk, but prefer the commit clock for ordering.
    """
    root = require_docs_repo()
    d_dir = decisions_dir(root)
    if not d_dir.is_dir():
        return []

    md_files = sorted(d_dir.glob("*.md"))
    if not md_files:
        return []

    commit_times = await _git_commit_times(root, md_files)
    entries: list[DecisionEntry] = []
    for file_path in md_files:
        try:
            raw = file_path.read_text(encoding="utf-8")
        except OSError as e:
            log.warning("Failed to read decision file", path=str(file_path), error=str(e))
            continue
        parsed = parse_markdown(raw, fallback_title=file_path.stem)
        rel = file_path.relative_to(root)
        entries.append(
            DecisionEntry(
                path=str(file_path),
                relative_path=str(rel),
                filename=file_path.name,
                title=parsed.title or file_path.stem,
                summary=parsed.summary,
                tags=parsed.tags,
                committed_at=commit_times.get(file_path.name),
            )
        )

    # Sort: committed entries first (sorted desc by commit time), then
    # untracked entries (sorted desc by filename so newer-looking dates
    # bubble up). Two passes so ``reverse=True`` doesn't also flip the
    # tracked-vs-untracked bucket order.
    tracked = [e for e in entries if e.committed_at]
    untracked = [e for e in entries if not e.committed_at]
    tracked.sort(key=lambda e: (e.committed_at or "", e.filename), reverse=True)
    untracked.sort(key=lambda e: e.filename, reverse=True)
    entries = tracked + untracked
    if limit is not None and limit > 0:
        entries = entries[:limit]
    return entries


async def _git_commit_times(root: Path, files: list[Path]) -> dict[str, str]:
    """Return ``{filename: ISO8601}`` for each file tracked by git."""
    if not files:
        return {}
    # ``git log --format=%aI -n 1 -- <file>`` per file. Cheap enough for ≤ 50
    # decisions; if that grows we can batch with ``git log --name-only``.
    out: dict[str, str] = {}
    for file_path in files:
        try:
            stdout = await run_cli(
                [
                    "git",
                    "-C",
                    str(root),
                    "log",
                    "--format=%aI",
                    "-n",
                    "1",
                    "--",
                    str(file_path.relative_to(root)),
                ],
                timeout_sec=5,
            )
        except RuntimeError:
            continue
        iso = stdout.strip().splitlines()[0].strip() if stdout.strip() else ""
        if iso:
            out[file_path.name] = iso
    return out


# ---------------------------------------------------------------------------
# RFC reading — one function, because the router is the place that cares
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RfcBundle:
    """The RFC README + list of images referenced alongside it."""

    issue_key: str
    readme_path: str
    content: str
    title: str
    images: list[str]  # filenames under the RFC dir (e.g. ["impact.png"])


def read_rfc(issue_key: str) -> RfcBundle | None:
    """Return the RFC for ``<issue_key>`` or ``None`` when no README exists."""
    directory = rfc_dir(issue_key)
    readme = directory / "README.md"
    if not readme.is_file():
        return None
    try:
        raw = readme.read_text(encoding="utf-8")
    except OSError as e:
        raise DocsRepoError(f"Failed to read RFC README: {e}") from e
    parsed = parse_markdown(raw, fallback_title=issue_key)
    images = sorted(
        p.name
        for p in directory.iterdir()
        if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".svg"}
    )
    return RfcBundle(
        issue_key=issue_key,
        readme_path=str(readme),
        content=raw,
        title=parsed.title,
        images=images,
    )


def rfc_image_path(issue_key: str, name: str) -> Path:
    """Resolve + safety-check an image path under the RFC directory.

    Rejects traversal (``..``) and separators so the API can serve the file
    without becoming an arbitrary-read oracle.
    """
    if "/" in name or "\\" in name or ".." in name or name.startswith("."):
        raise DocsRepoError(f"Invalid image name: {name!r}")
    directory = rfc_dir(issue_key)
    candidate = directory / name
    # Belt-and-braces: make sure the resolved path is still under ``directory``.
    try:
        candidate.resolve().relative_to(directory.resolve())
    except ValueError as e:
        raise DocsRepoError(f"Image is outside the RFC directory: {name}") from e
    if not candidate.is_file():
        raise DocsRepoError(f"Image not found: {name}")
    return candidate


# ---------------------------------------------------------------------------
# Editor launch — VSCode / Cursor / fallback
# ---------------------------------------------------------------------------


def open_in_editor(target: str) -> str:
    """Open ``target`` (file or directory) in an editor.

    Preference order:
      1. ``$TASK_SUMMONER_EDITOR`` (explicit override — command name or path)
      2. ``cursor`` on PATH
      3. ``code`` on PATH (VSCode)
      4. ``open`` on macOS / ``xdg-open`` on Linux — last-resort fallback

    Returns the name of the launcher used. Raises ``DocsRepoError`` when
    nothing is available.
    """
    path = Path(target).expanduser()
    if not path.exists():
        raise DocsRepoError(f"Path does not exist: {path}")

    override = os.environ.get("TASK_SUMMONER_EDITOR")
    candidates: list[str] = []
    if override:
        candidates.append(override)
    candidates.extend(["cursor", "code"])

    for cmd in candidates:
        if shutil.which(cmd):
            _launch(cmd, str(path))
            return cmd

    # OS fallback.
    if shutil.which("open"):
        _launch("open", str(path))
        return "open"
    if shutil.which("xdg-open"):
        _launch("xdg-open", str(path))
        return "xdg-open"

    raise DocsRepoError(
        "No editor found. Install VSCode (`code`) or Cursor (`cursor`), or set "
        "$TASK_SUMMONER_EDITOR to the command you use."
    )


def _launch(cmd: str, path: str) -> None:
    """Fire-and-forget — we don't wait for the editor to exit."""
    try:
        subprocess.Popen(  # noqa: S603 — cmd is from our own candidate list
            [cmd, path],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as e:
        raise DocsRepoError(f"Failed to launch {cmd}: {e}") from e


__all__ = [
    "DecisionEntry",
    "DocsRepoError",
    "ParsedMarkdown",
    "RfcBundle",
    "decisions_dir",
    "list_decisions",
    "open_in_editor",
    "parse_markdown",
    "read_rfc",
    "require_docs_repo",
    "rfc_dir",
    "rfc_image_path",
]
