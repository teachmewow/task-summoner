"""Async subprocess runner — the shared wrapper around `asyncio.create_subprocess_exec`.

Consolidates the subprocess pattern used by the Jira adapter (`acli`) and the git
workspace manager. Both need timeout, stderr capture, and consistent error shapes.
"""

from __future__ import annotations

import asyncio

import structlog

log = structlog.get_logger()


async def run_cli(
    cmd: list[str],
    *,
    timeout_sec: int,
    env: dict[str, str] | None = None,
) -> str:
    """Execute `cmd`, return stdout. Raises `RuntimeError` on timeout or non-zero exit.

    Stdout is returned as-is (not stripped). Callers that need a trimmed string
    should call `.strip()` themselves.
    """
    log.debug("Running subprocess", cmd=" ".join(cmd))

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
    except TimeoutError as e:
        proc.kill()
        raise RuntimeError(f"Subprocess timed out after {timeout_sec}s: {' '.join(cmd)}") from e

    if proc.returncode != 0:
        err = stderr.decode().strip()
        raise RuntimeError(f"Subprocess failed (exit {proc.returncode}): {err}")

    return stdout.decode()
