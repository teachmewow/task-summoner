"""Tests for sync, dispatcher, and orchestrator."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from task_summoner.config import TaskSummonerConfig
from task_summoner.core import StateStore
from task_summoner.events.bus import EventBus
from task_summoner.models import Ticket, TicketContext, TicketState
from task_summoner.runtime import JiraSyncService, TaskDispatcher
from task_summoner.tracker import JiraClient


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def jira(config: TaskSummonerConfig) -> JiraClient:
    return JiraClient(config)


@pytest.fixture
def store(config: TaskSummonerConfig) -> StateStore:
    return StateStore(config.artifacts_dir)


class TestJiraSyncService:
    async def test_new_ticket_queued(self, jira, store, bus):
        sync = JiraSyncService(jira=jira, store=store, bus=bus)
        ticket = Ticket(key="LLMOPS-42", summary="Test", labels=["task-summoner"])
        full_ticket = Ticket(key="LLMOPS-42", summary="Test", labels=["task-summoner"])

        with patch.object(jira, "search_eligible", new_callable=AsyncMock, return_value=[ticket]):
            with patch.object(jira, "fetch_ticket", new_callable=AsyncMock, return_value=full_ticket):
                await sync.discover()

        ctx = store.load("LLMOPS-42")
        assert ctx is not None
        assert ctx.state == TicketState.QUEUED

    async def test_recovers_from_labels(self, jira, store, bus):
        sync = JiraSyncService(jira=jira, store=store, bus=bus)
        ticket = Ticket(key="LLMOPS-42", summary="Test", labels=["task-summoner"])
        full_ticket = Ticket(
            key="LLMOPS-42", summary="Test",
            labels=["task-summoner", "ts:planning", "ts:waiting_plan_review"],
        )

        with patch.object(jira, "search_eligible", new_callable=AsyncMock, return_value=[ticket]):
            with patch.object(jira, "fetch_ticket", new_callable=AsyncMock, return_value=full_ticket):
                await sync.discover()

        ctx = store.load("LLMOPS-42")
        assert ctx.state == TicketState.WAITING_PLAN_REVIEW

    async def test_skips_already_tracked(self, jira, store, bus):
        store.save(TicketContext(ticket_key="LLMOPS-42", state=TicketState.IMPLEMENTING))
        sync = JiraSyncService(jira=jira, store=store, bus=bus)
        ticket = Ticket(key="LLMOPS-42", summary="Test", labels=["task-summoner"])

        with patch.object(jira, "search_eligible", new_callable=AsyncMock, return_value=[ticket]):
            with patch.object(jira, "fetch_ticket", new_callable=AsyncMock) as mock_fetch:
                await sync.discover()
                mock_fetch.assert_not_called()  # no fetch for tracked tickets

        ctx = store.load("LLMOPS-42")
        assert ctx.state == TicketState.IMPLEMENTING  # unchanged

    async def test_skips_terminal_without_local(self, jira, store, bus):
        sync = JiraSyncService(jira=jira, store=store, bus=bus)
        ticket = Ticket(key="LLMOPS-42", summary="Test", labels=["task-summoner"])
        full_ticket = Ticket(
            key="LLMOPS-42", summary="Test",
            labels=["task-summoner", "ts:done"],
        )

        with patch.object(jira, "search_eligible", new_callable=AsyncMock, return_value=[ticket]):
            with patch.object(jira, "fetch_ticket", new_callable=AsyncMock, return_value=full_ticket):
                await sync.discover()

        assert store.load("LLMOPS-42") is None

    async def test_jira_failure_returns_existing_active(self, jira, store, bus):
        store.save(TicketContext(ticket_key="LLMOPS-42", state=TicketState.PLANNING))
        sync = JiraSyncService(jira=jira, store=store, bus=bus)

        with patch.object(jira, "search_eligible", new_callable=AsyncMock, side_effect=RuntimeError("down")):
            active = await sync.discover()

        assert len(active) == 1
        assert active[0].ticket_key == "LLMOPS-42"

    async def test_fetch_failure_falls_back_to_search_ticket(self, jira, store, bus):
        sync = JiraSyncService(jira=jira, store=store, bus=bus)
        ticket = Ticket(key="LLMOPS-42", summary="Test", labels=["task-summoner"])

        with patch.object(jira, "search_eligible", new_callable=AsyncMock, return_value=[ticket]):
            with patch.object(jira, "fetch_ticket", new_callable=AsyncMock, side_effect=RuntimeError("fail")):
                await sync.discover()

        ctx = store.load("LLMOPS-42")
        assert ctx is not None
        assert ctx.state == TicketState.QUEUED  # no labels to recover from


class TestTaskDispatcher:
    @pytest.fixture
    def dispatcher(self, config, store, jira, bus):
        from task_summoner.states import build_state_registry, StateServices

        services = StateServices(
            jira=jira,
            workspace=MagicMock(),
            agent_runner=MagicMock(),
            store=store,
        )
        return TaskDispatcher(
            states=build_state_registry(config),
            services=services,
            store=store,
            jira=jira,
            bus=bus,
        )

    async def test_apply_trigger_transitions(self, dispatcher, store):
        ctx = TicketContext(ticket_key="LLMOPS-42", state=TicketState.QUEUED)
        store.save(ctx)

        await dispatcher._apply_trigger(ctx, "start")
        loaded = store.load("LLMOPS-42")
        assert loaded.state == TicketState.CHECKING_DOC

    async def test_apply_trigger_wait_no_transition(self, dispatcher, store):
        ctx = TicketContext(ticket_key="LLMOPS-42", state=TicketState.WAITING_PLAN_REVIEW)
        store.save(ctx)

        await dispatcher._apply_trigger(ctx, "_wait")
        loaded = store.load("LLMOPS-42")
        assert loaded.state == TicketState.WAITING_PLAN_REVIEW

    async def test_skips_running_tasks(self, dispatcher, store, jira):
        ctx = TicketContext(ticket_key="LLMOPS-42", state=TicketState.PLANNING)
        store.save(ctx)

        async def _hang():
            await asyncio.sleep(999)

        task = asyncio.create_task(_hang())
        dispatcher._running["LLMOPS-42"] = task

        ticket = Ticket(key="LLMOPS-42", summary="Test", labels=["task-summoner"])
        with patch.object(jira, "fetch_ticket", new_callable=AsyncMock, return_value=ticket):
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
