"""Tests for the per-ticket stream writer (ENG-121)."""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path

import pytest

from task_summoner.providers.agent import AgentEvent, AgentEventType
from task_summoner.runtime.stream_writer import (
    StreamWriter,
    _Broker,
    event_to_record,
    replay,
    stream_path,
)


class TestEventToRecord:
    def test_tool_use_record_extracts_known_fields(self):
        ev = AgentEvent(
            type=AgentEventType.TOOL_USE,
            content="Read",
            metadata={
                "agent": "planner",
                "tool_use_id": "t-1",
                "tool_input": {"path": "plan.md"},
            },
        )
        record = event_to_record(ev, state="planning")

        assert record["type"] == "tool_use"
        assert record["agent"] == "planner"
        assert record["tool_name"] == "Read"
        assert record["tool_input"] == {"path": "plan.md"}
        assert record["state"] == "planning"
        assert record["tool_use_id"] == "t-1"
        # Claimed fields are removed from the freeform metadata bag.
        assert "tool_input" not in record["metadata"]
        assert "tool_use_id" not in record["metadata"]

    def test_tool_result_record_carries_payload(self):
        ev = AgentEvent(
            type=AgentEventType.TOOL_RESULT,
            content="Read",
            metadata={
                "agent": "planner",
                "tool_use_id": "t-1",
                "tool_name": "Read",
                "tool_result": "file contents",
                "is_error": False,
            },
        )
        record = event_to_record(ev)

        assert record["type"] == "tool_result"
        assert record["tool_result"] == "file contents"
        assert record["tool_name"] == "Read"
        assert record["is_error"] is False

    def test_message_record_shape(self):
        ev = AgentEvent(
            type=AgentEventType.MESSAGE,
            content="planning the change",
            metadata={"agent": "planner"},
        )
        record = event_to_record(ev)
        assert record["type"] == "message"
        assert record["content"] == "planning the change"
        assert record["agent"] == "planner"
        assert record["tool_name"] is None


class TestStreamWriter:
    def test_appends_jsonl_and_creates_dir(self, tmp_path: Path):
        writer = StreamWriter(tmp_path / "artifacts", "ENG-121")
        writer.record(
            AgentEvent(
                type=AgentEventType.MESSAGE,
                content="hello",
                metadata={"agent": "planner"},
            ),
            state="planning",
        )
        writer.record(
            AgentEvent(
                type=AgentEventType.TOOL_USE,
                content="Read",
                metadata={"agent": "planner", "tool_input": {"path": "x.md"}},
            ),
        )

        path = stream_path(tmp_path / "artifacts", "ENG-121")
        assert path.exists()
        lines = path.read_text().strip().splitlines()
        assert len(lines) == 2
        first = json.loads(lines[0])
        assert first["type"] == "message"
        assert first["content"] == "hello"
        assert first["state"] == "planning"
        second = json.loads(lines[1])
        assert second["type"] == "tool_use"
        assert second["tool_name"] == "Read"

    def test_replay_returns_parsed_records(self, tmp_path: Path):
        writer = StreamWriter(tmp_path / "artifacts", "ENG-121")
        for i in range(3):
            writer.record(
                AgentEvent(
                    type=AgentEventType.MESSAGE,
                    content=f"msg-{i}",
                    metadata={"agent": "planner"},
                )
            )
        records = replay(tmp_path / "artifacts", "ENG-121")
        assert [r["content"] for r in records] == ["msg-0", "msg-1", "msg-2"]

    def test_replay_missing_file_is_empty(self, tmp_path: Path):
        assert replay(tmp_path / "artifacts", "NEVER-1") == []

    def test_replay_skips_bad_lines(self, tmp_path: Path):
        path = stream_path(tmp_path / "artifacts", "ENG-121")
        path.parent.mkdir(parents=True)
        path.write_text(
            '{"type":"message","content":"ok","agent":"a"}\n'
            "not json at all\n"
            '{"type":"message","content":"also ok","agent":"a"}\n'
        )
        records = replay(tmp_path / "artifacts", "ENG-121")
        assert [r["content"] for r in records] == ["ok", "also ok"]

    def test_concurrent_appenders_and_reader_dont_corrupt(self, tmp_path: Path):
        """Multiple writers appending alongside a reader yields well-formed JSONL.

        Python file-mode ``a`` is atomic for writes ≤ PIPE_BUF on POSIX for a
        single line, which is what we rely on — the test guards that behaviour
        end-to-end so a future refactor can't regress it silently.
        """
        writer = StreamWriter(tmp_path / "artifacts", "ENG-121")

        def _write(worker_id: int, count: int):
            for i in range(count):
                writer.record(
                    AgentEvent(
                        type=AgentEventType.MESSAGE,
                        content=f"w{worker_id}-{i}",
                        metadata={"agent": "planner"},
                    )
                )

        reader_snapshots: list[list[dict]] = []

        def _read():
            # Interleave reads with the writers to simulate the SSE endpoint
            # re-replaying during a live dispatch.
            for _ in range(10):
                reader_snapshots.append(replay(tmp_path / "artifacts", "ENG-121"))

        workers = [threading.Thread(target=_write, args=(i, 50)) for i in range(4)]
        reader = threading.Thread(target=_read)
        for w in workers:
            w.start()
        reader.start()
        for w in workers:
            w.join()
        reader.join()

        final = replay(tmp_path / "artifacts", "ENG-121")
        assert len(final) == 4 * 50
        # Every reader snapshot must have been valid JSONL (i.e. no partial
        # lines seen). ``replay`` skips bad lines silently, so if the byte
        # stream was ever torn we'd observe a count dropped below what was
        # physically in the file — every snapshot should be monotonic.
        prev = 0
        for snap in reader_snapshots:
            assert len(snap) >= prev
            prev = len(snap)


class TestBrokerAndLiveTail:
    @pytest.mark.asyncio
    async def test_publish_reaches_subscriber(self):
        broker = _Broker()
        writer = StreamWriter.__new__(StreamWriter)  # bypass __init__ for in-mem test
        writer._path = Path("/tmp/never-used-by-this-test.jsonl")
        writer._ticket_key = "ENG-121"
        writer._broker = broker

        # Stand up a subscriber BEFORE publishing so it must receive the event.
        received: list[dict] = []
        stop = asyncio.Event()

        async def consumer():
            async for record in broker.subscribe("ENG-121"):
                received.append(record)
                if len(received) >= 2:
                    stop.set()
                    break

        task = asyncio.create_task(consumer())
        await asyncio.sleep(0.01)

        broker.publish("ENG-121", {"type": "message", "content": "a"})
        broker.publish("ENG-121", {"type": "message", "content": "b"})

        await asyncio.wait_for(stop.wait(), timeout=1.0)
        task.cancel()
        assert [r["content"] for r in received] == ["a", "b"]

    @pytest.mark.asyncio
    async def test_subscribers_filtered_by_ticket_key(self):
        broker = _Broker()
        seen: list[dict] = []

        async def consumer():
            async for record in broker.subscribe("A-1"):
                seen.append(record)
                if len(seen) >= 1:
                    break

        task = asyncio.create_task(consumer())
        await asyncio.sleep(0.01)

        broker.publish("B-2", {"type": "message", "content": "wrong"})
        broker.publish("A-1", {"type": "message", "content": "right"})

        await asyncio.wait_for(task, timeout=1.0)
        assert [r["content"] for r in seen] == ["right"]
