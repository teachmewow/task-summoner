"""Filesystem helpers: atomic writes + safe JSON loads."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger()


def atomic_write(path: Path | str, content: str) -> None:
    """Write `content` to `path` atomically (tmp + rename).

    Crashes mid-write leave either the old file untouched or the new file
    complete — never a half-written file.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
    try:
        os.write(fd, content.encode())
        os.close(fd)
        os.rename(tmp_path, target)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def atomic_write_json(path: Path | str, data: Any, *, indent: int = 2) -> None:
    """Serialize `data` to JSON and write it atomically."""
    atomic_write(path, json.dumps(data, indent=indent))


def safe_load_json(path: Path | str) -> Any:
    """Load JSON from `path`. Returns None on missing file or decode error.

    Logs a warning on decode errors so callers can detect corruption without
    catching exceptions themselves. Missing file is expected (no warning).
    """
    target = Path(path)
    if not target.exists():
        return None
    try:
        return json.loads(target.read_text())
    except (json.JSONDecodeError, OSError) as e:
        log.warning("Failed to load JSON", path=str(target), error=str(e))
        return None
