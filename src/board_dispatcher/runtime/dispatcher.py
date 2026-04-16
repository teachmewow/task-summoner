"""Task dispatcher — spawns agent tasks, collects results, applies transitions.

Manages the asyncio.Task lifecycle for agent states and runs non-agent
states synchronously. Applies triggers to the state machine after completion.
"""

from __future__ import annotations

import asyncio

import structlog

from board_dispatcher.core import StateStore
from board_dispatcher.events.bus import EventBus
from board_dispatcher.events.models import StateTransitionEvent, TicketErrorEvent
from board_dispatcher.models import Ticket, TicketContext, TicketState
from board_dispatcher.states import StateServices
from board_dispatcher.states.base import BaseState
from board_dispatcher.tracker import JiraClient

log = structlog.get_logger()

_SHUTDOWN_TIMEOUT = 30


class TaskDispatcher:
    """Dispatches tickets to state handlers and manages running tasks."""

    def __init__(
        self,
        states: dict[TicketState, BaseState],
        services: StateServices,
        store: StateStore,
        jira: JiraClient,
        bus: EventBus,
    ) -> None:
        self._states = states
        self._services = services
        self._store = store
        self._jira = jira
        self._bus = bus
        self._running: dict[str, asyncio.Task] = {}

    @property
    def running_keys(self) -> set[str]:
        return set(self._running.keys())

    async def dispatch_all(self, contexts: list[TicketContext]) -> None:
        """Collect completed tasks, then dispatch all ready contexts."""
        await self._collect_completed()

        for ctx in contexts:
            if ctx.ticket_key in self._running:
                continue
            # Reload from store — _collect_completed may have transitioned this ticket
            fresh = self._store.load(ctx.ticket_key)
            if not fresh:
                continue
            try:
                ticket = await self._jira.fetch_ticket(fresh.ticket_key)
            except Exception as e:
                log.error("Failed to fetch ticket", ticket=fresh.ticket_key, error=str(e))
                continue
            await self._dispatch_one(fresh, ticket)

    def cancel_all(self) -> None:
        """Cancel all running agent tasks (used on force shutdown)."""
        for key, task in self._running.items():
            if not task.done():
                task.cancel()
                log.info("Cancelled agent task", ticket=key)

    async def wait_all(self) -> None:
        """Wait for running tasks to complete with timeout."""
        if not self._running:
            return
        try:
            await asyncio.wait_for(
                asyncio.gather(*self._running.values(), return_exceptions=True),
                timeout=_SHUTDOWN_TIMEOUT,
            )
        except asyncio.TimeoutError:
            log.warning("Shutdown timeout, cancelling remaining tasks")
            self.cancel_all()

    async def _dispatch_one(self, ctx: TicketContext, ticket: Ticket) -> None:
        handler: BaseState | None = self._states.get(ctx.state)
        if not handler:
            log.error("No handler for state", state=ctx.state.value, ticket=ctx.ticket_key)
            return

        if handler.requires_agent:
            self._running[ctx.ticket_key] = asyncio.create_task(
                self._run_agent(ctx, ticket, handler)
            )
        else:
            trigger = await handler.handle(ctx, ticket, self._services)
            await self._apply_trigger(ctx, trigger)

    async def _run_agent(self, ctx: TicketContext, ticket: Ticket, handler: BaseState) -> tuple[str, TicketContext]:
        trigger = await handler.handle(ctx, ticket, self._services)
        return trigger, ctx

    async def _collect_completed(self) -> None:
        completed = {k: t for k, t in self._running.items() if t.done()}
        for key, task in completed.items():
            del self._running[key]
            try:
                trigger, ctx = task.result()
                await self._apply_trigger(ctx, trigger)
            except asyncio.CancelledError:
                log.info("Agent task was cancelled", ticket=key)
            except Exception as e:
                log.error("Agent task crashed", ticket=key, error=str(e))
                await self._bus.emit(TicketErrorEvent(ticket_key=key, error=str(e)))
                ctx = self._store.load(key)
                if ctx:
                    ctx.error = str(e)
                    ctx.retry_count += 1
                    self._store.save(ctx)

    async def _apply_trigger(self, ctx: TicketContext, trigger: str) -> None:
        if trigger in ("_wait", "_noop", "_retry"):
            self._store.save(ctx)
            return
        try:
            old_state = ctx.state
            self._store.save(ctx)
            new_ctx = self._store.do_transition(ctx.ticket_key, trigger)
            await self._bus.emit(StateTransitionEvent(
                ticket_key=ctx.ticket_key,
                old_state=old_state.value,
                new_state=new_ctx.state.value,
                trigger=trigger,
            ))
            await self._jira.set_state_label(ctx.ticket_key, new_ctx.state.value)
        except Exception as e:
            log.error("Transition failed", ticket=ctx.ticket_key, trigger=trigger, error=str(e))
