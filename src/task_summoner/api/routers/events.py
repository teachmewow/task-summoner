"""Event endpoints — SSE streaming + history dump."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from task_summoner.api.deps import get_event_bus
from task_summoner.api.schemas import EventResponse
from task_summoner.events.bus import EventBus

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("/stream")
async def event_stream(
    ticket: str | None = None, event_bus: EventBus = Depends(get_event_bus)
) -> StreamingResponse:
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


@router.get("/history", response_model=list[EventResponse])
async def event_history(
    ticket: str | None = None, event_bus: EventBus = Depends(get_event_bus)
) -> list[EventResponse]:
    return list(event_bus.get_history(ticket))
