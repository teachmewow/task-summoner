"""Pydantic event models for the monitoring system."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class EventType(str, Enum):
    TICKET_DISCOVERED = "ticket_discovered"
    STATE_TRANSITION = "state_transition"
    AGENT_STARTED = "agent_started"
    AGENT_MESSAGE = "agent_message"
    AGENT_TOOL_USE = "agent_tool_use"
    AGENT_COMPLETED = "agent_completed"
    TICKET_ERROR = "ticket_error"
    APPROVAL_WAITING = "approval_waiting"
    APPROVAL_RECEIVED = "approval_received"


class BaseEvent(BaseModel):
    """Base event — all events share these fields."""

    event_type: EventType
    ticket_key: str
    timestamp: str = Field(default_factory=_now_iso)


class TicketDiscoveredEvent(BaseEvent):
    event_type: EventType = EventType.TICKET_DISCOVERED
    summary: str = ""
    labels: list[str] = Field(default_factory=list)


class StateTransitionEvent(BaseEvent):
    event_type: EventType = EventType.STATE_TRANSITION
    old_state: str
    new_state: str
    trigger: str


class AgentStartedEvent(BaseEvent):
    event_type: EventType = EventType.AGENT_STARTED
    agent_name: str  # "planner", "implementer", "evaluator"
    model: str = ""
    max_turns: int = 0
    budget_usd: float = 0.0


class AgentMessageEvent(BaseEvent):
    """Text output from the agent — streamed in real-time."""

    event_type: EventType = EventType.AGENT_MESSAGE
    agent_name: str
    text: str
    is_partial: bool = False  # True for streaming chunks


class AgentToolUseEvent(BaseEvent):
    """Agent invoked a tool (Read, Edit, Bash, etc.)."""

    event_type: EventType = EventType.AGENT_TOOL_USE
    agent_name: str
    tool_name: str
    tool_input: dict[str, Any] = Field(default_factory=dict)


class AgentCompletedEvent(BaseEvent):
    event_type: EventType = EventType.AGENT_COMPLETED
    agent_name: str
    success: bool
    cost_usd: float = 0.0
    num_turns: int = 0
    error: str | None = None


class TicketErrorEvent(BaseEvent):
    event_type: EventType = EventType.TICKET_ERROR
    error: str
    state: str = ""


class ApprovalWaitingEvent(BaseEvent):
    event_type: EventType = EventType.APPROVAL_WAITING
    plan_comment_id: str = ""


class ApprovalReceivedEvent(BaseEvent):
    event_type: EventType = EventType.APPROVAL_RECEIVED
    decision: str  # "approved" or "rejected"
    source: str  # "comment" or "emoji"
