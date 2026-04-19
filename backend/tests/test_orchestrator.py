"""Tests for sync, dispatcher, and orchestrator (provider-agnostic)."""

from __future__ import annotations

import asyncio
import os
import signal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from task_summoner.config import TaskSummonerConfig
from task_summoner.core import StateStore
from task_summoner.events.bus import EventBus
from task_summoner.models import Ticket, TicketContext, TicketState
from task_summoner.runtime import BoardSyncService, Orchestrator, TaskDispatcher
from task_summoner.states import StateServices, build_state_registry


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def board() -> AsyncMock:
    """Mock BoardProvider."""
    return AsyncMock()


@pytest.fixture
def store(config: TaskSummonerConfig) -> StateStore:
    return StateStore(config.artifacts_dir)


class TestBoardSyncService:
    async def test_new_ticket_queued(self, board, store, bus):
        sync = BoardSyncService(board=board, store=store, bus=bus)
        ticket = Ticket(key="LLMOPS-42", summary="Test", labels=["task-summoner"])
        full_ticket = Ticket(key="LLMOPS-42", summary="Test", labels=["task-summoner"])

        board.search_eligible.return_value = [ticket]
        board.fetch_ticket.return_value = full_ticket

        await sync.discover()

        ctx = store.load("LLMOPS-42")
        assert ctx is not None
        assert ctx.state == TicketState.QUEUED

    async def test_recovers_from_labels(self, board, store, bus):
        sync = BoardSyncService(board=board, store=store, bus=bus)
        ticket = Ticket(key="LLMOPS-42", summary="Test", labels=["task-summoner"])
        full_ticket = Ticket(
            key="LLMOPS-42",
            summary="Test",
            labels=["task-summoner", "ts:planning", "ts:waiting_plan_review"],
        )

        board.search_eligible.return_value = [ticket]
        board.fetch_ticket.return_value = full_ticket

        await sync.discover()

        ctx = store.load("LLMOPS-42")
        assert ctx.state == TicketState.WAITING_PLAN_REVIEW

    async def test_skips_already_tracked(self, board, store, bus):
        store.save(TicketContext(ticket_key="LLMOPS-42", state=TicketState.IMPLEMENTING))
        sync = BoardSyncService(board=board, store=store, bus=bus)
        ticket = Ticket(key="LLMOPS-42", summary="Test", labels=["task-summoner"])

        board.search_eligible.return_value = [ticket]
        await sync.discover()
        board.fetch_ticket.assert_not_called()

        ctx = store.load("LLMOPS-42")
        assert ctx.state == TicketState.IMPLEMENTING

    async def test_skips_terminal_without_local(self, board, store, bus):
        sync = BoardSyncService(board=board, store=store, bus=bus)
        ticket = Ticket(key="LLMOPS-42", summary="Test", labels=["task-summoner"])
        full_ticket = Ticket(
            key="LLMOPS-42",
            summary="Test",
            labels=["task-summoner", "ts:done"],
        )

        board.search_eligible.return_value = [ticket]
        board.fetch_ticket.return_value = full_ticket

        await sync.discover()

        assert store.load("LLMOPS-42") is None

    async def test_board_failure_returns_existing_active(self, board, store, bus):
        store.save(TicketContext(ticket_key="LLMOPS-42", state=TicketState.PLANNING))
        sync = BoardSyncService(board=board, store=store, bus=bus)

        board.search_eligible.side_effect = RuntimeError("down")
        active = await sync.discover()

        assert len(active) == 1
        assert active[0].ticket_key == "LLMOPS-42"

    async def test_fetch_failure_falls_back_to_search_ticket(self, board, store, bus):
        sync = BoardSyncService(board=board, store=store, bus=bus)
        ticket = Ticket(key="LLMOPS-42", summary="Test", labels=["task-summoner"])

        board.search_eligible.return_value = [ticket]
        board.fetch_ticket.side_effect = RuntimeError("fail")

        await sync.discover()

        ctx = store.load("LLMOPS-42")
        assert ctx is not None
        assert ctx.state == TicketState.QUEUED


