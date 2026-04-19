"""Integration-ish tests: decorators on real state handlers.

Verify that when tracing is enabled, the metadata dicts produced by each
instrumented function actually contain the expected fields pulled from
runtime objects (TicketContext / Ticket). We mock the langsmith traceable
shim so no network calls happen.

Adapter-level instrumentation is now owned by the purpose-built
`langsmith.integrations.claude_agent_sdk` integration (wired at startup in
`api/app.py`), so we no longer assert manual `@traceable` spans around the
dispatch path — see `test_api_app_tracing.py` for the startup wiring test.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from task_summoner.models import Ticket, TicketContext, TicketState
from task_summoner.observability import tracing as tracing_mod


class _CapturingTraceable:
    """Replacement for langsmith.traceable that records every invocation."""

    def __init__(self) -> None:
        self.invocations: list[dict[str, Any]] = []

    def __call__(self, *args: Any, **opts: Any):
        name = opts.get("name")
        invocations = self.invocations

        def decorator(fn):
            import inspect

            if inspect.iscoroutinefunction(fn):

                async def wrapped(*a, **kw):
                    invocations.append({"name": name, "extra": kw.pop("langsmith_extra", {})})
                    return await fn(*a, **kw)

                return wrapped

            def wrapped_sync(*a, **kw):
                invocations.append({"name": name, "extra": kw.pop("langsmith_extra", {})})
                return fn(*a, **kw)

            return wrapped_sync

        return decorator


@pytest.fixture
def enable_tracing(monkeypatch: pytest.MonkeyPatch) -> _CapturingTraceable:
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    monkeypatch.setenv("LANGCHAIN_API_KEY", "k")
    fake = _CapturingTraceable()
    monkeypatch.setattr(tracing_mod, "_load_langsmith_traceable", lambda: fake)
    return fake


class TestPlanningStateTracing:
    async def test_handle_emits_metadata_when_tracing_enabled(
        self,
        enable_tracing: _CapturingTraceable,
        config,
        mock_services,
        tmp_path,
    ) -> None:
        # Re-import after env vars are set so decorators re-apply.
        # (Handlers are decorated at import time, so decorators were bound with
        # tracing DISABLED — we re-create the handler class module to rebind.)
        import importlib

        import task_summoner.states.planning as planning_mod

        importlib.reload(planning_mod)

        # Rebuild registry against reloaded module.
        import task_summoner.states as states_mod

        importlib.reload(states_mod)
        registry = states_mod.build_state_registry(config)
        handler = registry[TicketState.PLANNING]

        ticket = Ticket(
            key="ENG-99",
            summary="Test",
            labels=["task-summoner", "repo:task-summoner-plugin"],
        )
        ctx = TicketContext(
            ticket_key="ENG-99",
            state=TicketState.PLANNING,
            workspace_path=str(tmp_path / "ws"),
            branch_name="eng-99",
        )
        (tmp_path / "ws").mkdir()

        # Agent returns nothing useful → handler will retry; we don't care about
        # the control-flow outcome, only that tracing fired with metadata.
        from task_summoner.providers.agent import AgentResult

        mock_services.agent.run = AsyncMock(
            return_value=AgentResult(success=False, output="", error="nope")
        )

        await handler.handle(ctx, ticket, mock_services)

        names = [inv["name"] for inv in enable_tracing.invocations]
        assert "state.planning" in names
        assert "prompt.planning" in names

        state_invocation = next(
            inv for inv in enable_tracing.invocations if inv["name"] == "state.planning"
        )
        meta = state_invocation["extra"]["metadata"]
        assert meta["issue_id"] == "ENG-99"
        assert meta["skill"] == "task-summoner-workflows:ticket-plan"
        assert meta["repo"] == "task-summoner-plugin"
        assert meta["phase"] == "planning"


class TestTracingOffByDefault:
    """Sanity-check: with env vars unset, NONE of our @traceable decorators
    reach into langsmith. We spy on the module's `_load_langsmith_traceable`
    and confirm it's never called during a real handler run."""

    async def test_no_langsmith_calls_when_disabled(
        self,
        monkeypatch: pytest.MonkeyPatch,
        config,
        mock_services,
        tmp_path,
    ) -> None:
        # Ensure env is clean.
        monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
        monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)

        # Spy on the loader: should never be hit.
        call_count = {"n": 0}

        def loader() -> None:
            call_count["n"] += 1
            return None

        monkeypatch.setattr(tracing_mod, "_load_langsmith_traceable", loader)

        # Reload handler modules so the decorator re-evaluates against the
        # cleared env.
        import importlib

        import task_summoner.states as states_mod
        import task_summoner.states.planning as planning_mod

        importlib.reload(planning_mod)
        importlib.reload(states_mod)

        # The decorator short-circuits BEFORE calling _load_langsmith_traceable.
        assert call_count["n"] == 0

        # Exercise a handler. Still zero loader calls.
        registry = states_mod.build_state_registry(config)
        handler = registry[TicketState.PLANNING]
        ticket = Ticket(key="ENG-1", summary="s", labels=["repo:r"])
        ctx = TicketContext(
            ticket_key="ENG-1",
            state=TicketState.PLANNING,
            workspace_path=str(tmp_path / "ws"),
            branch_name="eng-1",
        )
        (tmp_path / "ws").mkdir()

        from task_summoner.providers.agent import AgentResult

        mock_services.agent.run = AsyncMock(
            return_value=AgentResult(success=False, output="", error="nope")
        )

        await handler.handle(ctx, ticket, mock_services)

        # Because tracing is off, the module should never import langsmith.
        assert call_count["n"] == 0
