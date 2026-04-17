"""EventBus — async pub/sub for real-time event distribution.

Uses the Observer pattern. Components publish events, subscribers
(like the SSE endpoint) receive them via async generators.
"""

from __future__ import annotations

import asyncio

import structlog

from task_summoner.models.events import BaseEvent

log = structlog.get_logger()


class EventBus:
    """Central event bus — thread-safe async pub/sub.

    Publishers call `emit(event)`.
    Subscribers call `subscribe()` to get an async generator of events,
    optionally filtered by ticket_key.
    """

    def __init__(self, max_history: int = 500) -> None:
        self._subscribers: list[asyncio.Queue[BaseEvent]] = []
        self._history: list[BaseEvent] = []
        self._max_history = max_history
        self._lock = asyncio.Lock()

    async def emit(self, event: BaseEvent) -> None:
        """Publish an event to all subscribers."""
        async with self._lock:
            self._history.append(event)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history :]

            for queue in self._subscribers:
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    try:
                        queue.get_nowait()
                        queue.put_nowait(event)
                    except asyncio.QueueEmpty:
                        pass

        log.debug(
            "Event emitted",
            event_type=event.event_type.value,
            ticket=event.ticket_key,
        )

    async def subscribe(self, ticket_key: str | None = None, include_history: bool = True):
        """Async generator that yields events.

        Args:
            ticket_key: If set, only yield events for this ticket.
            include_history: If True, replay past events first.
        """
        queue: asyncio.Queue[BaseEvent] = asyncio.Queue(maxsize=1000)

        async with self._lock:
            self._subscribers.append(queue)

            if include_history:
                for event in self._history:
                    if ticket_key is None or event.ticket_key == ticket_key:
                        try:
                            queue.put_nowait(event)
                        except asyncio.QueueFull:
                            break

        try:
            while True:
                event = await queue.get()
                if ticket_key is None or event.ticket_key == ticket_key:
                    yield event
        finally:
            async with self._lock:
                self._subscribers.remove(queue)

    def get_history(self, ticket_key: str | None = None) -> list[BaseEvent]:
        """Get past events, optionally filtered by ticket."""
        if ticket_key is None:
            return list(self._history)
        return [e for e in self._history if e.ticket_key == ticket_key]

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)
