"""Tests for ClaudeCodeAdapter — focus on AgentProvider contract compliance."""

from __future__ import annotations

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
