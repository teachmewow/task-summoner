"""FastAPI dependency injection helpers.

Route handlers read shared infrastructure (store, event bus, config path, config
status) via `Depends(get_*)`. The actual instances are attached to `app.state`
by the lifespan in `app.py`.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import Request

from task_summoner.api.schemas import ConfigStatus
from task_summoner.core import StateStore
from task_summoner.events.bus import EventBus


def get_store(request: Request) -> StateStore:
    return request.app.state.store


def get_event_bus(request: Request) -> EventBus:
    return request.app.state.event_bus


def get_config_path(request: Request) -> Path:
    return request.app.state.config_path


def get_config_status(request: Request) -> ConfigStatus:
    return ConfigStatus(
        configured=bool(request.app.state.configured),
        errors=list(request.app.state.config_errors or []),
    )
