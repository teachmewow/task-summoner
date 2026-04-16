"""JSON file persistence for ticket state.

Each ticket gets its own directory: artifacts/{TICKET-KEY}/state.json
Writes are atomic (temp file + rename) to survive crashes.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import structlog

from task_summoner.models import TicketContext, TicketState
from task_summoner.core.state_machine import InvalidTransitionError, is_terminal, transition

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
        """Load ticket context from disk. Returns None if not found."""
        path = self._state_path(ticket_key)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            return TicketContext.from_dict(data)
        except (json.JSONDecodeError, KeyError) as e:
            log.error("Corrupt state file", ticket=ticket_key, error=str(e))
            return None

    def save(self, ctx: TicketContext) -> None:
        """Atomic write: write to temp, then rename."""
        ctx.updated_at = datetime.now(timezone.utc).isoformat()
        path = self._state_path(ctx.ticket_key)
        data = json.dumps(ctx.to_dict(), indent=2)

        fd, tmp_path = tempfile.mkstemp(
            dir=self._ticket_dir(ctx.ticket_key), suffix=".tmp"
        )
        try:
            os.write(fd, data.encode())
            os.close(fd)
            os.rename(tmp_path, path)
        except Exception:
            os.close(fd) if not os.get_inheritable(fd) else None
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

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

    def artifact_dir(self, ticket_key: str) -> Path:
        """Return the artifact directory for a ticket, creating if needed."""
        return self._ticket_dir(ticket_key)

    def _iter_ticket_dirs(self):
        if not self._root.exists():
            return
        for item in self._root.iterdir():
            if item.is_dir() and (item / "state.json").exists():
                yield item
