"""Orchestrator — slim polling loop that coordinates sync and dispatch."""

from __future__ import annotations

import asyncio
import signal

import structlog

from board_dispatcher.agents.options import AgentOptionsFactory
from board_dispatcher.agents.runner import AgentRunner
from board_dispatcher.config import BoardDispatcherConfig
from board_dispatcher.core import StateStore
from board_dispatcher.events.bus import EventBus
from board_dispatcher.runtime.dispatcher import TaskDispatcher
from board_dispatcher.runtime.sync import JiraSyncService
from board_dispatcher.states import StateServices, build_state_registry
from board_dispatcher.tracker import JiraClient
from board_dispatcher.workspace import GitWorkspaceManager

log = structlog.get_logger()


class Orchestrator:
    def __init__(
        self,
        config: BoardDispatcherConfig,
        event_bus: EventBus | None = None,
    ) -> None:
        self._config = config
        self._bus = event_bus or EventBus()

        # Infrastructure
        jira = JiraClient(config)
        store = StateStore(config.artifacts_dir)
        workspace = GitWorkspaceManager(config)
        plugin_resolver = config.build_plugin_resolver()
        options_factory = AgentOptionsFactory(config, plugin_resolver=plugin_resolver)
        agent_runner = AgentRunner(options_factory=options_factory, event_bus=self._bus)

        # Services shared by state handlers
        services = StateServices(
            jira=jira,
            workspace=workspace,
            agent_runner=agent_runner,
            store=store,
        )

        # Core components
        self._sync = JiraSyncService(jira=jira, store=store, bus=self._bus)
        self._dispatcher = TaskDispatcher(
            states=build_state_registry(config),
            services=services,
            store=store,
            jira=jira,
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
            "Board-dispatcher starting",
            poll_interval=self._config.poll_interval_sec,
            repos=list(self._config.repos.keys()),
        )

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._handle_signal)

        await asyncio.sleep(0.5)  # Let uvicorn start first

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
            except asyncio.TimeoutError:
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
