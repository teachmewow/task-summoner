"""JSON file persistence for ticket state.

Each ticket gets its own directory: artifacts/{TICKET-KEY}/state.json
Writes are atomic via `utils.atomic_write_json` (tmp + rename).
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import structlog

from task_summoner.core.state_machine import is_terminal, transition
from task_summoner.models import TicketContext
from task_summoner.utils import atomic_write_json, safe_load_json

log = structlog.get_logger()


class StateStore:
    def __init__(self, artifacts_dir: str | Path):
        self._root = Path(artifacts_dir)
        self._root.mkdir(parents=True, exist_ok=True)

    def _ticket_dir(self, ticket_key: str) -> Path:
        d = self._root / ticket_key
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _state_path(self, ticket_key: str) -> Path:
        return self._ticket_dir(ticket_key) / "state.json"

    def load(self, ticket_key: str) -> TicketContext | None:
        """Load ticket context from disk. Returns None if missing or corrupt."""
        data = safe_load_json(self._state_path(ticket_key))
        if data is None:
            return None
        try:
            return TicketContext.from_dict(data)
        except KeyError as e:
            log.error("Corrupt state file", ticket=ticket_key, error=str(e))
            return None

    def save(self, ctx: TicketContext) -> None:
        """Persist ticket context atomically."""
        ctx.updated_at = datetime.now(UTC).isoformat()
        atomic_write_json(self._state_path(ctx.ticket_key), ctx.to_dict())
        log.debug("State saved", ticket=ctx.ticket_key, state=ctx.state.value)

    def do_transition(self, ticket_key: str, trigger: str) -> TicketContext:
        """Load → transition → update timestamp → save. Raises on invalid transition."""
        ctx = self.load(ticket_key)
        if ctx is None:
            raise ValueError(f"No state found for {ticket_key}")

        old_state = ctx.state
        new_state = transition(ctx.state, trigger)
        ctx.state = new_state
        self.save(ctx)

        log.info(
            "State transition",
            ticket=ticket_key,
            old=old_state.value,
            trigger=trigger,
            new=new_state.value,
        )
        return ctx

    def list_active(self) -> list[TicketContext]:
        """All contexts where state is not terminal (DONE/FAILED)."""
        results = []
        for ticket_dir in self._iter_ticket_dirs():
            ctx = self.load(ticket_dir.name)
            if ctx and not is_terminal(ctx.state):
                results.append(ctx)
        return results

    def list_all(self) -> list[TicketContext]:
        """All contexts regardless of state."""
        results = []
        for ticket_dir in self._iter_ticket_dirs():
            ctx = self.load(ticket_dir.name)
            if ctx:
                results.append(ctx)
        return results

    def delete(self, ticket_key: str) -> bool:
        """Remove the on-disk state for a ticket. Returns True if it existed."""
        ticket_dir = self._root / ticket_key
        if not ticket_dir.exists():
            return False
        shutil.rmtree(ticket_dir)
        log.info("Ticket state deleted", ticket=ticket_key)
        return True

    def artifact_dir(self, ticket_key: str) -> Path:
        """Return the artifact directory for a ticket, creating if needed."""
        return self._ticket_dir(ticket_key)

    def _iter_ticket_dirs(self):
        if not self._root.exists():
            return
        for item in self._root.iterdir():
            if item.is_dir() and (item / "state.json").exists():
                yield item
