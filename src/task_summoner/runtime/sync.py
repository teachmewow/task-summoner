"""Board ↔ local state synchronization.

Uses the provider-agnostic BoardProvider contract — works with any board
(Jira, Linear). Discovery uses search results (lightweight); state recovery
fetches full ticket details only for new tickets without local state.
"""

from __future__ import annotations

import structlog

from task_summoner.core import StateStore
from task_summoner.events.bus import EventBus
from task_summoner.models import (
    TicketContext,
    TicketState,
    branch_from_labels,
    state_from_labels,
)
from task_summoner.models.events import TicketDiscoveredEvent
from task_summoner.providers.board import BoardProvider

log = structlog.get_logger()


class BoardSyncService:
    """Discovers new tickets and recovers state from board labels."""

    def __init__(self, board: BoardProvider, store: StateStore, bus: EventBus) -> None:
        self._board = board
        self._store = store
        self._bus = bus

    async def discover(self) -> list[TicketContext]:
        """Poll the board for eligible tickets, enqueue new ones, return active contexts."""
        try:
            candidates = await self._board.search_eligible()
        except Exception as e:
            log.error("Board search failed", error=str(e))
            return self._store.list_active()

        for ticket in candidates:
            if self._store.load(ticket.key):
                continue

            try:
                full_ticket = await self._board.fetch_ticket(ticket.key)
            except Exception as e:
                log.warning(
                    "Could not fetch ticket for recovery",
                    ticket=ticket.key,
                    error=str(e),
                )
                full_ticket = ticket

            recovered_state = state_from_labels(full_ticket.labels)

            if recovered_state in (TicketState.DONE, TicketState.FAILED):
                log.info(
                    "Skipping terminal ticket",
                    ticket=ticket.key,
                    state=recovered_state.value,
                )
                continue

            initial_state = recovered_state or TicketState.QUEUED
            ctx = TicketContext(ticket_key=ticket.key, state=initial_state)

            branch = branch_from_labels(full_ticket.labels)
            if branch:
                ctx.branch_name = branch

            self._store.save(ctx)

            await self._bus.emit(
                TicketDiscoveredEvent(
                    ticket_key=ticket.key,
                    summary=ticket.summary,
                    labels=full_ticket.labels,
                )
            )
            log.info(
                "Ticket discovered",
                ticket=ticket.key,
                state=initial_state.value,
                recovered=recovered_state is not None,
            )

        return self._store.list_active()
