"""Tests for JSON file-based state persistence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from task_summoner.core import StateStore
from task_summoner.core.state_machine import InvalidTransitionError
from task_summoner.models import TicketContext, TicketState


class TestStateStore:
    def test_save_and_load(self, store: StateStore):
        ctx = TicketContext(ticket_key="TEST-1", state=TicketState.QUEUED)
        store.save(ctx)

        loaded = store.load("TEST-1")
        assert loaded is not None
        assert loaded.ticket_key == "TEST-1"
        assert loaded.state == TicketState.QUEUED

    def test_load_nonexistent_returns_none(self, store: StateStore):
        assert store.load("DOES-NOT-EXIST") is None

    def test_save_creates_directory(self, store: StateStore):
        ctx = TicketContext(ticket_key="NEW-1", state=TicketState.QUEUED)
        store.save(ctx)
        assert (Path(store._root) / "NEW-1" / "state.json").exists()

    def test_save_updates_timestamp(self, store: StateStore):
        ctx = TicketContext(ticket_key="TEST-1", state=TicketState.QUEUED)
        store.save(ctx)
        first_ts = store.load("TEST-1").updated_at

        ctx.retry_count = 1
        store.save(ctx)
        second_ts = store.load("TEST-1").updated_at
        assert second_ts >= first_ts

    def test_do_transition(self, store: StateStore):
        ctx = TicketContext(ticket_key="TEST-1", state=TicketState.QUEUED)
        store.save(ctx)

        result = store.do_transition("TEST-1", "no_doc_needed")
        assert result.state == TicketState.PLANNING

        loaded = store.load("TEST-1")
        assert loaded.state == TicketState.PLANNING

    def test_do_transition_invalid_raises(self, store: StateStore):
        ctx = TicketContext(ticket_key="TEST-1", state=TicketState.DONE)
        store.save(ctx)

        with pytest.raises(InvalidTransitionError):
            store.do_transition("TEST-1", "no_doc_needed")

    def test_do_transition_missing_ticket_raises(self, store: StateStore):
        with pytest.raises(ValueError, match="No state found"):
            store.do_transition("MISSING-1", "no_doc_needed")

    def test_list_active(self, store: StateStore):
        store.save(TicketContext(ticket_key="A-1", state=TicketState.QUEUED))
        store.save(TicketContext(ticket_key="B-2", state=TicketState.PLANNING))
        store.save(TicketContext(ticket_key="C-3", state=TicketState.DONE))
        store.save(TicketContext(ticket_key="D-4", state=TicketState.FAILED))

        active = store.list_active()
        active_keys = {c.ticket_key for c in active}
        assert active_keys == {"A-1", "B-2"}

    def test_list_all(self, store: StateStore):
        store.save(TicketContext(ticket_key="A-1", state=TicketState.QUEUED))
        store.save(TicketContext(ticket_key="B-2", state=TicketState.DONE))

        all_ctx = store.list_all()
        assert len(all_ctx) == 2

    def test_artifact_dir(self, store: StateStore):
        d = store.artifact_dir("TEST-1")
        assert d.exists()
        assert d.name == "TEST-1"

    def test_corrupt_json_returns_none(self, store: StateStore):
        ticket_dir = Path(store._root) / "BAD-1"
        ticket_dir.mkdir(parents=True)
        (ticket_dir / "state.json").write_text("{invalid json")
        assert store.load("BAD-1") is None

    def test_atomic_write_creates_valid_json(self, store: StateStore):
        ctx = TicketContext(ticket_key="TEST-1", state=TicketState.QUEUED)
        store.save(ctx)
        path = Path(store._root) / "TEST-1" / "state.json"
        data = json.loads(path.read_text())
        assert data["ticket_key"] == "TEST-1"
        assert data["state"] == "QUEUED"
