"""Tests for the LangSmith tracing wrapper (opt-in, no-op when disabled).

These tests cover three properties:

1. Tracing is off by default (env vars unset) → the wrapper is a passthrough,
   `langsmith.traceable` is never invoked, and the wrapped function runs
   exactly as if unannotated.

2. When env vars are set, metadata_fn values flow through to the
   `langsmith_extra` kwarg that langsmith.traceable receives. We mock
   `langsmith.traceable` to capture what it sees, rather than hitting the
   real SDK / network.

3. Exceptions raised by the wrapped function are NOT swallowed — they
   propagate through the tracing layer.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from task_summoner.models import TicketState
from task_summoner.observability import tracing as tracing_mod
from task_summoner.observability.tracing import (
    _skill_for_state,
    is_tracing_enabled,
    repo_from_labels,
    state_trace_metadata,
    traceable,
)

# -----------------------------------------------------------------
# Fixtures: clean env between tests so ordering doesn't leak state
# -----------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_tracing_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)


# -----------------------------------------------------------------
# is_tracing_enabled
# -----------------------------------------------------------------


class TestIsTracingEnabled:
    def test_false_when_no_env_vars(self) -> None:
        assert is_tracing_enabled() is False

    def test_false_when_only_flag_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
        assert is_tracing_enabled() is False

    def test_false_when_only_key_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LANGCHAIN_API_KEY", "k")
        assert is_tracing_enabled() is False

    def test_true_when_both_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
        monkeypatch.setenv("LANGCHAIN_API_KEY", "k")
        assert is_tracing_enabled() is True

    def test_false_when_flag_is_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LANGCHAIN_TRACING_V2", "0")
        monkeypatch.setenv("LANGCHAIN_API_KEY", "k")
        assert is_tracing_enabled() is False


# -----------------------------------------------------------------
# traceable: no-op behavior when disabled
# -----------------------------------------------------------------


class TestTraceableNoOp:
    def test_sync_function_runs_unchanged_when_tracing_off(self) -> None:
        calls: list[str] = []

        @traceable(run_type="chain", name="noop")
        def fn(x: int) -> int:
            calls.append("ran")
            return x * 2

        assert fn(3) == 6
        assert calls == ["ran"]

    async def test_async_function_runs_unchanged_when_tracing_off(self) -> None:
        @traceable(run_type="chain", name="noop")
        async def fn(x: int) -> int:
            return x + 1

        assert await fn(10) == 11

    def test_no_langsmith_import_when_disabled(self) -> None:
        """When tracing is off we must not touch the SDK — pretend it's missing.

        This proves zero overhead: even if `langsmith` weren't installed in
        this env, the decorator would still be applied successfully.
        """

        with patch.object(tracing_mod, "_load_langsmith_traceable") as loader:

            @traceable(run_type="chain", name="noop")
            def fn(x: int) -> int:
                return x

            assert fn(5) == 5
            loader.assert_not_called()

    def test_decorator_tolerates_missing_langsmith(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """If tracing is ON but langsmith isn't importable, we still no-op."""
        monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
        monkeypatch.setenv("LANGCHAIN_API_KEY", "k")
        monkeypatch.setattr(tracing_mod, "_load_langsmith_traceable", lambda: None)

        @traceable(run_type="chain", name="noop")
        def fn() -> str:
            return "ok"

        assert fn() == "ok"


# -----------------------------------------------------------------
# traceable: metadata injection when enabled
# -----------------------------------------------------------------


class _FakeTraceable:
    """Mimics the shape of langsmith.traceable for testing.

    `langsmith.traceable(**opts)` returns a decorator; applying it to `fn`
    returns a wrapper that, when called, forwards to `fn` and records the
    `langsmith_extra` kwarg for assertions.
    """

    def __init__(self) -> None:
        self.captured_opts: dict[str, Any] | None = None
        self.received_extras: list[dict[str, Any]] = []

    def __call__(self, *args: Any, **kwargs: Any):
        self.captured_opts = kwargs

        def decorator(fn):
            import asyncio
            import inspect

            if inspect.iscoroutinefunction(fn):

                async def async_wrapped(*a, **kw):
                    self.received_extras.append(kw.pop("langsmith_extra", {}))
                    return await fn(*a, **kw)

                return async_wrapped

            def sync_wrapped(*a, **kw):
                self.received_extras.append(kw.pop("langsmith_extra", {}))
                return fn(*a, **kw)

            # support both sync + async tests
            if asyncio.iscoroutinefunction(fn):

                async def async_wrapped_alt(*a, **kw):
                    self.received_extras.append(kw.pop("langsmith_extra", {}))
                    return await fn(*a, **kw)

                return async_wrapped_alt
            return sync_wrapped

        return decorator


