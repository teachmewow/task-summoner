"""Integration tests for /api/issues/{key}/events + /stream (ENG-121)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from task_summoner.api import app as app_module
from task_summoner.api.app import create_app
from task_summoner.api.routers.streams import generate_issue_sse
from task_summoner.core import StateStore
from task_summoner.runtime.stream_writer import StreamWriter, get_broker


@pytest.fixture
def client_and_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(app_module, "_WEB_DIST", tmp_path / "no_web_dist")
    app = create_app(config_path=tmp_path / "config.yaml")
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    store = StateStore(str(artifacts))
    with TestClient(app) as client:
        app.state.store = store
        yield client, store, artifacts


class TestReplayEndpoint:
    def test_events_endpoint_returns_persisted_stream(self, client_and_store):
        client, _store, artifacts = client_and_store
        writer = StreamWriter(artifacts, "ENG-121")
        from task_summoner.providers.agent import AgentEvent, AgentEventType

        writer.record(
            AgentEvent(type=AgentEventType.MESSAGE, content="planning", metadata={"agent": "p"}),
            state="planning",
        )
        writer.record(
            AgentEvent(
                type=AgentEventType.TOOL_USE,
                content="Read",
                metadata={
                    "agent": "p",
                    "tool_use_id": "t-1",
                    "tool_input": {"path": "plan.md"},
                },
            )
        )

        resp = client.get("/api/issues/ENG-121/events")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2
        assert body[0]["type"] == "message"
        assert body[0]["content"] == "planning"
        assert body[1]["type"] == "tool_use"
        assert body[1]["tool_name"] == "Read"

    def test_events_empty_when_no_stream(self, client_and_store):
        client, _store, _artifacts = client_and_store
        resp = client.get("/api/issues/NEVER-1/events")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_events_rejects_junk_key_shape(self, client_and_store):
        client, _store, _artifacts = client_and_store
        # Keys with characters outside [A-Za-z0-9_-] short-circuit to [] —
        # starlette has already blocked anything with a literal slash, so we
        # only need to guard against dots / spaces making it to disk.
        resp = client.get("/api/issues/..dots/events")
        assert resp.status_code == 200
        assert resp.json() == []


class TestSseEndpointWiring:
    """Smoke-test that the route is registered under /api/issues/{key}/stream.

    We don't open a live connection — TestClient buffers streaming responses
    and our endpoint never naturally closes, which would hang the test. The
    deep-iteration tests live in ``TestSseGenerator`` below and exercise the
    same coroutine without going through the HTTP layer.
    """

    def test_stream_route_is_registered(self, client_and_store):
        client, _store, _artifacts = client_and_store
        route_paths = [getattr(r, "path", None) for r in client.app.routes]
        assert "/api/issues/{key}/stream" in route_paths
        assert "/api/issues/{key}/events" in route_paths


class TestSseGenerator:
    """Direct tests for the SSE frame generator.

    We construct the async generator ourselves and iterate it with
    ``__anext__`` + asyncio timeouts — this cleanly cancels at the end of
    each test and doesn't depend on the HTTP layer buffering behaviour.
    """

    @pytest.mark.asyncio
    async def test_replays_persisted_records_on_connect(self, tmp_path: Path):
        artifacts = tmp_path / "artifacts"
        artifacts.mkdir()
        writer = StreamWriter(artifacts, "ENG-121")
        from task_summoner.providers.agent import AgentEvent, AgentEventType

        writer.record(AgentEvent(type=AgentEventType.MESSAGE, content="a", metadata={"agent": "x"}))
        writer.record(AgentEvent(type=AgentEventType.MESSAGE, content="b", metadata={"agent": "x"}))

        async def never_disconnected() -> bool:
            return False

        gen = generate_issue_sse(
            "ENG-121",
            artifacts=str(artifacts),
            is_disconnected=never_disconnected,
            poll_timeout=0.05,
        )
        try:
            first = await asyncio.wait_for(gen.__anext__(), timeout=1.0)
            second = await asyncio.wait_for(gen.__anext__(), timeout=1.0)
        finally:
            await gen.aclose()

        assert first.startswith("event: message\n")
        assert '"content": "a"' in first
        assert second.startswith("event: message\n")
        assert '"content": "b"' in second

    @pytest.mark.asyncio
    async def test_live_events_flow_to_subscriber(self, tmp_path: Path):
        artifacts = tmp_path / "artifacts"
        artifacts.mkdir()

        async def never_disconnected() -> bool:
            return False

        gen = generate_issue_sse(
            "ENG-121",
            artifacts=str(artifacts),
            is_disconnected=never_disconnected,
            poll_timeout=0.05,
        )
        try:
            # Schedule a publish after the generator has subscribed. We prime
            # the event loop by awaiting the first ``__anext__`` with a short
            # timeout — if no persisted records exist, this call parks on the
            # broker queue, at which point our background publish wakes it.
            async def publish_after_delay():
                await asyncio.sleep(0.1)
                get_broker().publish(
                    "ENG-121",
                    {
                        "type": "tool_use",
                        "content": "Bash",
                        "tool_name": "Bash",
                        "tool_input": {"command": "ls"},
                        "agent": "p",
                    },
                )

            pub = asyncio.create_task(publish_after_delay())
            frame = await asyncio.wait_for(gen.__anext__(), timeout=2.0)
            await pub
        finally:
            await gen.aclose()

        assert frame.startswith("event: tool_use\n")
        assert '"tool_name": "Bash"' in frame

    @pytest.mark.asyncio
    async def test_disconnect_flag_terminates_generator(self, tmp_path: Path):
        artifacts = tmp_path / "artifacts"
        artifacts.mkdir()

        disconnected = {"flag": False}

        async def is_disc() -> bool:
            return disconnected["flag"]

        gen = generate_issue_sse(
            "ENG-121",
            artifacts=str(artifacts),
            is_disconnected=is_disc,
            poll_timeout=0.05,
        )
        try:
            # Flip the flag, then drive the generator one step — it should
            # return immediately (StopAsyncIteration) rather than park on the
            # queue forever.
            disconnected["flag"] = True
            with pytest.raises(StopAsyncIteration):
                await asyncio.wait_for(gen.__anext__(), timeout=1.0)
        finally:
            await gen.aclose()

    @pytest.mark.asyncio
    async def test_frames_are_valid_sse_json(self, tmp_path: Path):
        artifacts = tmp_path / "artifacts"
        artifacts.mkdir()
        writer = StreamWriter(artifacts, "ENG-121")
        from task_summoner.providers.agent import AgentEvent, AgentEventType

        writer.record(
            AgentEvent(
                type=AgentEventType.TOOL_USE,
                content="Bash",
                metadata={
                    "agent": "p",
                    "tool_use_id": "t-1",
                    "tool_input": {"command": "echo hi"},
                },
            )
        )

        async def never() -> bool:
            return False

        gen = generate_issue_sse(
            "ENG-121",
            artifacts=str(artifacts),
            is_disconnected=never,
            poll_timeout=0.05,
        )
        try:
            frame = await asyncio.wait_for(gen.__anext__(), timeout=1.0)
        finally:
            await gen.aclose()

        # Frame shape: ``event: <type>\ndata: <json>\n\n``
        assert frame.startswith("event: tool_use\n")
        lines = [line for line in frame.splitlines() if line.startswith("data:")]
        assert len(lines) == 1
        payload = json.loads(lines[0][len("data: ") :])
        assert payload["tool_name"] == "Bash"
        assert payload["tool_input"] == {"command": "echo hi"}
