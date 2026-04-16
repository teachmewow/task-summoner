"""ClaudeCodeAdapter — implements AgentProvider via the Claude Agent SDK.

Translates between the provider-agnostic AgentProvider contract and the
Claude-specific SDK: maps AgentProfile to ClaudeAgentOptions, emits
generic AgentEvent instances (never raw SDK types) through event_callback.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

import structlog
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    query,
)

from task_summoner.providers.agent.protocol import (
    AgentEvent,
    AgentEventType,
    AgentProfile,
    AgentResult,
)
from task_summoner.providers.config import ClaudeCodeConfig

log = structlog.get_logger()

_FORWARDED_ENV_KEYS = [
    "ANTHROPIC_API_KEY",
    "ATLASSIAN_EMAIL",
    "ATLASSIAN_TOKEN",
    "SLACK_BOT_TOKEN",
    "SLACK_USER_ID",
]


class ClaudeCodeAdapter:
    """AgentProvider implementation backed by the Claude Agent SDK."""

    def __init__(self, config: ClaudeCodeConfig) -> None:
        self._config = config

    def supports_streaming(self) -> bool:
        return True

    def supports_tool_use(self) -> bool:
        return True

    async def run(
        self,
        prompt: str,
        profile: AgentProfile,
        working_dir: Path,
        event_callback: Callable[[AgentEvent], None] | None = None,
    ) -> AgentResult:
        options = self._build_options(profile, working_dir)

        log.info(
            "Agent starting",
            agent=profile.name,
            model=profile.model,
            max_turns=profile.max_turns,
            budget=profile.max_cost_usd,
            cwd=str(working_dir),
        )

        output_parts: list[str] = []
        cost = 0.0
        turns = 0
        error: str | None = None

        try:
            async for message in query(prompt=prompt, options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            output_parts.append(block.text)
                            self._emit(
                                event_callback,
                                AgentEvent(
                                    type=AgentEventType.MESSAGE,
                                    content=block.text,
                                    metadata={"agent": profile.name},
                                ),
                            )
                        elif isinstance(block, ToolUseBlock):
                            self._emit(
                                event_callback,
                                AgentEvent(
                                    type=AgentEventType.TOOL_USE,
                                    content=block.name,
                                    metadata={
                                        "agent": profile.name,
                                        "tool_input": _safe_tool_input(block.input),
                                    },
                                ),
                            )
                elif isinstance(message, ResultMessage):
                    cost = getattr(message, "total_cost_usd", 0.0) or 0.0
                    turns = getattr(message, "num_turns", 0) or 0
                    if getattr(message, "is_error", False):
                        error = getattr(message, "result", None) or "Agent error"
        except Exception as e:
            log.error("Agent SDK error", agent=profile.name, error=str(e))
            error = str(e)
            self._emit(
                event_callback,
                AgentEvent(
                    type=AgentEventType.ERROR,
                    content=error,
                    metadata={"agent": profile.name},
                ),
            )

        success = error is None
        self._emit(
            event_callback,
            AgentEvent(
                type=AgentEventType.COMPLETED,
                content="",
                metadata={
                    "agent": profile.name,
                    "success": success,
                    "cost_usd": cost,
                    "turns": turns,
                },
            ),
        )

        log.info(
            "Agent finished",
            agent=profile.name,
            turns=turns,
            cost=f"${cost:.4f}",
            success=success,
        )

        return AgentResult(
            success=success,
            output="\n".join(output_parts),
            cost_usd=cost,
            turns_used=turns,
            error=error,
        )

    def _build_options(
        self, profile: AgentProfile, working_dir: Path
    ) -> ClaudeAgentOptions:
        return ClaudeAgentOptions(
            cwd=str(working_dir),
            model=profile.model,
            max_turns=profile.max_turns,
            max_budget_usd=profile.max_cost_usd,
            allowed_tools=profile.tools,
            permission_mode="bypassPermissions",
            setting_sources=["user"],
            plugins=self._resolve_plugins(profile),
            env=self._build_env(),
        )

    def _resolve_plugins(self, profile: AgentProfile) -> list[dict[str, str]]:
        if self._config.plugin_mode == "installed":
            return []
        if self._config.plugin_mode == "local":
            if not self._config.plugin_path:
                raise ValueError(
                    "plugin_mode='local' requires plugin_path to be set"
                )
            resolved = str(Path(self._config.plugin_path).resolve())
            return [{"type": "local", "path": resolved}]
        raise ValueError(f"Unknown plugin_mode: {self._config.plugin_mode}")

    def _build_env(self) -> dict[str, str]:
        return {k: os.environ[k] for k in _FORWARDED_ENV_KEYS if os.environ.get(k)}

    def _emit(
        self,
        callback: Callable[[AgentEvent], None] | None,
        event: AgentEvent,
    ) -> None:
        if callback:
            callback(event)


def _safe_tool_input(inp: Any) -> dict[str, str]:
    if isinstance(inp, dict):
        return {
            k: (s[:200] + "..." if len(s := str(v)) > 200 else s)
            for k, v in inp.items()
        }
    return {"raw": str(inp)[:500]}
