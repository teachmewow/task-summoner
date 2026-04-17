"""FastAPI application for the monitoring dashboard."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from task_summoner.api.setup import create_setup_router
from task_summoner.core import StateStore
from task_summoner.events.bus import EventBus

DASHBOARD_DIR = Path(__file__).resolve().parent.parent / "dashboard_ui" / "static"


def create_app(
    event_bus: EventBus,
    store: StateStore,
    config_path: Path | None = None,
) -> FastAPI:
    """Create FastAPI app wired to the shared EventBus and StateStore."""

    app = FastAPI(title="Task Summoner Monitor", version="0.1.0")
    app.include_router(create_setup_router(config_path or Path("config.yaml")))

    app.mount("/static", StaticFiles(directory=str(DASHBOARD_DIR)), name="static_files")

    @app.get("/", response_class=HTMLResponse)
    async def dashboard():
        return (DASHBOARD_DIR / "index.html").read_text()

    @app.get("/api/tickets")
    async def list_tickets():
        contexts = store.list_all()
        return [ctx.to_dict() for ctx in contexts]

    @app.get("/api/tickets/{ticket_key}")
    async def get_ticket(ticket_key: str):
        ctx = store.load(ticket_key)
        if not ctx:
            return {"error": "Not found"}, 404
        return ctx.to_dict()

    @app.get("/api/tickets/{ticket_key}/events")
    async def get_ticket_events(ticket_key: str):
        events = event_bus.get_history(ticket_key)
        return [e.model_dump(mode="json") for e in events]

    @app.get("/api/events/stream")
    async def event_stream(request: Request, ticket: str | None = None):
        async def generate():
            async for event in event_bus.subscribe(ticket_key=ticket, include_history=False):
                data = json.dumps(event.model_dump(mode="json"))
                yield f"event: {event.event_type.value}\ndata: {data}\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/events/history")
    async def event_history(ticket: str | None = None):
        events = event_bus.get_history(ticket)
        return [e.model_dump(mode="json") for e in events]

    return app
