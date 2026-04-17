"""Agent SDK runner — thin wrapper that streams events to the EventBus."""

from __future__ import annotations

import structlog
from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    query,
)

from task_summoner.config import AgentConfig
from task_summoner.events.bus import EventBus
from task_summoner.events.models import (
    AgentCompletedEvent,
    AgentMessageEvent,
    AgentStartedEvent,
    AgentToolUseEvent,
)
from task_summoner.models import AgentResult

from .options import AgentOptionsFactory

log = structlog.get_logger()


class AgentRunner:
    """Invokes Claude Agent SDK using shared options and streams events."""

    def __init__(
        self,
        options_factory: AgentOptionsFactory,
        event_bus: EventBus | None = None,
    ) -> None:
        self._factory = options_factory
        self._bus = event_bus

    async def _emit(self, event) -> None:
        if self._bus:
            await self._bus.emit(event)

    async def run(
        self,
        prompt: str,
        *,
        system_prompt: str,
        cwd: str,
        agent_config: AgentConfig,
        ticket_key: str = "",
        agent_name: str = "",
    ) -> AgentResult:
        options = self._factory.build(
            agent_config=agent_config,
            cwd=cwd,
            system_prompt=system_prompt,
        )

        log.info(
            "Agent starting",
            agent=agent_name,
            model=agent_config.model,
            max_turns=agent_config.max_turns,
            budget=agent_config.max_budget_usd,
            cwd=cwd,
        )

        await self._emit(
            AgentStartedEvent(
                ticket_key=ticket_key,
                agent_name=agent_name,
                model=agent_config.model,
                max_turns=agent_config.max_turns,
                budget_usd=agent_config.max_budget_usd,
            )
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
                            await self._emit(
                                AgentMessageEvent(
                                    ticket_key=ticket_key,
                                    agent_name=agent_name,
                                    text=block.text,
                                )
                            )
                        elif isinstance(block, ToolUseBlock):
                            await self._emit(
                                AgentToolUseEvent(
                                    ticket_key=ticket_key,
                                    agent_name=agent_name,
                                    tool_name=block.name,
                                    tool_input=_safe_tool_input(block.input),
                                )
                            )
                elif isinstance(message, ResultMessage):
                    cost = getattr(message, "total_cost_usd", 0.0) or 0.0
                    turns = getattr(message, "num_turns", 0) or 0
                    if getattr(message, "is_error", False):
                        error = getattr(message, "result", None) or "Agent error"

        except Exception as e:
            log.error("Agent SDK error", agent=agent_name, error=str(e))
            error = str(e)

        await self._emit(
            AgentCompletedEvent(
                ticket_key=ticket_key,
                agent_name=agent_name,
                success=error is None,
                cost_usd=cost,
                num_turns=turns,
                error=error,
            )
        )

        log.info("Agent finished", agent=agent_name, turns=turns, cost=f"${cost:.4f}")

        return AgentResult(
            success=error is None,
            output="\n".join(output_parts),
            cost_usd=cost,
            num_turns=turns,
            error=error,
        )


def _safe_tool_input(inp) -> dict:
    if isinstance(inp, dict):
        return {k: (s[:200] + "..." if len(s := str(v)) > 200 else s) for k, v in inp.items()}
    return {"raw": str(inp)[:500]}
