"""FastAPI composition — lifespan owns orchestrator/bus, routers own endpoints.

The lifespan starts the orchestrator polling loop as a background task and
attaches the shared `EventBus`, `StateStore`, and `config_path` to `app.state`
so route handlers can reach them via `Depends(get_*)` helpers in `api/deps.py`.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from task_summoner.api.routers import config_router, events_router, tickets_router
from task_summoner.config import TaskSummonerConfig
from task_summoner.core import StateStore
from task_summoner.events.bus import EventBus
from task_summoner.runtime import Orchestrator

log = structlog.get_logger()

_DASHBOARD_DIR = Path(__file__).resolve().parent.parent / "dashboard_ui" / "static"


def create_app(config_path: Path | None = None) -> FastAPI:
    """Build the FastAPI app. Orchestrator lifecycle runs inside the lifespan."""
    resolved_config_path = config_path or Path("config.yaml")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.config_path = resolved_config_path
        event_bus = EventBus()
        app.state.event_bus = event_bus

        orchestrator_task: asyncio.Task | None = None

        if resolved_config_path.exists():
            try:
                config = TaskSummonerConfig.load(resolved_config_path)
                errors = config.check_config()
                if errors:
                    app.state.configured = False
                    app.state.config_errors = errors
                    app.state.store = StateStore(config.artifacts_dir)
                    for err in errors:
                        log.error("Config validation failed", error=err)
                else:
                    orchestrator = Orchestrator(config, event_bus=event_bus)
                    app.state.store = orchestrator.store
                    app.state.configured = True
                    app.state.config_errors = []
                    orchestrator_task = asyncio.create_task(orchestrator.run())
            except Exception as e:
                log.exception("Failed to load config")
                app.state.configured = False
                app.state.config_errors = [str(e)]
                app.state.store = StateStore("./artifacts")
        else:
            app.state.configured = False
            app.state.config_errors = ["No config.yaml found. Visit /setup to create one."]
            app.state.store = StateStore("./artifacts")

        try:
            yield
        finally:
            if orchestrator_task is not None:
                orchestrator_task.cancel()
                try:
                    await orchestrator_task
                except (asyncio.CancelledError, Exception):
                    pass

    app = FastAPI(title="Task Summoner", version="0.1.0", lifespan=lifespan)

    app.include_router(tickets_router)
    app.include_router(events_router)
    app.include_router(config_router)

    app.mount("/static", StaticFiles(directory=str(_DASHBOARD_DIR)), name="static_files")

    @app.get("/", response_class=HTMLResponse)
    async def dashboard() -> str:
        return (_DASHBOARD_DIR / "index.html").read_text()

    return app
