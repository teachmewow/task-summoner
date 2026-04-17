"""Tests for the shared utils helpers (fs, subprocess, paths)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from task_summoner.utils import (
    atomic_write,
    atomic_write_json,
    expand,
    run_cli,
    safe_load_json,
)


class TestAtomicWrite:
    def test_creates_file_with_content(self, tmp_path: Path):
        target = tmp_path / "out.txt"
        atomic_write(target, "hello")
        assert target.read_text() == "hello"

    def test_creates_parent_dirs(self, tmp_path: Path):
        target = tmp_path / "nested" / "deep" / "out.txt"
        atomic_write(target, "x")
        assert target.read_text() == "x"

    def test_overwrites_existing_file(self, tmp_path: Path):
        target = tmp_path / "out.txt"
        target.write_text("old")
        atomic_write(target, "new")
        assert target.read_text() == "new"

    def test_leaves_no_tmp_file_behind(self, tmp_path: Path):
        atomic_write(tmp_path / "out.txt", "x")
        leftovers = [p for p in tmp_path.iterdir() if p.suffix == ".tmp"]
        assert leftovers == []

    def test_accepts_str_path(self, tmp_path: Path):
        target = str(tmp_path / "out.txt")
        atomic_write(target, "hi")
        assert Path(target).read_text() == "hi"


class TestAtomicWriteJson:
    def test_writes_dict_as_json(self, tmp_path: Path):
        target = tmp_path / "out.json"
        atomic_write_json(target, {"a": 1, "b": [2, 3]})
        assert json.loads(target.read_text()) == {"a": 1, "b": [2, 3]}

    def test_uses_indent(self, tmp_path: Path):
        target = tmp_path / "out.json"
        atomic_write_json(target, {"a": 1}, indent=4)
        assert "    " in target.read_text()


class TestSafeLoadJson:
    def test_returns_data_on_valid_json(self, tmp_path: Path):
        target = tmp_path / "in.json"
        target.write_text('{"k": "v"}')
        assert safe_load_json(target) == {"k": "v"}

    def test_returns_none_when_missing(self, tmp_path: Path):
        assert safe_load_json(tmp_path / "nope.json") is None

    def test_returns_none_on_corrupt_json(self, tmp_path: Path):
        target = tmp_path / "bad.json"
        target.write_text("{not json")
        assert safe_load_json(target) is None


class TestExpand:
    def test_expands_tilde(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("HOME", "/tmp/fakehome")
        assert expand("~/foo") == "/tmp/fakehome/foo"

    def test_passthrough_absolute(self):
        assert expand("/etc/hosts") == "/etc/hosts"


class TestRunCli:
    @pytest.mark.asyncio
    async def test_returns_stdout_on_success(self):
        out = await run_cli(["echo", "hello"], timeout_sec=5)
        assert out.strip() == "hello"

    @pytest.mark.asyncio
    async def test_raises_on_nonzero_exit(self):
        with pytest.raises(RuntimeError, match="exit 1"):
            await run_cli(["sh", "-c", "exit 1"], timeout_sec=5)

    @pytest.mark.asyncio
    async def test_raises_on_timeout(self):
        with pytest.raises(RuntimeError, match="timed out"):
            await run_cli(["sleep", "5"], timeout_sec=1)

    @pytest.mark.asyncio
    async def test_forwards_env(self):
        out = await run_cli(
            ["sh", "-c", "echo $MY_VAR"],
            timeout_sec=5,
            env={**os.environ, "MY_VAR": "xyz"},
        )
        assert out.strip() == "xyz"

    @pytest.mark.asyncio
    async def test_captures_stderr_in_error_message(self):
        with pytest.raises(RuntimeError, match="boom"):
            await run_cli(["sh", "-c", "echo boom >&2; exit 2"], timeout_sec=5)
