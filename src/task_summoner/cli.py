"""CLI command implementations."""

from __future__ import annotations

import asyncio
from pathlib import Path

import structlog
import uvicorn

from task_summoner.api.app import create_app
from task_summoner.config import TaskSummonerConfig
from task_summoner.core import StateStore
from task_summoner.events.bus import EventBus
from task_summoner.models import TicketContext
from task_summoner.providers.board import (
    BoardNotFoundError,
    BoardProvider,
    BoardProviderFactory,
)
from task_summoner.runtime import Orchestrator
from task_summoner.setup_wizard import run_wizard

log = structlog.get_logger()


async def cmd_run(config_path: str, port: int = 8420, with_ui: bool = True) -> None:
    """Start the orchestrator polling loop, optionally with the web dashboard."""
    path = Path(config_path)
    if not path.exists():
        log.info("No config found, launching setup wizard", path=config_path)
        run_wizard(path)
        if not path.exists():
            raise SystemExit(0)

    config = TaskSummonerConfig.load(config_path)

    errors = config.check_config()
    if errors:
        for err in errors:
            log.error("Config validation failed", error=err)
        raise SystemExit(1)

    event_bus = EventBus()
    orchestrator = Orchestrator(config, event_bus=event_bus)

    tasks: list[asyncio.Task] = [asyncio.create_task(orchestrator.run())]

    if with_ui:
        tasks.append(
            asyncio.create_task(_start_dashboard(event_bus, orchestrator.store, port, path))
        )

    await asyncio.gather(*tasks)


def cmd_setup(config_path: str) -> None:
    """Launch the interactive setup wizard to create or overwrite config.yaml."""
    run_wizard(Path(config_path))


async def _start_dashboard(
    event_bus: EventBus, store: StateStore, port: int, config_path: Path
) -> None:
    """Launch the FastAPI dashboard on the given port."""
    app = create_app(event_bus, store, config_path=config_path)
    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=port, log_level="warning"))
    log.info("Dashboard available", url=f"http://localhost:{port}")
    await server.serve()


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
