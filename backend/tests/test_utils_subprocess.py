"""Tests for `run_cli` — env-merge semantics are the critical contract."""

from __future__ import annotations

import os

import pytest

from task_summoner.utils.subprocess import run_cli


@pytest.mark.asyncio
async def test_env_none_inherits_parent_env():
    """`env=None` passes None to create_subprocess_exec, which inherits parent env.

    Concretely: the subprocess can find binaries available on the parent's PATH.
    We use /usr/bin/env to print PATH and confirm it's non-empty.
    """
    stdout = await run_cli(
        ["/bin/sh", "-c", "echo $PATH"],
        timeout_sec=5,
    )
    assert stdout.strip(), "PATH should be inherited"


@pytest.mark.asyncio
async def test_env_dict_is_merged_not_replaced():
    """Passing `env={'FOO': 'bar'}` must NOT strip PATH from the subprocess.

    This is the regression test for ENG-117 — previously the `env` arg was
    forwarded raw to create_subprocess_exec, which replaces the parent env
    wholesale, so PATH disappeared and tools like `gh` stopped resolving.
    """
    stdout = await run_cli(
        ["/bin/sh", "-c", "echo FOO=$FOO:PATH=$PATH"],
        timeout_sec=5,
        env={"FOO": "bar"},
    )
    line = stdout.strip()
    assert "FOO=bar" in line, "override should be applied"
    # PATH from os.environ must be preserved.
    path_from_env = os.environ.get("PATH", "")
    assert path_from_env, "test precondition: parent must have PATH"
    assert path_from_env in line, "parent PATH must be merged into subprocess env"


@pytest.mark.asyncio
async def test_env_dict_override_wins_over_parent():
    """When a key collides, the passed override wins."""
    existing = os.environ.get("HOME", "/home/ignored")
    assert existing  # precondition
    stdout = await run_cli(
        ["/bin/sh", "-c", "echo $HOME"],
        timeout_sec=5,
        env={"HOME": "/tmp/overridden"},
    )
    assert stdout.strip() == "/tmp/overridden"
