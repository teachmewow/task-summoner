"""Tests for the thin Agent SDK wrapper."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from task_summoner.agents.options import AgentOptionsFactory
from task_summoner.agents.plugin_resolver import PluginMode, PluginResolver
from task_summoner.agents.runner import AgentRunner
from task_summoner.config import AgentConfig, TaskSummonerConfig


def _make_assistant_msg(text: str):
    from claude_agent_sdk import AssistantMessage, TextBlock
    return AssistantMessage(content=[TextBlock(text=text)], model="sonnet")


def _make_result_msg(*, cost: float = 0.0, turns: int = 0, is_error: bool = False, result: str = "done"):
    from claude_agent_sdk import ResultMessage
    return ResultMessage(
        subtype="result", duration_ms=100, duration_api_ms=80,
        is_error=is_error, num_turns=turns, session_id="test-session",
        total_cost_usd=cost, result=result,
    )


class TestAgentRunner:
    @pytest.fixture
    def runner(self, config) -> AgentRunner:
        resolver = PluginResolver(mode=PluginMode.INSTALLED)
        factory = AgentOptionsFactory(config, plugin_resolver=resolver)
        return AgentRunner(options_factory=factory)

    @pytest.fixture
    def agent_config(self) -> AgentConfig:
        return AgentConfig(
            enabled=True, model="sonnet", max_turns=5,
            max_budget_usd=1.0, tools=["Read"],
        )

    async def test_successful_run(self, runner, agent_config):
        async def fake_query(**kwargs):
            yield _make_assistant_msg("Hello from agent")
            yield _make_result_msg(cost=0.5, turns=3)

        with patch("task_summoner.agents.runner.query", side_effect=fake_query):
            result = await runner.run(
                prompt="test prompt",
                system_prompt="test system",
                cwd="/tmp",
                agent_config=agent_config,
            )

        assert result.success
        assert "Hello from agent" in result.output
        assert result.cost_usd == 0.5
        assert result.num_turns == 3

    async def test_multi_message_run(self, runner, agent_config):
        async def fake_query(**kwargs):
            yield _make_assistant_msg("Part 1")
            yield _make_assistant_msg("Part 2")
            yield _make_result_msg(cost=1.0, turns=5)

        with patch("task_summoner.agents.runner.query", side_effect=fake_query):
            result = await runner.run(
                prompt="test", system_prompt="test",
                cwd="/tmp", agent_config=agent_config,
            )

        assert result.success
        assert "Part 1" in result.output
        assert "Part 2" in result.output

    async def test_sdk_exception(self, runner, agent_config):
        async def failing_query(**kwargs):
            raise RuntimeError("SDK connection failed")
            yield  # noqa: unreachable

        with patch("task_summoner.agents.runner.query", side_effect=failing_query):
            result = await runner.run(
                prompt="test", system_prompt="test",
                cwd="/tmp", agent_config=agent_config,
            )

        assert not result.success
        assert "SDK connection failed" in result.error

    async def test_agent_returns_error(self, runner, agent_config):
        async def error_query(**kwargs):
            yield _make_result_msg(cost=0.1, turns=1, is_error=True, result="Failed")

        with patch("task_summoner.agents.runner.query", side_effect=error_query):
            result = await runner.run(
                prompt="test", system_prompt="test",
                cwd="/tmp", agent_config=agent_config,
            )

        assert not result.success
        assert result.error is not None
