"""Detect whether the local machine has a Claude Code session logged in.

Used by the config validation + setup wizard to decide whether the user can
use `auth_method=personal_session`. The check is intentionally cheap and
best-effort — we look for filesystem artifacts that Claude Code creates on
first login. We do NOT hit the Anthropic API.
"""

from __future__ import annotations

from pathlib import Path

_DEFAULT_CLAUDE_HOME = Path.home() / ".claude"


def claude_code_session_available(claude_home: Path | None = None) -> bool:
    """Return True if Claude Code appears to be logged in on this machine.

    Heuristic: `~/.claude/` exists and contains at least one of the artifacts
    Claude Code writes on login (`projects/`, `history.jsonl`). Doesn't
    guarantee the session is still valid — the real validation happens when
    the agent spawns and fails to auth.
    """
    home = claude_home or _DEFAULT_CLAUDE_HOME
    if not home.is_dir():
        return False

    markers = [home / "projects", home / "history.jsonl"]
    return any(marker.exists() for marker in markers)