class TestTraceableMetadataInjection:
    async def test_metadata_fn_is_forwarded_to_langsmith(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
        monkeypatch.setenv("LANGCHAIN_API_KEY", "k")

        fake = _FakeTraceable()
        monkeypatch.setattr(tracing_mod, "_load_langsmith_traceable", lambda: fake)

        @traceable(
            run_type="chain",
            name="test_chain",
            metadata_fn=lambda ticket_id, phase: {
                "issue_id": ticket_id,
                "phase": phase,
            },
        )
        async def fn(ticket_id: str, phase: str) -> str:
            return f"{ticket_id}/{phase}"

        result = await fn("ENG-99", "planning")

        assert result == "ENG-99/planning"
        assert fake.captured_opts == {"run_type": "chain", "name": "test_chain"}
        assert fake.received_extras == [{"metadata": {"issue_id": "ENG-99", "phase": "planning"}}]

    async def test_metadata_fn_error_does_not_break_call(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A broken metadata_fn must not corrupt the traced function's result."""
        monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
        monkeypatch.setenv("LANGCHAIN_API_KEY", "k")

        fake = _FakeTraceable()
        monkeypatch.setattr(tracing_mod, "_load_langsmith_traceable", lambda: fake)

        def boom(*args: Any, **kwargs: Any) -> dict[str, Any]:
            raise RuntimeError("metadata bug")

        @traceable(run_type="chain", name="test", metadata_fn=boom)
        async def fn() -> str:
            return "ok"

        # The wrapped call should still succeed.
        assert await fn() == "ok"
        # And the traced function should have been called with empty metadata.
        assert fake.received_extras == [{"metadata": {}}]

    async def test_exceptions_propagate_through_tracing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
        monkeypatch.setenv("LANGCHAIN_API_KEY", "k")

        fake = _FakeTraceable()
        monkeypatch.setattr(tracing_mod, "_load_langsmith_traceable", lambda: fake)

        @traceable(run_type="chain", name="boom")
        async def fn() -> None:
            raise ValueError("inner error")

        with pytest.raises(ValueError, match="inner error"):
            await fn()

    def test_sync_exceptions_propagate_through_tracing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
        monkeypatch.setenv("LANGCHAIN_API_KEY", "k")

        fake = _FakeTraceable()
        monkeypatch.setattr(tracing_mod, "_load_langsmith_traceable", lambda: fake)

        @traceable(run_type="chain", name="boom")
        def fn() -> None:
            raise RuntimeError("sync inner")

        with pytest.raises(RuntimeError, match="sync inner"):
            fn()


# -----------------------------------------------------------------
# Helper: repo_from_labels
# -----------------------------------------------------------------


class TestRepoFromLabels:
    def test_returns_repo_name(self) -> None:
        assert repo_from_labels(["task-summoner", "repo:foo"]) == "foo"

    def test_none_when_no_repo_label(self) -> None:
        assert repo_from_labels(["task-summoner"]) is None

    def test_empty_list(self) -> None:
        assert repo_from_labels([]) is None


# -----------------------------------------------------------------
# Helper: state_trace_metadata
# -----------------------------------------------------------------


class _FakeState:
    """Stand-in state handler whose class name is one we know."""

    def __init__(self, cls_name: str = "PlanningState") -> None:
        self.__class__.__name__ = cls_name


class _FakeCtx:
    def __init__(self, state: TicketState, retry: int = 0) -> None:
        self.state = state
        self.retry_count = retry


class _FakeTicket:
    def __init__(self, key: str, labels: list[str]) -> None:
        self.key = key
        self.labels = labels


class TestStateTraceMetadata:
    def test_emits_all_four_tags(self) -> None:
        meta = state_trace_metadata(
            _FakeState("PlanningState"),
            _FakeCtx(TicketState.PLANNING, retry=1),
            _FakeTicket("ENG-99", ["task-summoner", "repo:task-summoner-plugin"]),
            svc=None,
        )
        assert meta == {
            "issue_id": "ENG-99",
            "skill": "task-summoner-workflows:ticket-plan",
            "repo": "task-summoner-plugin",
            "phase": "planning",
            "retry_count": 1,
        }

    def test_unknown_state_class_returns_none_skill(self) -> None:
        meta = state_trace_metadata(
            _FakeState("MysteryState"),
            _FakeCtx(TicketState.PLANNING),
            _FakeTicket("ENG-1", []),
            svc=None,
        )
        assert meta["skill"] is None

    def test_skill_mapping_covers_all_agent_states(self) -> None:
        """All agent-driven states should resolve to a non-empty skill name."""
        for cls_name in (
            "CheckingDocState",
            "CreatingDocState",
            "ImprovingDocState",
            "PlanningState",
            "ImplementingState",
            "FixingMrState",
        ):
            assert _skill_for_state(_FakeState(cls_name)) is not None, cls_name
