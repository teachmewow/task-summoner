"""Task dispatcher — spawns agent tasks, collects results, applies transitions."""

from __future__ import annotations

import asyncio

import structlog

from task_summoner.core import StateStore
from task_summoner.events.bus import EventBus
from task_summoner.models import Ticket, TicketContext, TicketState
from task_summoner.models.events import StateTransitionEvent, TicketErrorEvent
from task_summoner.providers.board import BoardNotFoundError, BoardProvider
from task_summoner.states import StateServices
from task_summoner.states.base import BaseState

log = structlog.get_logger()

_SHUTDOWN_TIMEOUT = 30


class TaskDispatcher:
    """Dispatches tickets to state handlers and manages running tasks."""

    def __init__(
        self,
        states: dict[TicketState, BaseState],
        services: StateServices,
        store: StateStore,
        board: BoardProvider,
        bus: EventBus,
    ) -> None:
        self._states = states
        self._services = services
        self._store = store
        self._board = board
        self._bus = bus
        self._running: dict[str, asyncio.Task] = {}

    @property
    def running_keys(self) -> set[str]:
        return set(self._running.keys())

    async def dispatch_all(self, contexts: list[TicketContext]) -> None:
        await self._collect_completed()

        for ctx in contexts:
            if ctx.ticket_key in self._running:
                continue
            fresh = self._store.load(ctx.ticket_key)
            if not fresh:
                continue
            try:
                ticket = await self._board.fetch_ticket(fresh.ticket_key)
            except BoardNotFoundError as e:
                self._quarantine(fresh, str(e))
                continue
            except Exception as e:
                log.error(
                    "Failed to fetch ticket",
                    ticket=fresh.ticket_key,
                    error=str(e),
                )
                continue
            await self._dispatch_one(fresh, ticket)

    def _quarantine(self, ctx: TicketContext, reason: str) -> None:
        """Mark a ticket as FAILED so it stops being retried every poll cycle."""
        if ctx.state == TicketState.FAILED:
            return
        log.warning(
            "Ticket quarantined (not found on board)",
            ticket=ctx.ticket_key,
            previous_state=ctx.state.value,
            reason=reason,
        )
        ctx.error = f"Not reachable on board: {reason}"
        ctx.state = TicketState.FAILED
        self._store.save(ctx)

    def cancel_all(self) -> None:
        for key, task in self._running.items():
            if not task.done():
                task.cancel()
                log.info("Cancelled agent task", ticket=key)

    async def wait_all(self) -> None:
        if not self._running:
            return
        try:
            await asyncio.wait_for(
                asyncio.gather(*self._running.values(), return_exceptions=True),
                timeout=_SHUTDOWN_TIMEOUT,
            )
        except TimeoutError:
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

    async def _run_agent(
        self, ctx: TicketContext, ticket: Ticket, handler: BaseState
    ) -> tuple[str, TicketContext]:
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
            await self._bus.emit(
                StateTransitionEvent(
                    ticket_key=ctx.ticket_key,
                    old_state=old_state.value,
                    new_state=new_ctx.state.value,
                    trigger=trigger,
                )
            )
            await self._board.set_state_label(ctx.ticket_key, new_ctx.state)
        except Exception as e:
            log.error(
                "Transition failed",
                ticket=ctx.ticket_key,
                trigger=trigger,
                error=str(e),
            )
