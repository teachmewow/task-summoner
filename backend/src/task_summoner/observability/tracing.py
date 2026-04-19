"""LangSmith tracing — opt-in via env vars, no-op otherwise.

Tracing is enabled only when both `LANGCHAIN_TRACING_V2=true` and
`LANGCHAIN_API_KEY` are set in the environment. The `langsmith` SDK is a soft
dependency: when not installed (or env vars unset), `traceable` is a passthrough
decorator with zero overhead and zero behavior change.

When enabled, the purpose-built `langsmith.integrations.claude_agent_sdk`
integration (`configure_claude_agent_sdk()`) auto-instruments the Claude Agent
SDK — every tool use, message, and result becomes a span. The `@traceable`
decorators on state handlers and prompt builders still frame each run with
FSM-specific context (`state.<phase>`, `prompt.<phase>`), wrapping the SDK
integration's auto-generated spans.

Usage:

    from task_summoner.observability import traceable

    @traceable(run_type="chain", name="my_function")
    async def my_function(...) -> ...:
        ...

Metadata can be static or dynamic (callable returning a dict):

    @traceable(
        run_type="chain",
        name="agent_dispatch",
        metadata_fn=lambda self, ctx, ticket, ...: {
            "issue_id": ticket.key,
            "skill": agent_name,
            "repo": repo_from_labels(ticket.labels),
            "phase": ctx.state.value,
        },
    )

The wrapper never swallows exceptions: if the wrapped function raises, the
trace is closed with error status and the exception is re-raised.
"""

from __future__ import annotations

import functools
import os
from collections.abc import Callable
from typing import Any

_TRACING_ENV_VAR = "LANGCHAIN_TRACING_V2"
_API_KEY_ENV_VAR = "LANGCHAIN_API_KEY"


def is_tracing_enabled() -> bool:
    """True iff both LangSmith env vars are set (tracing opt-in)."""
    flag = os.environ.get(_TRACING_ENV_VAR, "").strip().lower()
    if flag not in ("true", "1", "yes"):
        return False
    return bool(os.environ.get(_API_KEY_ENV_VAR, "").strip())


def configure_claude_agent_sdk_tracing() -> bool:
    """Install LangSmith's purpose-built Claude Agent SDK integration.

    When tracing is enabled (env vars set) AND the integration module is
    importable, calls `configure_claude_agent_sdk()` to auto-instrument every
    agent query, tool use, and result as LangSmith spans.

    Returns True if the integration was configured, False otherwise. Safe to
    call at application startup regardless of env state — it short-circuits
    when tracing is off and swallows ImportError if the optional extra wasn't
    installed (`langsmith[claude-agent-sdk]`).
    """
    if not is_tracing_enabled():
        return False

    try:
        from langsmith.integrations.claude_agent_sdk import configure_claude_agent_sdk
    except ImportError:
        return False

    configure_claude_agent_sdk()
    return True


def _load_langsmith_traceable() -> Callable[..., Any] | None:
    """Try to import the real langsmith.traceable. None if unavailable."""
    try:
        from langsmith import traceable as _ls_traceable
    except ImportError:
        return None
    return _ls_traceable


def traceable(
    *decorator_args: Any,
    metadata_fn: Callable[..., dict[str, Any]] | None = None,
    **decorator_kwargs: Any,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """LangSmith `@traceable` wrapper that becomes a no-op when tracing is off.

    Args:
        *decorator_args / **decorator_kwargs: forwarded to langsmith.traceable
            (e.g. `run_type="chain"`, `name="agent_dispatch"`).
        metadata_fn: optional callable that receives the wrapped function's
            args/kwargs and returns a metadata dict for this invocation. Use
            this to pull metadata (issue_id, skill, repo, phase) from runtime
            objects like TicketContext.

    Behavior:
        - If tracing is disabled (env vars unset) OR `langsmith` is not
          installed: returns the function unchanged. No SDK imports, no calls.
        - Otherwise: returns `langsmith.traceable(...)` applied to the function.
          When `metadata_fn` is provided, we wrap the function to compute
          per-call metadata and inject it via the `langsmith_extra` kwarg so it
          attaches to the correct run.
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        if not is_tracing_enabled():
            return fn

        ls_traceable = _load_langsmith_traceable()
        if ls_traceable is None:
            return fn

        traced = ls_traceable(*decorator_args, **decorator_kwargs)(fn)

        if metadata_fn is None:
            return traced

        if _is_async_callable(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                extra = _safe_metadata(metadata_fn, args, kwargs)
                return await traced(*args, **kwargs, langsmith_extra=extra)

            return async_wrapper

        @functools.wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            extra = _safe_metadata(metadata_fn, args, kwargs)
            return traced(*args, **kwargs, langsmith_extra=extra)

        return sync_wrapper

    return decorator


def _is_async_callable(fn: Callable[..., Any]) -> bool:
    import asyncio
    import inspect

    if inspect.iscoroutinefunction(fn):
        return True
    if inspect.isasyncgenfunction(fn):
        return True
    return asyncio.iscoroutinefunction(fn)


def _safe_metadata(
    metadata_fn: Callable[..., dict[str, Any]],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> dict[str, Any]:
    """Compute metadata for a single traced call, swallowing errors.

    Metadata lookup should never break the wrapped function. If the metadata_fn
    raises (e.g. the caller's context has an unexpected shape), we silently
    fall back to an empty metadata dict rather than corrupting the call.
    """
    try:
        metadata = metadata_fn(*args, **kwargs) or {}
    except Exception:
        metadata = {}
    return {"metadata": metadata}


def repo_from_labels(labels: list[str]) -> str | None:
    """Extract the `repo:*` label value (used in trace metadata)."""
    for label in labels:
        if label.startswith("repo:"):
            return label[len("repo:") :]
    return None


def state_trace_metadata(
    self: Any,
    ctx: Any,
    ticket: Any,
    svc: Any,
) -> dict[str, Any]:
    """Metadata extractor for a state handler's `handle(ctx, ticket, svc)`.

    Used as `metadata_fn` when decorating state handlers. Pulls the four
    standard tags (issue_id, skill, repo, phase) from the runtime objects.
    Robust to missing attrs so tests with minimal fixtures don't crash.
    """
    phase = getattr(getattr(ctx, "state", None), "value", None) or _safe_attr(self, "state")
    if isinstance(phase, str):
        phase = phase.lower()
    labels = getattr(ticket, "labels", []) or []
    return {
        "issue_id": getattr(ticket, "key", None),
        "skill": _skill_for_state(self),
        "repo": repo_from_labels(labels),
        "phase": phase,
        "retry_count": getattr(ctx, "retry_count", 0),
    }


def _safe_attr(obj: Any, name: str) -> Any:
    try:
        value = getattr(obj, name, None)
        return getattr(value, "value", value)
    except Exception:
        return None


# Static mapping from state-handler class name -> plugin skill invoked.
# Keeps the observability module decoupled from the states module (no circular
# imports). Update when adding a new state handler that calls a new skill.
_SKILL_BY_STATE_CLASS: dict[str, str] = {
    "CheckingDocState": "task-summoner-workflows:ticket-plan",
    "CreatingDocState": "task-summoner-workflows:create-design-doc",
    "ImprovingDocState": "task-summoner-workflows:address-doc-feedback",
    "PlanningState": "task-summoner-workflows:ticket-plan",
    "ImplementingState": "task-summoner-workflows:ticket-implement",
    "FixingMrState": "task-summoner-workflows:review-pr",
}


def _skill_for_state(handler: Any) -> str | None:
    return _SKILL_BY_STATE_CLASS.get(type(handler).__name__)
