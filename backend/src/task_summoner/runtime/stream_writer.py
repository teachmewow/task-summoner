"""Per-ticket append-only JSONL writer + in-process pubsub for live readers.

Each ticket gets its own ``artifacts/{KEY}/stream.jsonl`` — the agent's event
callback records one JSON line per event, so the file is always a replayable
transcript of what the Claude subprocess did. The file is opened in append
mode for each record so readers can safely re-open it concurrently.

In-process subscribers (the SSE endpoint) receive a copy of every record via
``broker.subscribe()``: the reader first re-plays the persisted file from
disk, then consumes ``broker.new_events`` to tail whatever the writer appends
while its connection is open. There is deliberately no cross-process fanout —
task-summoner is single-process, and the only reader is the bundled dashboard.

Format (one JSON object per line):

    {
        "ts":        "2026-04-19T15:45:12.345+00:00",
        "type":      "message" | "tool_use" | "tool_result" | "error" | "completed",
        "content":   str,
        "agent":     str,
        "state":     str,           // orchestrator state at record time (optional)
        "tool_name": str | null,
        "tool_input": dict | null,
        "tool_result": str | null,
        "is_error":  bool | null,
        "metadata":  dict
    }

Anything unknown goes into ``metadata`` to keep the frontend contract loose.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from task_summoner.providers.agent import AgentEvent, AgentEventType

log = structlog.get_logger()


STREAM_FILENAME = "stream.jsonl"


def stream_path(artifacts_dir: Path | str, ticket_key: str) -> Path:
    """Locate the stream.jsonl file for a ticket (directory may not exist yet)."""
    return Path(artifacts_dir) / ticket_key / STREAM_FILENAME


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def event_to_record(
    event: AgentEvent,
    *,
    agent_name: str | None = None,
    state: str | None = None,
) -> dict[str, Any]:
    """Serialize an AgentEvent into a JSONL-safe dict.

    The shape is stable across agent providers — Codex and future adapters
    emit the same `AgentEvent` dataclass, so the UI never learns what
    provider it's reading from.
    """
    meta = dict(event.metadata or {})
    record: dict[str, Any] = {
        "ts": _now_iso(),
        "type": event.type.value if isinstance(event.type, AgentEventType) else str(event.type),
        "content": event.content,
        "agent": agent_name or meta.pop("agent", ""),
        "tool_name": meta.pop("tool_name", None),
        "tool_input": meta.pop("tool_input", None),
        "tool_result": meta.pop("tool_result", None),
        "is_error": meta.pop("is_error", None),
    }
    tool_use_id = meta.pop("tool_use_id", None)
    if tool_use_id is not None:
        record["tool_use_id"] = tool_use_id
    if state is not None:
        record["state"] = state
    # Derive sensible defaults from event type for the UI.
    if record["type"] == AgentEventType.TOOL_USE.value and record["tool_name"] is None:
        record["tool_name"] = event.content or None
    record["metadata"] = meta
    return record


class _Broker:
    """In-process per-ticket fanout for live SSE subscribers.

    Kept separate from the writer so the writer can be used in tests without
    dragging in asyncio bookkeeping — anyone who needs live updates asks the
    broker for a subscription queue.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[dict[str, Any] | None]]] = {}
        self._terminal: set[str] = set()

    def publish(self, ticket_key: str, record: dict[str, Any]) -> None:
        for q in list(self._subscribers.get(ticket_key, [])):
            try:
                q.put_nowait(record)
            except asyncio.QueueFull:
                # Drop oldest to make room — viewers falling behind should not
                # back-pressure the agent. Writers pushing to disk are authoritative.
                try:
                    q.get_nowait()
                    q.put_nowait(record)
                except asyncio.QueueEmpty:
                    pass

    def close(self, ticket_key: str) -> None:
        """Signal to subscribers that the writer has finished this run.

        The current contract is lenient: ``close`` just signals end-of-dispatch
        so the SSE loop can choose to wrap up. Subsequent dispatches for the
        same ticket will re-open the file and publish again; readers that
        stayed connected keep receiving events.
        """
        self._terminal.add(ticket_key)
        for q in list(self._subscribers.get(ticket_key, [])):
            try:
                q.put_nowait(None)
            except asyncio.QueueFull:
                pass

    async def subscribe(
        self,
        ticket_key: str,
        *,
        maxsize: int = 1024,
    ) -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(maxsize=maxsize)
        self._subscribers.setdefault(ticket_key, []).append(queue)
        try:
            while True:
                item = await queue.get()
                if item is None:
                    # Writer signalled end-of-dispatch. Yield control so the
                    # endpoint can decide whether to stay open (follow a later
                    # dispatch) or close — we keep the subscription alive so a
                    # re-dispatch still reaches this reader.
                    continue
                yield item
        finally:
            queue_list = self._subscribers.get(ticket_key, [])
            if queue in queue_list:
                queue_list.remove(queue)
            if not queue_list:
                self._subscribers.pop(ticket_key, None)


_broker = _Broker()


def get_broker() -> _Broker:
    """Return the process-global broker. Tests inject their own by monkeypatching."""
    return _broker


class StreamWriter:
    """Append-only JSONL writer for one ticket.

    The same writer is reused across multiple state-handler runs for the same
    ticket (planning → implementing → review-fix, etc.) — every dispatch
    adds more lines to the same file, preserving a full per-ticket log.
    """

    def __init__(
        self,
        artifacts_dir: Path | str,
        ticket_key: str,
        *,
        broker: _Broker | None = None,
    ) -> None:
        self._path = stream_path(artifacts_dir, ticket_key)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._ticket_key = ticket_key
        self._broker = broker or get_broker()

    @property
    def path(self) -> Path:
        return self._path

    def record_dict(self, record: dict[str, Any]) -> None:
        """Append one already-serialized record. Fans out to live subscribers."""
        try:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except OSError:
            log.exception("stream_writer.write_failed", ticket=self._ticket_key)
            return
        self._broker.publish(self._ticket_key, record)

    def record(
        self,
        event: AgentEvent,
        *,
        agent_name: str | None = None,
        state: str | None = None,
    ) -> None:
        self.record_dict(event_to_record(event, agent_name=agent_name, state=state))

    def close(self) -> None:
        """Signal end-of-dispatch so long-poll SSE can unblock cleanly."""
        self._broker.close(self._ticket_key)


def replay(artifacts_dir: Path | str, ticket_key: str) -> list[dict[str, Any]]:
    """Return the full persisted stream for a ticket (empty list if none)."""
    path = stream_path(artifacts_dir, ticket_key)
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    log.warning("stream_writer.bad_line", ticket=ticket_key, line=line[:120])
    except OSError:
        log.exception("stream_writer.read_failed", ticket=ticket_key)
    return out
