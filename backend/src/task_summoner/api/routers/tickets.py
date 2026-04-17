"""Ticket endpoints — list, single, and per-ticket event history."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from task_summoner.api.deps import get_event_bus, get_store
from task_summoner.api.schemas import EventResponse, TicketResponse
from task_summoner.core import StateStore
from task_summoner.events.bus import EventBus

router = APIRouter(prefix="/api/tickets", tags=["tickets"])


@router.get("", response_model=list[TicketResponse])
async def list_tickets(store: StateStore = Depends(get_store)) -> list[TicketResponse]:
    return store.list_all()


@router.get("/{ticket_key}", response_model=TicketResponse)
async def get_ticket(ticket_key: str, store: StateStore = Depends(get_store)) -> TicketResponse:
    ctx = store.load(ticket_key)
    if not ctx:
        raise HTTPException(status_code=404, detail="Not found")
    return ctx


@router.get("/{ticket_key}/events", response_model=list[EventResponse])
async def get_ticket_events(
    ticket_key: str, event_bus: EventBus = Depends(get_event_bus)
) -> list[EventResponse]:
    return list(event_bus.get_history(ticket_key))
