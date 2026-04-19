"""Tests for ClaudeCodeAdapter — focus on AgentProvider contract compliance."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock

from task_summoner.providers.agent import (
    AgentEvent,
    AgentEventType,
    AgentProfile,
    AgentProvider,
    AgentResult,
    ClaudeCodeAdapter,
)
from task_summoner.providers.config import ClaudeCodeConfig


@pytest.fixture
def adapter() -> ClaudeCodeAdapter:
    return ClaudeCodeAdapter(ClaudeCodeConfig(api_key="k"))


@pytest.fixture
def profile() -> AgentProfile:
    return AgentProfile(
        name="standard",
        model="sonnet",
        max_turns=10,
        max_cost_usd=5.0,
        tools=["Read", "Bash"],
    )


class TestClaudeCodeAdapterContract:
    def test_adapter_satisfies_protocol(self, adapter):
        assert isinstance(adapter, AgentProvider)

    def test_supports_streaming_returns_true(self, adapter):
        assert adapter.supports_streaming() is True

    def test_supports_tool_use_returns_true(self, adapter):
        assert adapter.supports_tool_use() is True


class TestClaudeCodeAdapterPlugins:
    def test_installed_mode_returns_empty_plugin_list(self, profile):
        adapter = ClaudeCodeAdapter(ClaudeCodeConfig(api_key="k", plugin_mode="installed"))
        assert adapter._resolve_plugins(profile) == []

    def test_local_mode_returns_local_plugin_entry(self, profile, tmp_path):
        adapter = ClaudeCodeAdapter(
            ClaudeCodeConfig(api_key="k", plugin_mode="local", plugin_path=str(tmp_path))
        )
        plugins = adapter._resolve_plugins(profile)
        assert len(plugins) == 1
        assert plugins[0]["type"] == "local"
        assert plugins[0]["path"] == str(tmp_path.resolve())

    def test_local_mode_without_path_raises(self, profile):
        adapter = ClaudeCodeAdapter(ClaudeCodeConfig(api_key="k", plugin_mode="local"))
        with pytest.raises(ValueError, match="plugin_path"):
            adapter._resolve_plugins(profile)

    def test_unknown_plugin_mode_raises(self, profile):
        adapter = ClaudeCodeAdapter(ClaudeCodeConfig(api_key="k", plugin_mode="bogus"))
        with pytest.raises(ValueError, match="Unknown plugin_mode"):
            adapter._resolve_plugins(profile)


class TestClaudeCodeAdapterRun:
    @pytest.mark.asyncio
    async def test_run_returns_agent_result_on_success(self, adapter, profile, tmp_path):
        async def fake_query(prompt, options):
            yield AssistantMessage(content=[TextBlock(text="hello")], model="sonnet")
            yield ResultMessage(
                subtype="",
                duration_ms=0,
                duration_api_ms=0,
                is_error=False,
                num_turns=3,
                session_id="s",
                total_cost_usd=0.12,
            )

        with patch(
            "task_summoner.providers.agent.claude_code.adapter.query",
            fake_query,
        ):
            result = await adapter.run("do something", profile, tmp_path)

        assert isinstance(result, AgentResult)
        assert result.success is True
        assert result.output == "hello"
        assert result.turns_used == 3
        assert result.cost_usd == 0.12
        assert result.error is None

    @pytest.mark.asyncio
    async def test_run_surfaces_sdk_exception_as_error(self, adapter, profile, tmp_path):
        async def fake_query(prompt, options):
            raise RuntimeError("boom")
            yield  # pragma: no cover

        with patch(
            "task_summoner.providers.agent.claude_code.adapter.query",
            fake_query,
        ):
            result = await adapter.run("prompt", profile, tmp_path)

        assert result.success is False
        assert result.error == "boom"

    @pytest.mark.asyncio
    async def test_run_emits_events_through_callback(self, adapter, profile, tmp_path):
        async def fake_query(prompt, options):
            yield AssistantMessage(content=[TextBlock(text="msg")], model="sonnet")
            yield ResultMessage(
                subtype="",
                duration_ms=0,
                duration_api_ms=0,
                is_error=False,
                num_turns=1,
                session_id="s",
                total_cost_usd=0.0,
            )

        events: list[AgentEvent] = []
        with patch(
            "task_summoner.providers.agent.claude_code.adapter.query",
            fake_query,
        ):
            await adapter.run("p", profile, tmp_path, event_callback=events.append)

        event_types = [e.type for e in events]
        assert AgentEventType.MESSAGE in event_types
        assert AgentEventType.COMPLETED in event_types


class TestClaudeCodeAdapterMcpIsolation:
    """ENG-111: MCP servers must be passed explicitly, not inherited from global."""

    def test_build_options_includes_linear_mcp_when_key_set(self, profile, tmp_path, monkeypatch):
        monkeypatch.setenv("LINEAR_API_KEY", "lin_api_secret")
        adapter = ClaudeCodeAdapter(
            ClaudeCodeConfig(api_key="k"),
            board_team_id="team-abc",
        )
        options = adapter._build_options(profile, tmp_path)

        assert isinstance(options.mcp_servers, dict)
        assert "linear-server" in options.mcp_servers
        linear = options.mcp_servers["linear-server"]
        assert linear["type"] == "http"
        assert linear["url"] == "https://mcp.linear.app/mcp"
        assert linear["headers"]["Authorization"] == "Bearer lin_api_secret"

    def test_build_options_omits_linear_mcp_when_key_absent(self, profile, tmp_path, monkeypatch):
        monkeypatch.delenv("LINEAR_API_KEY", raising=False)
        adapter = ClaudeCodeAdapter(ClaudeCodeConfig(api_key="k"))
        options = adapter._build_options(profile, tmp_path)

        assert isinstance(options.mcp_servers, dict)
        assert "linear-server" not in options.mcp_servers

    def test_mcp_servers_is_dict_never_none(self, profile, tmp_path, monkeypatch):
        """Passing an empty dict still blocks global MCP inheritance."""
        monkeypatch.delenv("LINEAR_API_KEY", raising=False)
        adapter = ClaudeCodeAdapter(ClaudeCodeConfig(api_key="k"))
        options = adapter._build_options(profile, tmp_path)
        assert options.mcp_servers is not None
        assert isinstance(options.mcp_servers, dict)

    def test_forwarded_env_includes_linear_api_key(self, monkeypatch):
        monkeypatch.setenv("LINEAR_API_KEY", "lin_api_forwarded")
        adapter = ClaudeCodeAdapter(ClaudeCodeConfig(auth_method="personal_session"))
        env = adapter._build_env()
        assert env["LINEAR_API_KEY"] == "lin_api_forwarded"

    def test_forwarded_env_omits_linear_key_when_absent(self, monkeypatch):
        monkeypatch.delenv("LINEAR_API_KEY", raising=False)
        adapter = ClaudeCodeAdapter(ClaudeCodeConfig(auth_method="personal_session"))
        env = adapter._build_env()
        assert "LINEAR_API_KEY" not in env

    def test_system_prompt_contains_team_id_scoping(self, profile, tmp_path):
        adapter = ClaudeCodeAdapter(
            ClaudeCodeConfig(api_key="k"),
            board_team_id="team-uuid-42",
        )
        options = adapter._build_options(profile, tmp_path)
        assert options.system_prompt is not None
        assert "team-uuid-42" in options.system_prompt
        assert "ALWAYS" in options.system_prompt
        assert "team_id" in options.system_prompt

    def test_system_prompt_none_when_no_team_id(self, profile, tmp_path):
        adapter = ClaudeCodeAdapter(ClaudeCodeConfig(api_key="k"))
        options = adapter._build_options(profile, tmp_path)
        assert options.system_prompt is None


class TestClaudeCodeAdapterCancellation:
    """ENG-112: cancellation must close the SDK stream and propagate."""

    @pytest.fixture
    def adapter(self):
        return ClaudeCodeAdapter(ClaudeCodeConfig(api_key="k"))

    @pytest.fixture
    def profile(self):
        return AgentProfile(
            name="standard",
            model="sonnet",
            max_turns=10,
            max_cost_usd=5.0,
            tools=["Read"],
        )

    @pytest.mark.asyncio
    async def test_cancelled_error_is_propagated(self, adapter, profile, tmp_path):
        """If the caller cancels the task, CancelledError must bubble out."""
        aclose_called = {"count": 0}

        class FakeStream:
            def __aiter__(self):
                return self

            async def __anext__(self):
                # Block forever until cancelled.
                await asyncio.Event().wait()
                raise StopAsyncIteration

            async def aclose(self):
                aclose_called["count"] += 1

        def fake_query(prompt, options):
            return FakeStream()

        with patch(
            "task_summoner.providers.agent.claude_code.adapter.query",
            fake_query,
        ):
            task = asyncio.create_task(adapter.run("p", profile, tmp_path))
            # Give it a tick to enter the stream loop.
            await asyncio.sleep(0.05)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        assert aclose_called["count"] == 1, (
            "Adapter must call aclose() on cancellation to terminate subprocess"
        )

    @pytest.mark.asyncio
    async def test_aclose_called_on_normal_completion(self, adapter, profile, tmp_path):
        aclose_called = {"count": 0}

        class FakeStream:
            def __init__(self):
                self._yielded = False

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self._yielded:
                    raise StopAsyncIteration
                self._yielded = True
                return ResultMessage(
                    subtype="",
                    duration_ms=0,
                    duration_api_ms=0,
                    is_error=False,
                    num_turns=1,
                    session_id="s",
                    total_cost_usd=0.0,
                )

            async def aclose(self):
                aclose_called["count"] += 1

        def fake_query(prompt, options):
            return FakeStream()

        with patch(
            "task_summoner.providers.agent.claude_code.adapter.query",
            fake_query,
        ):
            result = await adapter.run("p", profile, tmp_path)
        assert result.success is True
        assert aclose_called["count"] == 1

    @pytest.mark.asyncio
    async def test_missing_aclose_does_not_crash(self, adapter, profile, tmp_path):
        """Older SDKs may not expose aclose on the returned iterator."""

        async def fake_query(prompt, options):
            yield ResultMessage(
                subtype="",
                duration_ms=0,
                duration_api_ms=0,
                is_error=False,
                num_turns=1,
                session_id="s",
                total_cost_usd=0.0,
            )

        with patch(
            "task_summoner.providers.agent.claude_code.adapter.query",
            fake_query,
        ):
            result = await adapter.run("p", profile, tmp_path)
        assert result.success is True
