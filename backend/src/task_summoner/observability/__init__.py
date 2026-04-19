"""Observability — LangSmith tracing integration.

Tracing is OPT-IN. When `LANGCHAIN_TRACING_V2` and `LANGCHAIN_API_KEY` env vars
are not set, `traceable` becomes a no-op passthrough decorator with zero
overhead. See `tracing.py` for details and the README "Observability" section
for env var setup.
"""

from .tracing import (
    configure_claude_agent_sdk_tracing,
    is_tracing_enabled,
    repo_from_labels,
    state_trace_metadata,
    traceable,
)

__all__ = [
    "configure_claude_agent_sdk_tracing",
    "is_tracing_enabled",
    "repo_from_labels",
    "state_trace_metadata",
    "traceable",
]
