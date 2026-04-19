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
    agent_profiles_router,
    config_router,
    cost_router,
    decisions_router,
    events_router,
    failures_router,
    gates_router,
    health_router,
    rfcs_router,
    setup_router,
    skills_router,
    streams_router,
    tickets_router,
    workflow_router,
)
from task_summoner.config import TaskSummonerConfig
from task_summoner.core import StateStore
from task_summoner.events.bus import EventBus
from task_summoner.observability import configure_claude_agent_sdk_tracing
from task_summoner.runtime import Orchestrator

log = structlog.get_logger()

_WEB_DIST = Path(__file__).resolve().parent.parent / "web_dist"

# Upper bound for the lifespan shutdown hook. Must be strictly less than
# uvicorn's `timeout_graceful_shutdown` so the lifespan finishes before
# uvicorn's own deadline fires and force-closes us.
_SHUTDOWN_TIMEOUT_SEC = 8.0


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

        # Opt-in LangSmith tracing: auto-instruments the Claude Agent SDK when
        # LANGCHAIN_TRACING_V2 + LANGCHAIN_API_KEY are set. No-op otherwise.
        if configure_claude_agent_sdk_tracing():
            log.info("LangSmith Claude Agent SDK tracing enabled")

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
    app.include_router(agent_profiles_router)
    app.include_router(skills_router)
    app.include_router(workflow_router)
    app.include_router(health_router)
    app.include_router(setup_router)
    app.include_router(gates_router)
    app.include_router(decisions_router)
    app.include_router(rfcs_router)
    app.include_router(streams_router)

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
    app.state.orchestrator = orchestrator
    app.state.config = config
    app.state.configured = True
    app.state.config_errors = []
    # ENG-116: uvicorn installs SIGINT via signal.signal() before our lifespan
    # runs. If the orchestrator called loop.add_signal_handler(), it would
    # silently clobber uvicorn's handler and Ctrl+C would hang forever because
    # uvicorn's main_loop would never see should_exit=True. Let uvicorn own
    # signals; it calls the lifespan finalizer which calls stop() for us.
    app.state.orchestrator_task = asyncio.create_task(
        orchestrator.run(install_signal_handlers=False)
    )
    log.info("Orchestrator started")


async def _stop_orchestrator(app: FastAPI) -> None:
    """Bounded orchestrator shutdown for the lifespan close hook.

    Asks the orchestrator to stop gracefully within `_SHUTDOWN_TIMEOUT_SEC`
    (which drains in-flight agents through the dispatcher). If it doesn't
    finish in time, we cancel the underlying task so uvicorn can close the
    event loop. This prevents the "Ctrl+C hangs forever" bug — see ENG-112.
    """
    task: asyncio.Task | None = getattr(app.state, "orchestrator_task", None)
    if task is None:
        return

    orchestrator: Orchestrator | None = getattr(app.state, "orchestrator", None)
    if orchestrator is not None:
        try:
            await asyncio.wait_for(
                orchestrator.stop(timeout=_SHUTDOWN_TIMEOUT_SEC),
                timeout=_SHUTDOWN_TIMEOUT_SEC + 2.0,
            )
        except TimeoutError:
            log.warning(
                "Orchestrator.stop() exceeded budget — proceeding to cancel",
                budget_sec=_SHUTDOWN_TIMEOUT_SEC,
            )
        except Exception:
            log.exception("Orchestrator.stop() raised unexpectedly")

    if not task.done():
        task.cancel()
    try:
        await asyncio.wait_for(task, timeout=2.0)
    except (asyncio.CancelledError, TimeoutError, Exception):
        pass
    app.state.orchestrator_task = None
    app.state.orchestrator = None


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
