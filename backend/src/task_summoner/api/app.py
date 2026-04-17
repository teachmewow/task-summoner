"""FastAPI composition — lifespan owns orchestrator/bus, routers own endpoints.

The lifespan tries to start the orchestrator polling loop as a background task
when a valid config exists. If config is missing or invalid, the server still
serves (UI-first onboarding — see ENG-69). The orchestrator can be restarted
at runtime via `reload_orchestrator(app)` after `/api/config` writes a new
config.yaml.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from task_summoner.api.routers import (
    config_router,
    cost_router,
    events_router,
    failures_router,
    tickets_router,
)
from task_summoner.config import TaskSummonerConfig
from task_summoner.core import StateStore
from task_summoner.events.bus import EventBus
from task_summoner.runtime import Orchestrator

log = structlog.get_logger()

_WEB_DIST = Path(__file__).resolve().parent.parent / "web_dist"


def create_app(config_path: Path | None = None) -> FastAPI:
    """Build the FastAPI app. Orchestrator lifecycle runs inside the lifespan."""
    resolved_config_path = config_path or Path("config.yaml")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.config_path = resolved_config_path
        app.state.event_bus = EventBus()
        app.state.orchestrator_task = None
        app.state.configured = False
        app.state.config_errors = []
        app.state.store = StateStore("./artifacts")

        await reload_orchestrator(app)

        try:
            yield
        finally:
            await _stop_orchestrator(app)

    app = FastAPI(title="Task Summoner", version="0.1.0", lifespan=lifespan)

    app.include_router(tickets_router)
    app.include_router(events_router)
    app.include_router(config_router)
    app.include_router(cost_router)
    app.include_router(failures_router)

    _mount_frontend(app)

    return app


async def reload_orchestrator(app: FastAPI) -> None:
    """Stop any running orchestrator, reload config, restart if valid.

    Called on startup by the lifespan, and again after `/api/config` writes a
    new config.yaml. Populates `app.state.{configured,config_errors,store}`
    regardless of success so the UI can report status.
    """
    await _stop_orchestrator(app)

    config_path: Path = app.state.config_path
    event_bus: EventBus = app.state.event_bus

    if not config_path.exists():
        app.state.configured = False
        app.state.config_errors = ["No config.yaml found. Visit /setup to create one."]
        app.state.store = StateStore("./artifacts")
        return

    try:
        config = TaskSummonerConfig.load(config_path)
    except Exception as e:
        log.exception("Failed to load config")
        app.state.configured = False
        app.state.config_errors = [str(e)]
        app.state.store = StateStore("./artifacts")
        return

    errors = config.check_config()
    if errors:
        app.state.configured = False
        app.state.config_errors = errors
        app.state.store = StateStore(config.artifacts_dir)
        for err in errors:
            log.error("Config validation failed", error=err)
        return

    orchestrator = Orchestrator(config, event_bus=event_bus)
    app.state.store = orchestrator.store
    app.state.config = config
    app.state.configured = True
    app.state.config_errors = []
    app.state.orchestrator_task = asyncio.create_task(orchestrator.run())
    log.info("Orchestrator started")


async def _stop_orchestrator(app: FastAPI) -> None:
    task: asyncio.Task | None = getattr(app.state, "orchestrator_task", None)
    if task is None:
        return
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass
    app.state.orchestrator_task = None


def _mount_frontend(app: FastAPI) -> None:
    """Serve the built React app from `web_dist/` with SPA fallback.

    When the bundle is missing (contributors running backend only, no `pnpm build`),
    the catch-all returns a JSON hint instead of crashing uvicorn.
    """
    index_html = _WEB_DIST / "index.html"
    assets_dir = _WEB_DIST / "assets"

    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str, request: Request):
        if full_path.startswith(("api/", "assets/")):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        if index_html.is_file():
            return FileResponse(index_html)
        return JSONResponse(
            {
                "detail": (
                    "Frontend bundle not found. Run `pnpm build` in frontend/ "
                    "or start dev mode with `task-summoner run --dev`."
                )
            },
            status_code=503,
        )
