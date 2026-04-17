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

    async def run(self) -> None:
        log.info(
            "Task Summoner starting",
            poll_interval=self._config.poll_interval_sec,
            repos=list(self._config.repos.keys()),
        )

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._handle_signal)

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
        await self._dispatcher.wait_all()
        log.info("Shutdown complete")

    def _handle_signal(self) -> None:
        if self._shutdown_event.is_set():
            log.warning("Force shutdown — cancelling agents")
            self._dispatcher.cancel_all()
            return
        log.info("Shutdown requested (Ctrl+C again to force)")
        self._shutdown_event.set()
