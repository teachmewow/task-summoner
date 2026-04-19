"""CLI command implementations."""

from __future__ import annotations

import asyncio
import os
import shutil
import signal
import subprocess
import threading
from pathlib import Path

import structlog
import uvicorn

from task_summoner.api.app import create_app
from task_summoner.config import TaskSummonerConfig
from task_summoner.core import StateStore
from task_summoner.models import TicketContext
from task_summoner.providers.board import (
    BoardNotFoundError,
    BoardProvider,
    BoardProviderFactory,
)
from task_summoner.setup_wizard import run_wizard

log = structlog.get_logger()

_WEB_DIST = Path(__file__).resolve().parent / "web_dist"
_FRONTEND_DIR = Path(__file__).resolve().parents[3] / "frontend"

# ENG-116: safety-net budget. If uvicorn + lifespan shutdown doesn't finish in
# this many seconds after the first SIGINT, we hard-exit via os._exit(1).
# Uvicorn's own timeout_graceful_shutdown is 10s, the lifespan hook is 8s —
# 15s leaves a 5s slack for everything to unwind before the hard exit fires.
_HARD_EXIT_BUDGET_SEC = 15.0


async def cmd_run(config_path: str, port: int = 8420, dev: bool = False) -> None:
    """Start the FastAPI app. With --dev, also spawn the vite dev server on :5173."""
    path = Path(config_path)
    if not path.exists():
        log.info("No config found — open /setup in the browser", path=config_path)

    if not dev and not (_WEB_DIST / "index.html").is_file():
        log.error(
            "Frontend bundle not found. "
            "Run `pnpm build` in frontend/ or start with `task-summoner run --dev`.",
            web_dist=str(_WEB_DIST),
        )
        raise SystemExit(1)

    vite_proc: subprocess.Popen | None = None
    if dev:
        vite_proc = _spawn_vite()

    # ENG-116: arm the hard-exit safety net. The Timer only fires if the
    # clean shutdown path (uvicorn → lifespan → orchestrator.stop → vite
    # cleanup) hasn't completed within _HARD_EXIT_BUDGET_SEC of the first
    # SIGINT. On a healthy exit we cancel the timer before it ever runs.
    hard_exit_timer = _HardExitGuard(budget_sec=_HARD_EXIT_BUDGET_SEC)
    hard_exit_timer.arm_on_sigint()

    try:
        app = create_app(config_path=path)
        # `timeout_graceful_shutdown` puts a hard upper bound on Ctrl+C
        # handling: uvicorn closes the listening socket, runs the lifespan
        # shutdown hook (which in turn awaits Orchestrator.stop with its own
        # bounded timeout), and force-exits at 10s — never hangs. See
        # ENG-112 and ENG-116.
        server = uvicorn.Server(
            uvicorn.Config(
                app,
                host="0.0.0.0",
                port=port,
                log_level="warning",
                timeout_graceful_shutdown=10,
            )
        )
        if dev:
            log.info(
                "Task Summoner dev mode", api=f"http://localhost:{port}", ui="http://localhost:5173"
            )
        else:
            log.info("Task Summoner running", url=f"http://localhost:{port}")
        await server.serve()
    finally:
        log.info("Shutting down CLI wrapper", dev=dev)
        if vite_proc is not None:
            _terminate_vite(vite_proc)
        # Healthy exit path — disarm the safety net.
        hard_exit_timer.disarm()


def _terminate_vite(proc: subprocess.Popen) -> None:
    """Kill the vite dev server AND its children.

    ENG-116: ``pnpm dev`` spawns vite as a child; terminating only the pnpm
    wrapper can orphan vite. We put vite in its own process group at spawn
    time (via ``start_new_session=True``) and here we signal the whole
    group so every descendant receives SIGTERM / SIGKILL.
    """
    try:
        pgid = os.getpgid(proc.pid)
    except (ProcessLookupError, OSError):
        # Process already gone.
        return

    log.info("Terminating vite process group", pgid=pgid)
    try:
        os.killpg(pgid, signal.SIGTERM)
    except (ProcessLookupError, OSError) as e:
        log.debug("vite process group already exited", error=str(e))
        return

    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        log.warning("vite didn't exit within 5s, sending SIGKILL", pgid=pgid)
        try:
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, OSError):
            pass
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            log.error("vite refused SIGKILL — abandoning", pgid=pgid)


def _spawn_vite() -> subprocess.Popen:
    if not _FRONTEND_DIR.is_dir():
        log.error("frontend/ directory not found", path=str(_FRONTEND_DIR))
        raise SystemExit(1)
    pnpm = shutil.which("pnpm")
    if pnpm is None:
        log.error("pnpm not found on PATH — install it to use --dev")
        raise SystemExit(1)
    log.info("Starting vite dev server", cwd=str(_FRONTEND_DIR))
    # ENG-116: start_new_session=True puts vite (and its children) in a new
    # process group so we can signal them all at once on shutdown.
    return subprocess.Popen(
        [pnpm, "dev"],
        cwd=_FRONTEND_DIR,
        start_new_session=True,
    )


