"""ENG-116: shutdown behavior for `task-summoner run` and `run --dev`.

Covers:
- ``_HardExitGuard`` timer logic — arms on SIGINT, disarmed on healthy exit.
- Orchestrator's new ``install_signal_handlers=False`` path (no loop.add_signal_handler
  clobbering uvicorn's handler).
- End-to-end: spawn ``python -m task_summoner run --dev`` as a real subprocess,
  send SIGINT, assert the process exits within the safety-net budget. This is
  the regression that ENG-112 missed — unit tests stub out uvicorn, so they
  couldn't observe the signal-handler clobber.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from task_summoner.cli import _HardExitGuard
from task_summoner.config import TaskSummonerConfig
from task_summoner.runtime import Orchestrator


class TestHardExitGuard:
    """The safety net that force-exits if graceful shutdown stalls past budget."""

    def test_disarm_before_sigint_is_noop(self):
        """If we never see a signal, disarm() must be cheap and leave no timer."""
        guard = _HardExitGuard(budget_sec=15.0)
        guard.arm_on_sigint()
        # Immediately disarm — no timer was started yet.
        guard.disarm()
        assert guard._timer is None

    def test_sigint_schedules_timer_but_disarm_cancels_it(self):
        """The timer is armed on SIGINT; disarm() cancels before it fires."""
        guard = _HardExitGuard(budget_sec=15.0)
        # Override the previous handler so chaining does NOT raise KeyboardInterrupt
        # inside pytest — we want to verify timer lifecycle in isolation.
        guard._prev_handler = MagicMock()
        guard._installed = True

        with patch("os._exit") as mock_exit:
            guard._on_sigint(signal.SIGINT, None)
            assert guard._timer is not None
            assert guard._timer.is_alive()

            guard.disarm()

            # Timer must have been cancelled; it must NEVER call os._exit.
            time.sleep(0.05)
            mock_exit.assert_not_called()

    def test_second_sigint_does_not_rearm(self):
        """A second SIGINT must not reset the countdown — the deadline is absolute."""
        guard = _HardExitGuard(budget_sec=15.0)
        guard._prev_handler = MagicMock()
        guard._installed = True

        guard._on_sigint(signal.SIGINT, None)
        first_timer = guard._timer
        guard._on_sigint(signal.SIGINT, None)
        second_timer = guard._timer

        assert first_timer is second_timer
        guard.disarm()

    def test_chains_to_previous_handler(self):
        """SIGINT pre-handler must delegate to the handler that was in place.

        This is what lets uvicorn continue owning SIGINT: our guard just
        arms a timer then forwards the signal.
        """
        guard = _HardExitGuard(budget_sec=15.0)
        prev = MagicMock()
        guard._prev_handler = prev
        guard._installed = True

        guard._on_sigint(signal.SIGINT, None)

        prev.assert_called_once()
        # Cleanup — stop the timer we just started.
        guard.disarm()

    def test_non_main_thread_install_degrades_gracefully(self, monkeypatch):
        """signal.signal() on a non-main thread raises — we must log and carry on."""
        import threading as th

        fake_thread = MagicMock()
        monkeypatch.setattr(th, "main_thread", lambda: fake_thread)
        # current_thread() returns the real current thread, which is != fake_thread.

        guard = _HardExitGuard(budget_sec=15.0)
        guard.arm_on_sigint()

        # Nothing installed.
        assert guard._installed is False
        guard.disarm()

    def test_hard_exit_calls_os_exit(self):
        """_hard_exit must be os._exit(1) — not SystemExit, not sys.exit."""
        guard = _HardExitGuard(budget_sec=0.01)

        with patch("os._exit") as mock_exit:
            guard._hard_exit()
            mock_exit.assert_called_once_with(1)


class TestOrchestratorNoSignalHandlerInstall:
    """ENG-116 root cause: orchestrator must not install SIGINT under uvicorn."""

    @pytest.fixture
    def orchestrator(self, config: TaskSummonerConfig, monkeypatch) -> Orchestrator:
        from task_summoner.providers.agent import AgentProviderFactory
        from task_summoner.providers.board import BoardProviderFactory

        monkeypatch.setattr(BoardProviderFactory, "create", staticmethod(lambda _cfg: AsyncMock()))
        monkeypatch.setattr(AgentProviderFactory, "create", staticmethod(lambda _cfg: AsyncMock()))
        orch = Orchestrator(config)
        orch._sync.discover = AsyncMock(return_value=[])  # type: ignore[assignment]
        orch._dispatcher.dispatch_all = AsyncMock()  # type: ignore[assignment]
        return orch

    @pytest.mark.asyncio
    async def test_install_false_skips_add_signal_handler(self, orchestrator, monkeypatch):
        """When install_signal_handlers=False, we must NOT touch loop signals.

        Concretely: ``loop.add_signal_handler`` must never be called. This is
        the exact behavior that makes uvicorn's ``signal.signal``-based
        handler survive, so SIGINT reaches uvicorn's graceful-shutdown path.
        """
        import asyncio

        loop = asyncio.get_running_loop()
        with patch.object(loop, "add_signal_handler") as mock_add:
            task = asyncio.create_task(orchestrator.run(install_signal_handlers=False))
            await asyncio.sleep(0.05)  # let it enter the loop
            orchestrator._shutdown_event.set()
            await asyncio.wait_for(task, timeout=5)

            mock_add.assert_not_called()

    @pytest.mark.asyncio
    async def test_install_true_still_wires_signals(self, orchestrator):
        """Default install_signal_handlers=True preserves pre-ENG-116 behavior."""
        import asyncio

        loop = asyncio.get_running_loop()
        with patch.object(loop, "add_signal_handler") as mock_add:
            task = asyncio.create_task(orchestrator.run(install_signal_handlers=True))
            await asyncio.sleep(0.05)
            orchestrator._shutdown_event.set()
            await asyncio.wait_for(task, timeout=5)

            # SIGINT + SIGTERM both hooked.
            sigs_seen = {call.args[0] for call in mock_add.call_args_list}
            assert signal.SIGINT in sigs_seen
            assert signal.SIGTERM in sigs_seen


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals only")
class TestRunCliSigintExits:
    """Integration: real ``python -m task_summoner run`` must exit on SIGINT.

    This is the regression the ENG-112 unit tests couldn't catch — they never
    exercised uvicorn. Here we spawn the real CLI in a subprocess, send SIGINT,
    and assert ``proc.wait(timeout=...)`` returns within the hard-exit budget.
    No sleeps, no polling — ``proc.wait`` with a timeout is the determinism.
    """

    @pytest.fixture
    def minimal_config_path(self, tmp_path: Path) -> Path:
        """Write a deliberately-invalid config so the orchestrator does not
        actually start — we only need uvicorn + the lifespan + the CLI wrapper.
        The UI/setup endpoint still serves, which is what `cmd_run` needs.
        """
        cfg = tmp_path / "config.yaml"
        cfg.write_text("# empty — triggers the 'visit /setup' path\n")
        return cfg

    def test_sigint_exits_within_budget(self, tmp_path: Path, minimal_config_path: Path):
        """End-to-end: spawn the CLI, send SIGINT, expect exit within 15s."""
        # Pick an unlikely-to-be-bound port so parallel test runs don't collide.
        port = 8765 + (os.getpid() % 200)

        # Launch `python -m task_summoner run` (no --dev: avoids pnpm dependency).
        proc = subprocess.Popen(
            [
                sys.executable,
                "-c",
                textwrap.dedent(
                    f"""
                    import asyncio
                    from pathlib import Path
                    from task_summoner.cli import cmd_run
                    asyncio.run(cmd_run({str(minimal_config_path)!r}, port={port}, dev=False))
                    """
                ),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            # New process group — isolates our SIGINT from the pytest runner.
            start_new_session=True,
        )

        try:
            # Wait for uvicorn to bind. We poll stdout for the "running" line
            # with a bounded budget — no sleep loops.
            deadline = time.monotonic() + 10.0
            started = False
            buf = b""
            assert proc.stdout is not None
            while time.monotonic() < deadline and not started:
                line = proc.stdout.readline()
                if not line:
                    break
                buf += line
                if b"Uvicorn running" in line or b"Task Summoner" in line:
                    started = True

            assert started, f"CLI didn't start within 10s. Output:\n{buf.decode(errors='replace')}"

            # Send SIGINT to the subprocess's process group.
            os.killpg(os.getpgid(proc.pid), signal.SIGINT)

            # proc.wait with timeout is the deterministic exit-within-budget check.
            # Budget: _HARD_EXIT_BUDGET_SEC (15s) + a little slack for subprocess
            # wrapper overhead.
            exit_code = proc.wait(timeout=20)

            # Either a clean exit (0), a SIGINT propagated exit (-SIGINT or 130),
            # or the hard-exit safety net (1). Any of those count as "did exit".
            assert exit_code is not None
            # Hanging-forever fails by raising TimeoutExpired above.
        finally:
            if proc.poll() is None:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.wait(timeout=5)