class TestTaskDispatcher:
    @pytest.fixture
    def dispatcher(self, config, store, board, bus):
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

    async def test_apply_trigger_transitions(self, dispatcher, store):
        ctx = TicketContext(ticket_key="LLMOPS-42", state=TicketState.QUEUED)
        store.save(ctx)

        await dispatcher._apply_trigger(ctx, "no_doc_needed")
        loaded = store.load("LLMOPS-42")
        assert loaded.state == TicketState.PLANNING

    async def test_apply_trigger_wait_no_transition(self, dispatcher, store):
        ctx = TicketContext(ticket_key="LLMOPS-42", state=TicketState.WAITING_PLAN_REVIEW)
        store.save(ctx)

        await dispatcher._apply_trigger(ctx, "_wait")
        loaded = store.load("LLMOPS-42")
        assert loaded.state == TicketState.WAITING_PLAN_REVIEW

    async def test_skips_running_tasks(self, dispatcher, store, board):
        ctx = TicketContext(ticket_key="LLMOPS-42", state=TicketState.PLANNING)
        store.save(ctx)

        async def _hang():
            await asyncio.sleep(999)

        task = asyncio.create_task(_hang())
        dispatcher._running["LLMOPS-42"] = task

        ticket = Ticket(key="LLMOPS-42", summary="Test", labels=["task-summoner"])
        board.fetch_ticket.return_value = ticket
        with patch.object(dispatcher, "_dispatch_one", new_callable=AsyncMock) as mock:
            await dispatcher.dispatch_all([ctx])
            mock.assert_not_called()

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def test_collect_crashed_tasks(self, dispatcher, store):
        ctx = TicketContext(ticket_key="LLMOPS-42", state=TicketState.PLANNING)
        store.save(ctx)

        async def _crash():
            raise RuntimeError("boom")

        dispatcher._running["LLMOPS-42"] = asyncio.create_task(_crash())
        await asyncio.sleep(0.01)

        await dispatcher._collect_completed()
        loaded = store.load("LLMOPS-42")
        assert loaded.retry_count == 1
        assert loaded.error is not None


class TestOrchestratorShutdown:
    """ENG-112: SIGINT must unblock the run loop within a bounded timeout."""

    @pytest.fixture
    def orchestrator(self, config: TaskSummonerConfig, monkeypatch) -> Orchestrator:
        # Avoid spinning up real provider adapters inside Orchestrator.__init__.
        # The polling loop does not exercise them in this test.
        from task_summoner.providers.agent import AgentProviderFactory
        from task_summoner.providers.board import BoardProviderFactory

        monkeypatch.setattr(BoardProviderFactory, "create", staticmethod(lambda _cfg: AsyncMock()))
        monkeypatch.setattr(AgentProviderFactory, "create", staticmethod(lambda _cfg: AsyncMock()))
        orch = Orchestrator(config)
        # Short poll so the loop wakes quickly on shutdown_event.
        orch._config = config.model_copy(update={"polling_interval_sec": 1})
        # Make sync.discover a no-op so tests don't depend on real board I/O.
        orch._sync.discover = AsyncMock(return_value=[])  # type: ignore[assignment]
        orch._dispatcher.dispatch_all = AsyncMock()  # type: ignore[assignment]
        return orch

    @pytest.mark.asyncio
    async def test_sigint_unblocks_run_within_budget(self, orchestrator):
        """Send SIGINT to the current process; run() must exit within 10s."""
        # Start the orchestrator's polling loop.
        task = asyncio.create_task(orchestrator.run())
        # Let it install signal handlers and enter the loop.
        await asyncio.sleep(0.1)

        # Trigger first Ctrl+C.
        os.kill(os.getpid(), signal.SIGINT)

        # run() must complete (graceful shutdown) well within 10s.
        await asyncio.wait_for(task, timeout=10)
        assert task.done()
        assert not task.cancelled()

    @pytest.mark.asyncio
    async def test_stop_cancels_hanging_agents_within_timeout(self, orchestrator):
        """If a running agent task hangs, stop() must force-cancel before timing out."""

        async def _hang():
            await asyncio.Event().wait()  # forever

        orchestrator._dispatcher._running["STUCK-1"] = asyncio.create_task(_hang())

        start = asyncio.get_event_loop().time()
        await orchestrator.stop(timeout=0.5)
        elapsed = asyncio.get_event_loop().time() - start

        # Stop must return promptly (budget 0.5s + a bit of overhead).
        assert elapsed < 3.0
        # The hung task must have been cancelled.
        stuck = orchestrator._dispatcher._running.get("STUCK-1")
        assert stuck is None or stuck.cancelled() or stuck.done()

    @pytest.mark.asyncio
    async def test_second_signal_force_cancels(self, orchestrator):
        """Second signal delivery calls dispatcher.cancel_all."""

        async def _hang():
            await asyncio.Event().wait()

        orchestrator._dispatcher._running["STUCK-2"] = asyncio.create_task(_hang())

        # First invocation sets the shutdown event.
        orchestrator._handle_signal()
        assert orchestrator._shutdown_event.is_set()

        # Second invocation force-cancels running agents.
        orchestrator._handle_signal()
        await asyncio.sleep(0)  # let cancellation propagate

        stuck = orchestrator._dispatcher._running["STUCK-2"]
        assert stuck.cancelled() or stuck.done()
        # Cleanup so pytest doesn't complain about unawaited tasks.
        try:
            await stuck
        except asyncio.CancelledError:
            pass
