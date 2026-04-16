"""Core state management — state machine transitions and JSON persistence."""

from .state_machine import InvalidTransitionError, is_terminal, transition
from .state_store import StateStore

__all__ = [
    "InvalidTransitionError",
    "StateStore",
    "is_terminal",
    "transition",
]
