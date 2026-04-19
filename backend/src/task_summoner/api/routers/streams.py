"""Per-issue agent-activity replay + SSE tail.

Two endpoints:

* ``GET /api/issues/{key}/events`` — full persisted history as JSON.
* ``GET /api/issues/{key}/stream`` — SSE; replays history, then tails any
  events the writer appends while the connection is open.

The data source is ``artifacts/{KEY}/stream.jsonl`` (append-only JSONL).
Readers re-open the file on each request so they never race the writer.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from task_summoner.api.deps import get_store
from task_summoner.core import StateStore
from task_summoner.runtime.stream_writer import get_broker, replay

log = structlog.get_logger()

router = APIRouter(prefix="/api/issues", tags=["issue-streams"])


# Poll interval for the SSE tail loop — we check ``request.is_disconnected``
# at the top of each iteration, so this bounds how long the generator will
# stay parked after the client closes its tab. 1s is plenty for human UX and
# keeps tests snappy. Every `_KEEPALIVE_TICKS` timeouts we also emit a
# comment frame to survive idle-proxy disconnects.
_POLL_TIMEOUT_SECS = 1.0
_KEEPALIVE_TICKS = 25

_VALID_KEY_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")


def _validate_key(key: str) -> None:
    if not key or any(c not in _VALID_KEY_CHARS for c in key):
        # Keep this lax — FastAPI's own 404 path handles missing tickets; we
        # only reject anything that would traverse the filesystem.
        raise ValueError(f"Invalid issue key: {key!r}")


def _artifacts_root(store: StateStore) -> str:
    # StateStore exposes the root via the private attr; we treat it as part
    # of the contract (every test in the repo already relies on it).
    return str(store._root)  # noqa: SLF001 — intentional, single owner per process.


@router.get("/{key}/events", response_model=list[dict[str, Any]])
async def get_issue_events(
    key: str, store: StateStore = Depends(get_store)
) -> list[dict[str, Any]]:
    """Return the full persisted agent-event log for an issue.

    Empty list when the ticket has never dispatched or the file was deleted.
    """
    try:
        _validate_key(key)
    except ValueError:
        return []
    return replay(_artifacts_root(store), key)


async def generate_issue_sse(
    key: str,
    *,
    artifacts: str,
    is_disconnected: Any,
    poll_timeout: float = _POLL_TIMEOUT_SECS,
    keepalive_ticks: int = _KEEPALIVE_TICKS,
):
    """Yield SSE frames for a ticket (replay + live tail).

    Factored out of the endpoint so it can be unit-tested with a plain async
    generator, without fighting httpx's ASGITransport buffering (which doesn't
    expose chunk-by-chunk yields). ``is_disconnected`` is an awaitable that
    returns True when the client went away; in production it's bound to
    ``Request.is_disconnected``.
    """
    broker = get_broker()

    # Subscribe BEFORE reading the file so we don't miss anything appended
    # between read() and subscribe(). Duplicates on that boundary are filtered
    # by the client via the per-record ``ts`` field.
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(maxsize=1024)
    subs = broker._subscribers.setdefault(key, [])  # noqa: SLF001
    subs.append(queue)

    try:
        for record in replay(artifacts, key):
            if await is_disconnected():
                return
            yield _sse_frame(record)

        # Tail loop. Each iteration waits up to poll_timeout on the broker
        # queue; on timeout we re-check the disconnect flag so the generator
        # unblocks within ``poll_timeout`` seconds of the client closing the
        # tab. Every Nth timeout emits a keepalive comment so idle proxies
        # don't kill the connection.
        idle_ticks = 0
        while True:
            if await is_disconnected():
                return
            try:
                item = await asyncio.wait_for(queue.get(), timeout=poll_timeout)
            except TimeoutError:
                idle_ticks += 1
                if idle_ticks >= keepalive_ticks:
                    idle_ticks = 0
                    yield ": keepalive\n\n"
                continue
            idle_ticks = 0
            if item is None:
                # End-of-dispatch sentinel — keep the connection open so a
                # subsequent dispatch for the same ticket still reaches this
                # reader (re-dispatch is common during review loops).
                continue
            yield _sse_frame(item)
    finally:
        if queue in subs:
            subs.remove(queue)
        if not subs:
            broker._subscribers.pop(key, None)  # noqa: SLF001


@router.get("/{key}/stream")
async def stream_issue_events(
    key: str, request: Request, store: StateStore = Depends(get_store)
) -> StreamingResponse:
    """Replay persisted events, then tail live ones via in-process pubsub."""
    artifacts = _artifacts_root(store)

    async def _is_disconnected() -> bool:
        return await request.is_disconnected()

    return StreamingResponse(
        generate_issue_sse(
            key,
            artifacts=artifacts,
            is_disconnected=_is_disconnected,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _sse_frame(record: dict[str, Any]) -> str:
    event_type = str(record.get("type", "message"))
    return f"event: {event_type}\ndata: {json.dumps(record, default=str)}\n\n"