class _HardExitGuard:
    """Arms a threading.Timer on the first SIGINT to force-exit if shutdown stalls.

    ENG-116: the healthy path is

        SIGINT -> uvicorn.handle_exit -> main_loop exits
               -> lifespan finalizer -> orchestrator.stop()
               -> vite terminated -> cmd_run returns -> asyncio.run unwinds.

    If anything in that chain hangs (stuck agent subprocess, deadlocked
    generator, kernel-level pipe waiter), this guard calls ``os._exit(1)``
    at ``budget_sec``. On a healthy exit we ``disarm()`` before the timer
    fires, so it's only visible when the process was actually stuck.
    """

    def __init__(self, *, budget_sec: float) -> None:
        self._budget_sec = budget_sec
        self._timer: threading.Timer | None = None
        self._prev_handler: signal.Handlers | None = None
        self._installed = False

    def arm_on_sigint(self) -> None:
        """Install a SIGINT pre-handler that starts the hard-exit countdown.

        Signal handlers can only be installed from the main thread. Pytest
        sometimes runs the CLI off the main thread — degrade gracefully.
        """
        if threading.current_thread() is not threading.main_thread():
            log.debug("Hard-exit guard skipped — not main thread")
            return
        try:
            self._prev_handler = signal.signal(signal.SIGINT, self._on_sigint)
            self._installed = True
            log.debug("Hard-exit guard armed", budget_sec=self._budget_sec)
        except (ValueError, OSError) as e:
            log.debug("Hard-exit guard install failed", error=str(e))

    def disarm(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        if self._installed and self._prev_handler is not None:
            try:
                signal.signal(signal.SIGINT, self._prev_handler)
            except (ValueError, OSError):
                pass
        self._installed = False

    def _on_sigint(self, signum: int, frame) -> None:  # type: ignore[no-untyped-def]
        # Re-raise to uvicorn / whoever owns SIGINT by chaining to the
        # previous handler. We only schedule the timer on the FIRST SIGINT.
        if self._timer is None:
            log.warning(
                "SIGINT received — arming hard-exit safety net",
                budget_sec=self._budget_sec,
            )
            self._timer = threading.Timer(self._budget_sec, self._hard_exit)
            self._timer.daemon = True
            self._timer.start()
        prev = self._prev_handler
        if callable(prev):
            prev(signum, frame)
        elif prev == signal.SIG_DFL:
            # Restore default handler and re-raise so the default action
            # (process termination) still happens for subsequent signals.
            signal.signal(signum, signal.SIG_DFL)
            signal.raise_signal(signum)

    def _hard_exit(self) -> None:
        # Using os._exit to skip at-exit hooks — they're probably what stalled.
        log.error(
            "Shutdown exceeded hard-exit budget — forcing process termination",
            budget_sec=self._budget_sec,
        )
        os._exit(1)


def cmd_setup(config_path: str) -> None:
    """Launch the interactive setup wizard to create or overwrite config.yaml."""
    run_wizard(Path(config_path))


def cmd_status(config_path: str) -> None:
    """Show all tracked tickets and their states."""
    config = TaskSummonerConfig.load(config_path)
    store = StateStore(config.artifacts_dir)

    contexts = store.list_all()
    if not contexts:
        print("No tracked tickets.")
        return

    print(f"{'TICKET':<16} {'STATE':<16} {'COST':>8} {'RETRIES':>8} {'UPDATED'}")
    print("-" * 72)
    for ctx in sorted(contexts, key=lambda c: c.updated_at, reverse=True):
        print(
            f"{ctx.ticket_key:<16} {ctx.state.value:<16} "
            f"${ctx.total_cost_usd:>6.2f} {ctx.retry_count:>8} "
            f"{ctx.updated_at[:19]}"
        )
        if ctx.error:
            print(f"  ERROR: {ctx.error}")
        if ctx.mr_url:
            print(f"  MR: {ctx.mr_url}")


def cmd_clean(config_path: str, *, dry_run: bool = False, force: bool = False) -> None:
    """Remove local state for tickets that no longer exist on the current board."""
    config = TaskSummonerConfig.load(config_path)
    store = StateStore(config.artifacts_dir)
    board = BoardProviderFactory.create(config.build_provider_config())

    contexts = store.list_all()
    if not contexts:
        print("No tracked tickets.")
        return

    print(f"Scanning {len(contexts)} local tickets against the board...")
    stale = asyncio.run(_find_stale_tickets(board, contexts))

    if not stale:
        print("All tracked tickets are reachable on the board. Nothing to clean.")
        return

    print(f"\nFound {len(stale)} ticket(s) not reachable on the current board:")
    for ctx in stale:
        marker = " (already quarantined)" if ctx.state.value == "FAILED" else ""
        print(f"  - {ctx.ticket_key:<16} state={ctx.state.value}{marker}")

    if dry_run:
        print("\n--dry-run: no files were removed.")
        return

    if not force:
        try:
            answer = input("\nRemove all? [y/N]: ").strip().lower()
        except EOFError:
            answer = ""
        if answer not in ("y", "yes"):
            print("Cancelled.")
            return

    for ctx in stale:
        store.delete(ctx.ticket_key)
    print(f"Removed {len(stale)} ticket(s).")


async def _find_stale_tickets(
    board: BoardProvider, contexts: list[TicketContext]
) -> list[TicketContext]:
    stale: list[TicketContext] = []
    for ctx in contexts:
        try:
            await board.fetch_ticket(ctx.ticket_key)
        except BoardNotFoundError:
            stale.append(ctx)
        except Exception as e:
            log.warning(
                "Skipping ticket during scan (transient error)",
                ticket=ctx.ticket_key,
                error=str(e),
            )
    return stale
