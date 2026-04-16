"""CLI command implementations."""

from __future__ import annotations

import asyncio

import uvicorn
import structlog

from board_dispatcher.api.app import create_app
from board_dispatcher.config import BoardDispatcherConfig
from board_dispatcher.core import StateStore
from board_dispatcher.events.bus import EventBus
from board_dispatcher.runtime import Orchestrator

log = structlog.get_logger()


async def cmd_run(config_path: str, port: int = 8420, with_ui: bool = True) -> None:
    """Start the orchestrator polling loop, optionally with the web dashboard."""
    config = BoardDispatcherConfig.load(config_path)

    errors = config.check_config()
    if errors:
        for err in errors:
            log.error("Config validation failed", error=err)
        raise SystemExit(1)

    event_bus = EventBus()
    orchestrator = Orchestrator(config, event_bus=event_bus)

    tasks: list[asyncio.Task] = [asyncio.create_task(orchestrator.run())]

    if with_ui:
        tasks.append(asyncio.create_task(_start_dashboard(event_bus, orchestrator.store, port)))

    await asyncio.gather(*tasks)


async def _start_dashboard(event_bus: EventBus, store: StateStore, port: int) -> None:
    """Launch the FastAPI dashboard on the given port."""
    app = create_app(event_bus, store)
    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=port, log_level="warning"))
    log.info("Dashboard available", url=f"http://localhost:{port}")
    await server.serve()


def cmd_status(config_path: str) -> None:
    """Show all tracked tickets and their states."""
    config = BoardDispatcherConfig.load(config_path)
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
