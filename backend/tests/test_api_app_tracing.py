"""Startup-wiring tests for LangSmith's Claude Agent SDK integration.

Verifies that `configure_claude_agent_sdk()` is called during the FastAPI
lifespan iff the opt-in env vars are set. When unset, the function must not be
invoked — preserving the zero-overhead default for users who don't use
LangSmith.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from task_summoner.api import app as app_module
from task_summoner.api.app import create_app
from task_summoner.observability import tracing as tracing_mod


@pytest.fixture
def isolated_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """App with no config (lifespan runs, but orchestrator stays unconfigured)."""
    monkeypatch.setattr(app_module, "_WEB_DIST", tmp_path / "no_web_dist")
    config_path = tmp_path / "config.yaml"
    return create_app(config_path=config_path)


class TestConfigureClaudeAgentSdkTracing:
    """Unit tests for the opt-in wrapper itself (no FastAPI involved)."""

    def test_returns_false_when_env_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
        monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
        assert tracing_mod.configure_claude_agent_sdk_tracing() is False

    def test_returns_false_when_only_flag_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
        monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
        assert tracing_mod.configure_claude_agent_sdk_tracing() is False

    def test_invokes_integration_when_env_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When env vars are set, the SDK integration must be invoked exactly once."""
        monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
        monkeypatch.setenv("LANGCHAIN_API_KEY", "k")

        call_count = {"n": 0}

        def fake_configure() -> None:
            call_count["n"] += 1

        # Inject a fake `langsmith.integrations.claude_agent_sdk` module so we
        # don't depend on the real package being importable in CI.
        import sys
        import types

        fake_mod = types.ModuleType("langsmith.integrations.claude_agent_sdk")
        fake_mod.configure_claude_agent_sdk = fake_configure  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "langsmith.integrations.claude_agent_sdk", fake_mod)

        assert tracing_mod.configure_claude_agent_sdk_tracing() is True
        assert call_count["n"] == 1

    def test_returns_false_when_integration_not_installed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If env is on but the optional extra wasn't installed, silently no-op."""
        monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
        monkeypatch.setenv("LANGCHAIN_API_KEY", "k")

        # Force ImportError by poisoning the module with a non-importable sentinel.
        import builtins

        real_import = builtins.__import__

        def fake_import(name: str, *args, **kwargs):
            if name == "langsmith.integrations.claude_agent_sdk":
                raise ImportError("extra not installed")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        assert tracing_mod.configure_claude_agent_sdk_tracing() is False


class TestLifespanStartupWiring:
    """End-to-end lifespan wiring: the FastAPI startup should trigger (or not
    trigger) the SDK integration based on env-var opt-in."""

    def test_startup_invokes_integration_when_env_set(
        self, monkeypatch: pytest.MonkeyPatch, isolated_app
    ) -> None:
        monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
        monkeypatch.setenv("LANGCHAIN_API_KEY", "k")

        call_count = {"n": 0}

        def fake_configure() -> bool:
            call_count["n"] += 1
            return True

        monkeypatch.setattr(app_module, "configure_claude_agent_sdk_tracing", fake_configure)

        with TestClient(isolated_app):
            pass

        assert call_count["n"] == 1

    def test_startup_does_not_invoke_integration_when_env_unset(
        self, monkeypatch: pytest.MonkeyPatch, isolated_app
    ) -> None:
        monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
        monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)

        # We replace the gated wrapper with a spy: the wrapper itself is always
        # called at startup, but because env is unset it must return False
        # *without* touching the SDK integration. The wrapper's own contract
        # (tested above) guarantees no SDK call — here we verify the lifespan
        # still runs cleanly.
        call_count = {"n": 0}

        def spy() -> bool:
            call_count["n"] += 1
            # Emulate the real wrapper's return value when env is unset.
            return tracing_mod.is_tracing_enabled()

        monkeypatch.setattr(app_module, "configure_claude_agent_sdk_tracing", spy)

        with TestClient(isolated_app):
            pass

        assert call_count["n"] == 1
        assert tracing_mod.is_tracing_enabled() is False
