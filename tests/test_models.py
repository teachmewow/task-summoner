"""Tests for Pydantic domain models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from task_summoner.models import AgentResult, Ticket, TicketContext, TicketState


class TestTicket:
    def test_valid_ticket(self):
        t = Ticket(key="LLMOPS-123", summary="Test ticket")
        assert t.key == "LLMOPS-123"
        assert t.project_key == "LLMOPS"
        assert t.description == ""
        assert t.labels == []

    def test_project_key_derived_from_key(self):
        t = Ticket(key="MLOPS-99", summary="Test")
        assert t.project_key == "MLOPS"

    def test_explicit_project_key_not_overwritten(self):
        t = Ticket(key="LLMOPS-1", summary="Test", project_key="CUSTOM")
        assert t.project_key == "CUSTOM"

    def test_invalid_key_rejected(self):
        with pytest.raises(ValidationError):
            Ticket(key="bad-key", summary="Test")

    def test_invalid_key_no_number(self):
        with pytest.raises(ValidationError):
            Ticket(key="LLMOPS-", summary="Test")

    def test_from_acli_json_full(self):
        data = {
            "key": "LLMOPS-99",
            "fields": {
                "summary": "Fix the thing",
                "description": "Details here",
                "status": {"name": "To Do"},
                "labels": [{"name": "task-summoner"}, {"name": "urgent"}],
                "assignee": {"displayName": "Matheus"},
            },
        }
        t = Ticket.from_acli_json(data)
        assert t.key == "LLMOPS-99"
        assert t.summary == "Fix the thing"
        assert t.description == "Details here"
        assert t.status == "To Do"
        assert t.labels == ["task-summoner", "urgent"]
        assert t.assignee == "Matheus"

    def test_from_acli_json_minimal(self):
        data = {"key": "TEST-1", "fields": {"summary": "Minimal"}}
        t = Ticket.from_acli_json(data)
        assert t.summary == "Minimal"
        assert t.labels == []

    def test_from_acli_json_adf_description(self):
        data = {
            "key": "TEST-1",
            "fields": {
                "summary": "ADF test",
                "description": {
                    "type": "doc",
                    "content": [
                        {"type": "paragraph", "content": [{"type": "text", "text": "Hello world"}]}
                    ],
                },
            },
        }
        t = Ticket.from_acli_json(data)
        assert "Hello world" in t.description

    def test_from_acli_json_string_labels(self):
        data = {"key": "TEST-1", "fields": {"summary": "Test", "labels": ["a", "b"]}}
        t = Ticket.from_acli_json(data)
        assert t.labels == ["a", "b"]


class TestTicketContext:
    def test_defaults(self):
        ctx = TicketContext(ticket_key="TEST-1", state=TicketState.QUEUED)
        assert ctx.retry_count == 0
        assert ctx.total_cost_usd == 0.0
        assert ctx.branch_name is None
        assert ctx.created_at is not None

    def test_invalid_ticket_key(self):
        with pytest.raises(ValidationError):
            TicketContext(ticket_key="bad", state=TicketState.QUEUED)

    def test_negative_retry_count_rejected(self):
        with pytest.raises(ValidationError):
            TicketContext(ticket_key="TEST-1", state=TicketState.QUEUED, retry_count=-1)

    def test_negative_cost_rejected(self):
        with pytest.raises(ValidationError):
            TicketContext(ticket_key="TEST-1", state=TicketState.QUEUED, total_cost_usd=-5.0)

    def test_invalid_mr_url_rejected(self):
        with pytest.raises(ValidationError):
            TicketContext(ticket_key="TEST-1", state=TicketState.QUEUED, mr_url="not-a-url")

    def test_valid_mr_url_accepted(self):
        ctx = TicketContext(
            ticket_key="TEST-1",
            state=TicketState.QUEUED,
            mr_url="https://gitlab.example.com/-/merge_requests/1",
        )
        assert ctx.mr_url is not None

    def test_none_mr_url_accepted(self):
        ctx = TicketContext(ticket_key="TEST-1", state=TicketState.QUEUED, mr_url=None)
        assert ctx.mr_url is None

    def test_serialization_roundtrip(self):
        ctx = TicketContext(
            ticket_key="LLMOPS-42",
            state=TicketState.IMPLEMENTING,
            branch_name="LLMOPS-42-fix-thing",
            retry_count=1,
            total_cost_usd=3.50,
        )
        d = ctx.to_dict()
        assert d["state"] == "IMPLEMENTING"
        assert d["ticket_key"] == "LLMOPS-42"

        ctx2 = TicketContext.from_dict(d)
        assert ctx2.state == TicketState.IMPLEMENTING
        assert ctx2.branch_name == "LLMOPS-42-fix-thing"
        assert ctx2.total_cost_usd == 3.50


class TestAgentResult:
    def test_success(self):
        r = AgentResult(success=True, output="done", cost_usd=1.5, num_turns=10)
        assert r.success
        assert r.cost_usd == 1.5

    def test_failure(self):
        r = AgentResult(success=False, error="Something broke")
        assert not r.success
        assert r.error == "Something broke"

    def test_negative_cost_rejected(self):
        with pytest.raises(ValidationError):
            AgentResult(success=True, cost_usd=-1.0)

    def test_negative_turns_rejected(self):
        with pytest.raises(ValidationError):
            AgentResult(success=True, num_turns=-1)

    def test_metadata(self):
        r = AgentResult(success=True, metadata={"mr_url": "https://gitlab.com/mr/1"})
        assert r.metadata["mr_url"] == "https://gitlab.com/mr/1"
