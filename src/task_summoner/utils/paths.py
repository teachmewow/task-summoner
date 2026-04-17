"""Path helpers."""

from __future__ import annotations

from pathlib import Path


def expand(path: str) -> str:
    """Expand `~` in a path and return an absolute string."""
    return str(Path(path).expanduser())
