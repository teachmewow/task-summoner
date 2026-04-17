"""Event bus infrastructure. Domain event models live in `models.events`."""

from .bus import EventBus

__all__ = ["EventBus"]
