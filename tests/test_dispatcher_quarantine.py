"""Tests for dispatcher auto-quarantine behavior on BoardNotFoundError."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from task_summoner.core import StateStore
from task_summoner.events.bus import EventBus
from task_summoner.models import TicketContext, TicketState
from task_summoner.providers.board import BoardNotFoundError
from task_summoner.runtime import TaskDispatcher
from task_summoner.states import StateServices, build_state_registry


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def board() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def dispatcher(config, store: StateStore, board, bus: EventBus) -> TaskDispatcher:
    services = StateServices(
        board=board,
        workspace=MagicMock(),
        agent=AsyncMock(),
        store=store,
    )
    return TaskDispatcher(
        states=build_state_registry(config),
        services=services,
        store=store,
        board=board,
        bus=bus,
    )


class TestDispatcherQuarantine:
    async def test_board_not_found_marks_ticket_failed(
        self, dispatcher: TaskDispatcher, store: StateStore, board: AsyncMock
    ):
        ctx = TicketContext(ticket_key="GONE-1", state=TicketState.QUEUED)
        store.save(ctx)

        board.fetch_ticket.side_effect = BoardNotFoundError("GONE-1 not found")
        await dispatcher.dispatch_all([ctx])

        loaded = store.load("GONE-1")
        assert loaded is not None
        assert loaded.state == TicketState.FAILED
        assert "Not reachable on board" in (loaded.error or "")

    async def test_already_failed_ticket_is_noop(
        self, dispatcher: TaskDispatcher, store: StateStore, board: AsyncMock
    ):
        ctx = TicketContext(
            ticket_key="GONE-2",
            state=TicketState.FAILED,
            error="Not reachable on board: previous run",
        )
        store.save(ctx)

        board.fetch_ticket.side_effect = BoardNotFoundError("GONE-2 not found")
        await dispatcher.dispatch_all([ctx])

        loaded = store.load("GONE-2")
        assert loaded is not None
        assert loaded.state == TicketState.FAILED

    async def test_transient_fetch_error_does_not_quarantine(
        self, dispatcher: TaskDispatcher, store: StateStore, board: AsyncMock
    ):
        ctx = TicketContext(ticket_key="FLAKY-1", state=TicketState.QUEUED)
        store.save(ctx)

        board.fetch_ticket.side_effect = RuntimeError("network timeout")
        await dispatcher.dispatch_all([ctx])

        loaded = store.load("FLAKY-1")
        assert loaded is not None
        assert loaded.state == TicketState.QUEUED


class TestStateStoreDelete:
    def test_delete_removes_ticket_dir(self, store: StateStore):
        ctx = TicketContext(ticket_key="TMP-1", state=TicketState.QUEUED)
        store.save(ctx)
        assert store.load("TMP-1") is not None

        removed = store.delete("TMP-1")
        assert removed is True
        assert store.load("TMP-1") is None

    def test_delete_missing_ticket_returns_false(self, store: StateStore):
        assert store.delete("NEVER-EXISTED") is False
