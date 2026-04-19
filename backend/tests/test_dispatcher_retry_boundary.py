"""Tests for the retry-boundary stream event emitted on ``_retry`` triggers.

When a state handler returns ``_retry`` (planning failure, implementation
verification mismatch, etc.), the dispatcher must write a single
``retry_boundary`` record to the ticket's stream BEFORE the next dispatch
re-runs the same handler. That event is what the UI uses to draw the
"Attempt N — retrying …" divider.

We don't run an actual agent here — we mock the handler so it synchronously
returns ``_retry`` and verify the dispatcher wrote the expected record via
the stream_writer_factory hook.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from task_summoner.core import StateStore
from task_summoner.events.bus import EventBus
from task_summoner.models import Ticket, TicketContext, TicketState
from task_summoner.runtime import TaskDispatcher
from task_summoner.runtime.stream_writer import StreamWriter, replay
from task_summoner.states import StateServices
from task_summoner.states.base import BaseState


class _FakePlanningHandler(BaseState):
    """Minimal state handler that records a failure and returns ``_retry``.

    Mirrors what ``PlanningState._fail`` does on a planner that didn't produce
    a plan: bumps ``retry_count``, stores an error message, returns ``_retry``.
    Kept as a non-agent handler (``requires_agent=False``) so the dispatcher
    runs it synchronously and we don't need asyncio task collection.
    """

    def __init__(self, config) -> None:
        super().__init__(config)
        self._state = TicketState.PLANNING

    @property
    def state(self) -> TicketState:  # type: ignore[override]
        return TicketState.PLANNING

    async def handle(self, ctx, ticket, services):  # type: ignore[override]
        ctx.error = "Planner did not produce a plan"
        ctx.retry_count += 1
        return "_retry"


@pytest.mark.asyncio
async def test_retry_boundary_event_written_with_attempt_and_reason(
    config, store: StateStore, tmp_path: Path
):
    """A ``_retry`` trigger writes one retry_boundary record with the right shape."""
    ctx = TicketContext(ticket_key="ENG-136", state=TicketState.PLANNING)
    store.save(ctx)
    ticket = Ticket(key="ENG-136", summary="s", description="d", status="In Progress")

    board = AsyncMock()
    board.fetch_ticket.return_value = ticket

    writer_factory = lambda key: StreamWriter(tmp_path / "artifacts", key)  # noqa: E731

    services = StateServices(
        board=board,
        workspace=MagicMock(),
        agent=AsyncMock(),
        store=store,
        stream_writer_factory=writer_factory,
    )

    handler = _FakePlanningHandler(config)
    dispatcher = TaskDispatcher(
        states={TicketState.PLANNING: handler},
        services=services,
        store=store,
        board=board,
        bus=EventBus(),
    )

    await dispatcher.dispatch_all([ctx])

    records = replay(tmp_path / "artifacts", "ENG-136")
    boundaries = [r for r in records if r.get("type") == "retry_boundary"]
    assert len(boundaries) == 1
    b = boundaries[0]
    assert b["state"] == "PLANNING"
    # After the handler's own retry_count bump (0 -> 1), the next attempt is 2.
    assert b["attempt"] == 2
    assert "Planner did not produce" in b["reason"]
    # Serializes as canonical JSONL — the SSE endpoint re-reads this as a dict.
    assert json.dumps(b)


@pytest.mark.asyncio
async def test_retry_boundary_noop_when_no_stream_writer_factory(
    config, store: StateStore, tmp_path: Path
):
    """Dispatcher must stay functional when the factory is unset (tests, etc.)."""
    ctx = TicketContext(ticket_key="ENG-137", state=TicketState.PLANNING)
    store.save(ctx)
    ticket = Ticket(key="ENG-137", summary="s", description="d", status="In Progress")

    board = AsyncMock()
    board.fetch_ticket.return_value = ticket

    services = StateServices(
        board=board,
        workspace=MagicMock(),
        agent=AsyncMock(),
        store=store,
        stream_writer_factory=None,
    )

    handler = _FakePlanningHandler(config)
    dispatcher = TaskDispatcher(
        states={TicketState.PLANNING: handler},
        services=services,
        store=store,
        board=board,
        bus=EventBus(),
    )

    await dispatcher.dispatch_all([ctx])

    # No stream writer configured -> no file emitted, no exception raised.
    assert replay(tmp_path / "artifacts", "ENG-137") == []
    loaded = store.load("ENG-137")
    assert loaded is not None
    assert loaded.retry_count == 1
