"""Orchestrator — slim polling loop that coordinates sync and dispatch.

Wires services via provider factories — no direct imports of Jira or
Claude Code. Current provider (Jira + Claude Code) is derived from the
legacy TaskSummonerConfig; M5 will introduce the full provider-agnostic
config schema.
"""

from __future__ import annotations

import asyncio
import signal

import structlog

from task_summoner.config import TaskSummonerConfig
from task_summoner.core import StateStore
from task_summoner.events.bus import EventBus
from task_summoner.providers.agent import AgentProviderFactory
from task_summoner.providers.board import BoardProviderFactory
from task_summoner.runtime.dispatcher import TaskDispatcher
from task_summoner.runtime.sync import BoardSyncService
from task_summoner.states import StateServices, build_state_registry
from task_summoner.workspace import GitWorkspaceManager

log = structlog.get_logger()


class Orchestrator:
    def __init__(
        self,
        config: TaskSummonerConfig,
        event_bus: EventBus | None = None,
    ) -> None:
        self._config = config
        self._bus = event_bus or EventBus()

        provider_config = config.build_provider_config()
        board = BoardProviderFactory.create(provider_config)
        agent = AgentProviderFactory.create(provider_config)

        store = StateStore(config.artifacts_dir)
        workspace = GitWorkspaceManager(config)

        services = StateServices(
            board=board,
            workspace=workspace,
            agent=agent,
            store=store,
        )

        self._sync = BoardSyncService(board=board, store=store, bus=self._bus)
        self._dispatcher = TaskDispatcher(
            states=build_state_registry(config),
            services=services,
            store=store,
            board=board,
            bus=self._bus,
        )
        self._store = store
        self._shutdown_event = asyncio.Event()

    @property
    def event_bus(self) -> EventBus:
        return self._bus

    @property
    def store(self) -> StateStore:
        return self._store

    async def run(self, *, install_signal_handlers: bool = True) -> None:
        """Drive the polling loop.

        Signal handling (ENG-116): by default we install handlers for
        SIGINT/SIGTERM so that running the orchestrator standalone (e.g.
        from a pytest harness) responds to Ctrl+C. When embedded inside
        uvicorn's lifespan (the normal CLI path), the caller MUST pass
        ``install_signal_handlers=False`` because uvicorn installs its own
        ``signal.signal`` handler first, and ``loop.add_signal_handler``
        silently overwrites it — breaking uvicorn's own graceful-shutdown
        path and causing ``task-summoner run --dev`` to hang on Ctrl+C.
        When uvicorn owns SIGINT, it triggers the FastAPI lifespan
        finalizer, which calls ``stop()`` explicitly.
        """
        log.info(
            "Task Summoner starting",
            poll_interval=self._config.poll_interval_sec,
            repos=list(self._config.repos.keys()),
            install_signal_handlers=install_signal_handlers,
        )

        if install_signal_handlers:
            self._install_signal_handlers()

        await asyncio.sleep(0.5)

        while not self._shutdown_event.is_set():
            try:
                active = await self._sync.discover()
                await self._dispatcher.dispatch_all(active)
            except Exception:
                log.exception("Poll cycle error")

            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=self._config.poll_interval_sec,
                )
            except TimeoutError:
                pass

        log.info("Shutting down, waiting for agents...")
        await self.stop()
        log.info("Shutdown complete")

    async def stop(self, *, timeout: float = 10.0) -> None:
        """Cleanly stop the orchestrator: set shutdown flag, drain running tasks.

        Idempotent and bounded by `timeout`. If running agents don't finish
        within the budget, they are force-cancelled so the caller never
        hangs. Safe to call from the FastAPI lifespan's shutdown hook.
        """
        self._shutdown_event.set()
        try:
            await asyncio.wait_for(self._dispatcher.wait_all(), timeout=timeout)
        except TimeoutError:
            log.warning(
                "Orchestrator stop exceeded budget, force-cancelling agents",
                budget_sec=timeout,
            )
            self._dispatcher.cancel_all()

    def _install_signal_handlers(self) -> None:
        """Hook SIGINT/SIGTERM into the running loop.

        The loop may not support `add_signal_handler` (e.g., on Windows or
        when the orchestrator is driven from a pytest runner that owns the
        signal dispatch). We degrade to "no handler" rather than crash — the
        orchestrator is also started from inside a FastAPI lifespan, where
        uvicorn already traps SIGINT and drives a clean shutdown through
        `stop()`.
        """
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._handle_signal)
            except (NotImplementedError, RuntimeError, ValueError):
                log.debug("Signal handler not installed", sig=sig.name)

    def _handle_signal(self) -> None:
        if self._shutdown_event.is_set():
            log.warning("Force shutdown — cancelling agents")
            self._dispatcher.cancel_all()
            return
        log.info("Shutdown requested (Ctrl+C again to force)")
        self._shutdown_event.set()
