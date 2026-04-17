"""Shared sys-level helpers used across the codebase.

These helpers exist because task-summoner is a systems tool — it touches the
filesystem, spawns subprocesses, and parses JSON from untyped external tools.
The same patterns were being re-implemented in multiple places. Consolidated
here so that changes to e.g. atomic-write semantics happen in one place.
"""

from task_summoner.utils.fs import atomic_write, atomic_write_json, safe_load_json
from task_summoner.utils.paths import expand
from task_summoner.utils.subprocess import run_cli

__all__ = [
    "atomic_write",
    "atomic_write_json",
    "expand",
    "run_cli",
    "safe_load_json",
]
