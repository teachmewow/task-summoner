"""CodexAdapter — stub implementation of AgentProvider for the Codex CLI.

Not yet functional: proves the AgentProvider abstraction is sound and leaves
a clear extension point. Contributors can flesh this out when the Codex CLI
API stabilizes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from task_summoner.providers.agent.protocol import (
    AgentEvent,
    AgentProfile,
    AgentResult,
)
from task_summoner.providers.config import CodexConfig


class CodexAdapter:
    """AgentProvider stub for OpenAI Codex CLI. Not yet implemented."""

    def __init__(self, config: CodexConfig) -> None:
        if not config.api_key:
            raise ValueError("CodexConfig requires api_key")
        self._config = config

    def supports_streaming(self) -> bool:
        return False

    def supports_tool_use(self) -> bool:
        return True

    async def run(
        self,
        prompt: str,
        profile: AgentProfile,
        working_dir: Path,
        event_callback: Callable[[AgentEvent], None] | None = None,
    ) -> AgentResult:
        raise NotImplementedError("Codex support coming soon")
