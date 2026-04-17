"""Tests for CLI entry point and commands."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from task_summoner.__main__ import main
from task_summoner.cli import cmd_run, cmd_status
from task_summoner.core import StateStore
from task_summoner.models import TicketContext, TicketState


class TestCmdStatus:
    def test_empty(self, config, capsys):
        with patch("task_summoner.cli.TaskSummonerConfig.load", return_value=config):
            cmd_status("config.yaml")

        captured = capsys.readouterr()
        assert "No tracked tickets" in captured.out

    def test_with_tickets(self, config, capsys):
        store = StateStore(config.artifacts_dir)
        store.save(TicketContext(ticket_key="LLMOPS-1", state=TicketState.PLANNING))
        store.save(TicketContext(ticket_key="LLMOPS-2", state=TicketState.DONE, total_cost_usd=5.0))
        store.save(
            TicketContext(
                ticket_key="LLMOPS-3",
                state=TicketState.FAILED,
                error="SDK error",
                mr_url="https://gitlab.com/-/merge_requests/1",
            )
        )

        with patch("task_summoner.cli.TaskSummonerConfig.load", return_value=config):
            cmd_status("config.yaml")

        captured = capsys.readouterr()
        assert "LLMOPS-1" in captured.out
        assert "PLANNING" in captured.out
        assert "LLMOPS-2" in captured.out
        assert "$" in captured.out
        assert "SDK error" in captured.out
        assert "merge_requests" in captured.out


class TestCmdRun:
    async def test_validation_failure_exits(self, config):
        old = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            with patch("task_summoner.cli.TaskSummonerConfig.load", return_value=config):
                with pytest.raises(SystemExit):
                    await cmd_run("config.yaml")
        finally:
            if old:
                os.environ["ANTHROPIC_API_KEY"] = old


class TestMainEntryPoint:
    def test_no_args_prints_help(self, capsys):
        with pytest.raises(SystemExit):
            main()

    def test_status_command(self, config, capsys):
        with patch("sys.argv", ["task-summoner", "status", "-c", "config.yaml"]):
            with patch("task_summoner.cli.TaskSummonerConfig.load", return_value=config):
                main()

        captured = capsys.readouterr()
        assert "No tracked tickets" in captured.out
