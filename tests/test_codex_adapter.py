"""Tests for CodexAdapter stub."""

from __future__ import annotations

import pytest

from task_summoner.providers.agent import (
    AgentProfile,
    AgentProvider,
    CodexAdapter,
)
from task_summoner.providers.config import CodexConfig


class TestCodexAdapter:
    def test_adapter_satisfies_protocol(self):
        adapter = CodexAdapter(CodexConfig(api_key="k"))
        assert isinstance(adapter, AgentProvider)

    def test_supports_streaming_returns_false(self):
        adapter = CodexAdapter(CodexConfig(api_key="k"))
        assert adapter.supports_streaming() is False

    def test_supports_tool_use_returns_true(self):
        adapter = CodexAdapter(CodexConfig(api_key="k"))
        assert adapter.supports_tool_use() is True

    def test_init_validates_api_key(self):
        with pytest.raises(ValueError, match="api_key"):
            CodexAdapter(CodexConfig(api_key=""))

    @pytest.mark.asyncio
    async def test_run_raises_not_implemented(self, tmp_path):
        adapter = CodexAdapter(CodexConfig(api_key="k"))
        profile = AgentProfile(name="standard", model="gpt", max_turns=1, max_cost_usd=1.0)
        with pytest.raises(NotImplementedError, match="coming soon"):
            await adapter.run("hello", profile, tmp_path)
