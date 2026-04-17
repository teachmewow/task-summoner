"""Tests for `task-summoner clean` — stale ticket cleanup."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from task_summoner.cli import _find_stale_tickets, cmd_clean
from task_summoner.core import StateStore
from task_summoner.models import TicketContext, TicketState
from task_summoner.providers.board import BoardNotFoundError


@pytest.fixture
def populated_store(tmp_path: Path) -> StateStore:
    store = StateStore(tmp_path / "artifacts")
    store.save(TicketContext(ticket_key="LIVE-1", state=TicketState.QUEUED))
    store.save(TicketContext(ticket_key="GONE-1", state=TicketState.QUEUED))
    store.save(TicketContext(ticket_key="GONE-2", state=TicketState.FAILED))
    return store


def _make_board(not_found_keys: set[str]) -> AsyncMock:
    board = AsyncMock()

    async def fetch(ticket_id: str):
        if ticket_id in not_found_keys:
            raise BoardNotFoundError(f"{ticket_id} not found")
        return object()  # the value doesn't matter for these tests

    board.fetch_ticket.side_effect = fetch
    return board


class TestFindStaleTickets:
    async def test_returns_contexts_that_404(self, populated_store: StateStore):
        board = _make_board({"GONE-1", "GONE-2"})
        contexts = populated_store.list_all()

        stale = await _find_stale_tickets(board, contexts)
        keys = {c.ticket_key for c in stale}
        assert keys == {"GONE-1", "GONE-2"}

    async def test_skips_transient_errors(self, populated_store: StateStore):
        board = AsyncMock()

        async def fetch(ticket_id: str):
            raise RuntimeError("network timeout")

        board.fetch_ticket.side_effect = fetch
        contexts = populated_store.list_all()

        stale = await _find_stale_tickets(board, contexts)
        assert stale == []


class TestCmdClean:
    def _write_config(self, tmp_path: Path, store: StateStore) -> Path:
        content = f"""
providers:
  board:
    type: linear
    linear:
      api_key: k
      team_id: t
  agent:
    type: claude_code
    claude_code:
      api_key: ak

repos:
  demo: "{tmp_path}"

default_repo: demo
artifacts_dir: "{store._root}"
workspace_root: "{tmp_path}/ws"
"""
        path = tmp_path / "config.yaml"
        path.write_text(content)
        return path

    def test_dry_run_does_not_delete(self, tmp_path: Path, populated_store: StateStore, capsys):
        config_path = self._write_config(tmp_path, populated_store)
        board = _make_board({"GONE-1"})

        with patch("task_summoner.cli.BoardProviderFactory.create", return_value=board):
            cmd_clean(str(config_path), dry_run=True, force=False)

        assert populated_store.load("GONE-1") is not None
        assert "--dry-run" in capsys.readouterr().out

    def test_force_removes_stale(self, tmp_path: Path, populated_store: StateStore, capsys):
        config_path = self._write_config(tmp_path, populated_store)
        board = _make_board({"GONE-1", "GONE-2"})

        with patch("task_summoner.cli.BoardProviderFactory.create", return_value=board):
            cmd_clean(str(config_path), dry_run=False, force=True)

        assert populated_store.load("GONE-1") is None
        assert populated_store.load("GONE-2") is None
        assert populated_store.load("LIVE-1") is not None
        assert "Removed 2" in capsys.readouterr().out

    def test_noop_when_all_reachable(self, tmp_path: Path, populated_store: StateStore, capsys):
        config_path = self._write_config(tmp_path, populated_store)
        board = _make_board(set())

        with patch("task_summoner.cli.BoardProviderFactory.create", return_value=board):
            cmd_clean(str(config_path), dry_run=False, force=True)

        assert "Nothing to clean" in capsys.readouterr().out
