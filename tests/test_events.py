"""Tests for the event system."""

from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from task_summoner.events.bus import EventBus
from task_summoner.events.models import (
    AgentCompletedEvent,
    AgentMessageEvent,
    AgentStartedEvent,
    AgentToolUseEvent,
    BaseEvent,
    EventType,
    StateTransitionEvent,
    TicketErrorEvent,
)


class TestEventModels:
    def test_base_event_requires_fields(self):
        with pytest.raises(ValidationError):
            BaseEvent()

    def test_state_transition(self):
        e = StateTransitionEvent(
            ticket_key="TEST-1",
            old_state="QUEUED",
            new_state="PLANNING",
            trigger="start_planning",
        )
        assert e.event_type == EventType.STATE_TRANSITION
        assert e.timestamp is not None

    def test_agent_started(self):
        e = AgentStartedEvent(
            ticket_key="TEST-1",
            agent_name="planner",
            model="sonnet",
            max_turns=30,
            budget_usd=5.0,
        )
        assert e.agent_name == "planner"
        assert e.budget_usd == 5.0

    def test_agent_message(self):
        e = AgentMessageEvent(
            ticket_key="TEST-1",
            agent_name="planner",
            text="Hello world",
        )
        assert e.text == "Hello world"

    def test_agent_tool_use(self):
        e = AgentToolUseEvent(
            ticket_key="TEST-1",
            agent_name="implementer",
            tool_name="Bash",
            tool_input={"command": "ls"},
        )
        assert e.tool_name == "Bash"

    def test_agent_completed(self):
        e = AgentCompletedEvent(
            ticket_key="TEST-1",
            agent_name="planner",
            success=True,
            cost_usd=0.5,
            num_turns=3,
        )
        assert e.success
        assert e.cost_usd == 0.5

    def test_ticket_error(self):
        e = TicketErrorEvent(ticket_key="TEST-1", error="Something broke")
        assert e.event_type == EventType.TICKET_ERROR

    def test_serialization(self):
        e = AgentStartedEvent(
            ticket_key="TEST-1",
            agent_name="planner",
            model="sonnet",
        )
        d = e.model_dump(mode="json")
        assert d["event_type"] == "agent_started"
        assert d["ticket_key"] == "TEST-1"


class TestEventBus:
    async def test_emit_and_history(self):
        bus = EventBus()
        event = AgentStartedEvent(
            ticket_key="TEST-1",
            agent_name="planner",
            model="sonnet",
        )
        await bus.emit(event)
        assert len(bus.get_history()) == 1
        assert bus.get_history("TEST-1")[0].agent_name == "planner"

    async def test_history_filtered_by_ticket(self):
        bus = EventBus()
        await bus.emit(AgentStartedEvent(ticket_key="A-1", agent_name="planner", model="s"))
        await bus.emit(AgentStartedEvent(ticket_key="B-2", agent_name="impl", model="s"))

        assert len(bus.get_history("A-1")) == 1
        assert len(bus.get_history("B-2")) == 1
        assert len(bus.get_history()) == 2

    async def test_subscribe_receives_events(self):
        bus = EventBus()
        received = []

        async def consumer():
            async for event in bus.subscribe(include_history=False):
                received.append(event)
                if len(received) >= 2:
                    break

        task = asyncio.create_task(consumer())
        await asyncio.sleep(0.01)

        await bus.emit(AgentStartedEvent(ticket_key="T-1", agent_name="a", model="s"))
        await bus.emit(AgentMessageEvent(ticket_key="T-1", agent_name="a", text="hi"))

        await asyncio.wait_for(task, timeout=1.0)
        assert len(received) == 2

    async def test_subscribe_filtered(self):
        bus = EventBus()
        received = []

        async def consumer():
            async for event in bus.subscribe(ticket_key="A-1", include_history=False):
                received.append(event)
                if len(received) >= 1:
                    break

        task = asyncio.create_task(consumer())
        await asyncio.sleep(0.01)

        await bus.emit(AgentStartedEvent(ticket_key="B-2", agent_name="a", model="s"))
        await bus.emit(AgentStartedEvent(ticket_key="A-1", agent_name="b", model="s"))

        await asyncio.wait_for(task, timeout=1.0)
        assert len(received) == 1
        assert received[0].ticket_key == "A-1"

    async def test_history_limit(self):
        bus = EventBus(max_history=5)
        for i in range(10):
            await bus.emit(AgentMessageEvent(ticket_key="T-1", agent_name="a", text=f"msg{i}"))
        assert len(bus.get_history()) == 5

    async def test_subscriber_count(self):
        bus = EventBus()
        assert bus.subscriber_count == 0

        async def consumer():
            async for _ in bus.subscribe(include_history=False):
                break

        task = asyncio.create_task(consumer())
        await asyncio.sleep(0.01)
        assert bus.subscriber_count == 1

        await bus.emit(AgentStartedEvent(ticket_key="T-1", agent_name="a", model="s"))
        await asyncio.wait_for(task, timeout=1.0)
        await asyncio.sleep(0.01)
        assert bus.subscriber_count == 0
