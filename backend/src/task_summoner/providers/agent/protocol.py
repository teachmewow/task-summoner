"""AgentProvider protocol — the contract all agent CLI providers must implement."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


class AgentEventType(str, Enum):
    """Types of events emitted during agent execution."""

    MESSAGE = "message"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    ERROR = "error"
    COMPLETED = "completed"


@dataclass
class AgentProfile:
    """Configuration for an agent run — model, budget, tools, plugins."""

    name: str
    model: str
    max_turns: int
    max_cost_usd: float
    tools: list[str] = field(default_factory=list)
    plugins: list[str] = field(default_factory=list)


@dataclass
class AgentEvent:
    """Event emitted during agent execution (for streaming to dashboard)."""

    type: AgentEventType
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    """Return value from an agent run."""

    success: bool
    output: str = ""
    artifacts: dict[str, Path] = field(default_factory=dict)
    cost_usd: float = 0.0
    turns_used: int = 0
    error: str | None = None


@runtime_checkable
class AgentProvider(Protocol):
    """Abstract interface for agent CLI providers (Claude Code, Codex, etc.)."""

    async def run(
        self,
        prompt: str,
        profile: AgentProfile,
        working_dir: Path,
        event_callback: Callable[[AgentEvent], None] | None = None,
    ) -> AgentResult:
        """Execute an agent with the given prompt and profile."""
        ...

    def supports_streaming(self) -> bool:
        """Whether this provider supports real-time event streaming."""
        ...

    def supports_tool_use(self) -> bool:
        """Whether this provider supports tool use (MCP, function calling, etc.)."""
        ...
