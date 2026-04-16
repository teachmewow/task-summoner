"""Enforce the provider abstraction boundary.

Core, states, runtime, and models must never import from concrete provider
implementations (jira, linear, claude_code, codex, claude_agent_sdk).
They may only import from the protocol and config modules.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_SRC_ROOT = Path(__file__).resolve().parents[1] / "src" / "task_summoner"

_FORBIDDEN_PREFIXES = (
    "task_summoner.providers.board.jira",
    "task_summoner.providers.board.linear",
    "task_summoner.providers.agent.claude_code",
    "task_summoner.providers.agent.codex",
    "claude_agent_sdk",
)

_GUARDED_DIRECTORIES = ("core", "states", "runtime", "models")

_ALLOWED_ENTRY_POINTS = {"config.py"}


def _collect_imports(py_path: Path) -> list[str]:
    tree = ast.parse(py_path.read_text(), filename=str(py_path))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports


def _py_files() -> list[Path]:
    files: list[Path] = []
    for directory in _GUARDED_DIRECTORIES:
        base = _SRC_ROOT / directory
        if not base.exists():
            continue
        files.extend(p for p in base.rglob("*.py") if "__pycache__" not in p.parts)
    return files


@pytest.mark.parametrize("py_path", _py_files(), ids=lambda p: str(p.relative_to(_SRC_ROOT)))
def test_no_provider_imports_in_core_layers(py_path: Path) -> None:
    """Files under core/ states/ runtime/ models/ must not import concrete providers."""
    imports = _collect_imports(py_path)
    violations = [
        imp
        for imp in imports
        if any(imp.startswith(prefix) for prefix in _FORBIDDEN_PREFIXES)
    ]
    assert not violations, (
        f"{py_path.relative_to(_SRC_ROOT)} imports forbidden provider modules: "
        f"{violations}. Use providers.board.protocol or providers.agent.protocol."
    )
