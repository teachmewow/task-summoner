"""Jira ↔ local state synchronization.

Discovery uses search results (lightweight, no full labels).
State recovery uses fetch_ticket (full labels) only for NEW tickets
without local state — not on every poll.
"""

from __future__ import annotations

import structlog

from task_summoner.events.bus import EventBus
from task_summoner.events.models import TicketDiscoveredEvent
from task_summoner.models import TicketContext, TicketState, branch_from_labels, state_from_labels
from task_summoner.core import StateStore
from task_summoner.tracker import JiraClient

log = structlog.get_logger()


class JiraSyncService:
    """Discovers new tickets and recovers state from Jira labels."""

    def __init__(self, jira: JiraClient, store: StateStore, bus: EventBus) -> None:
        self._jira = jira
        self._store = store
        self._bus = bus

    async def discover(self) -> list[TicketContext]:
        """Poll Jira for eligible tickets, enqueue new ones, return active contexts."""
        try:
            candidates = await self._jira.search_eligible()
        except Exception as e:
            log.error("Jira search failed", error=str(e))
            return self._store.list_active()

        for ticket in candidates:
            if self._store.load(ticket.key):
                continue  # already tracked

            # New ticket — fetch full details to get complete labels for recovery
            try:
                full_ticket = await self._jira.fetch_ticket(ticket.key)
            except Exception as e:
                log.warning("Could not fetch ticket for recovery", ticket=ticket.key, error=str(e))
                full_ticket = ticket

            jira_state = state_from_labels(full_ticket.labels)

            # Skip terminal tickets
            if jira_state in (TicketState.DONE, TicketState.FAILED):
                log.info("Skipping terminal ticket", ticket=ticket.key, state=jira_state.value)
                continue

            initial_state = jira_state or TicketState.QUEUED
            ctx = TicketContext(ticket_key=ticket.key, state=initial_state)

            # Recover branch name from Jira labels
            branch = branch_from_labels(full_ticket.labels)
            if branch:
                ctx.branch_name = branch

            self._store.save(ctx)

            await self._bus.emit(TicketDiscoveredEvent(
                ticket_key=ticket.key, summary=ticket.summary, labels=full_ticket.labels,
            ))
            log.info(
                "Ticket discovered",
                ticket=ticket.key,
                state=initial_state.value,
                recovered=jira_state is not None,
            )

        return self._store.list_active()
