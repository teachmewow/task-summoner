"""Event response schema.

Events are a discriminated union (AgentMessageEvent, StateTransitionEvent, etc.)
sharing `BaseEvent` fields. The API returns whichever subclass matches; the
client should switch on `event_type`.

We expose `BaseEvent` as the typed response model. `FastAPI` serializes
concrete subclasses via `model_dump`, so discriminator fields survive.
"""

from __future__ import annotations

from task_summoner.models.events import BaseEvent

EventResponse = BaseEvent

__all__ = ["EventResponse"]
