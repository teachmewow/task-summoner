"""Tests for the deterministic state machine."""

from __future__ import annotations

import pytest

from board_dispatcher.models import TicketState
from board_dispatcher.core.state_machine import (
    InvalidTransitionError,
    is_agent_running,
    is_approval_waiting,
    is_terminal,
    transition,
)


class TestTransition:
    @pytest.mark.parametrize(
        "current, trigger, expected",
        [
            # Queued
            (TicketState.QUEUED, "start", TicketState.CHECKING_DOC),
            # Doc phase
            (TicketState.CHECKING_DOC, "doc_exists", TicketState.WAITING_DOC_REVIEW),
            (TicketState.CHECKING_DOC, "doc_needed", TicketState.CREATING_DOC),
            (TicketState.CHECKING_DOC, "doc_not_needed", TicketState.WAITING_DOC_REVIEW),
            (TicketState.CREATING_DOC, "doc_created", TicketState.WAITING_DOC_REVIEW),
            (TicketState.CREATING_DOC, "doc_failed", TicketState.FAILED),
            (TicketState.WAITING_DOC_REVIEW, "approved", TicketState.PLANNING),
            (TicketState.WAITING_DOC_REVIEW, "retry", TicketState.IMPROVING_DOC),
            (TicketState.IMPROVING_DOC, "improved", TicketState.WAITING_DOC_REVIEW),
            (TicketState.IMPROVING_DOC, "improve_failed", TicketState.FAILED),
            # Planning phase
            (TicketState.PLANNING, "plan_complete", TicketState.WAITING_PLAN_REVIEW),
            (TicketState.PLANNING, "plan_failed", TicketState.FAILED),
            (TicketState.WAITING_PLAN_REVIEW, "approved", TicketState.IMPLEMENTING),
            (TicketState.WAITING_PLAN_REVIEW, "retry", TicketState.PLANNING),
            # Implementation phase
            (TicketState.IMPLEMENTING, "mr_created", TicketState.WAITING_MR_REVIEW),
            (TicketState.IMPLEMENTING, "impl_failed", TicketState.FAILED),
            (TicketState.WAITING_MR_REVIEW, "approved", TicketState.DONE),
            (TicketState.WAITING_MR_REVIEW, "retry", TicketState.FIXING_MR),
            (TicketState.FIXING_MR, "fixed", TicketState.WAITING_MR_REVIEW),
            (TicketState.FIXING_MR, "fix_failed", TicketState.FAILED),
            # Recovery
            (TicketState.FAILED, "reset", TicketState.QUEUED),
        ],
    )
    def test_valid_transitions(self, current, trigger, expected):
        assert transition(current, trigger) == expected

    def test_invalid_transition_raises(self):
        with pytest.raises(InvalidTransitionError):
            transition(TicketState.DONE, "start")

    def test_invalid_trigger_raises(self):
        with pytest.raises(InvalidTransitionError):
            transition(TicketState.QUEUED, "nonexistent")


class TestStatePredicates:
    def test_terminal_states(self):
        assert is_terminal(TicketState.DONE)
        assert is_terminal(TicketState.FAILED)
        assert not is_terminal(TicketState.PLANNING)

    def test_agent_states(self):
        for s in [TicketState.CHECKING_DOC, TicketState.CREATING_DOC, TicketState.IMPROVING_DOC,
                  TicketState.PLANNING, TicketState.IMPLEMENTING, TicketState.FIXING_MR]:
            assert is_agent_running(s), f"{s} should be agent state"

    def test_non_agent_states(self):
        for s in [TicketState.QUEUED, TicketState.WAITING_DOC_REVIEW,
                  TicketState.WAITING_PLAN_REVIEW, TicketState.WAITING_MR_REVIEW,
                  TicketState.DONE, TicketState.FAILED]:
            assert not is_agent_running(s), f"{s} should NOT be agent state"

    def test_approval_states(self):
        for s in [TicketState.WAITING_DOC_REVIEW, TicketState.WAITING_PLAN_REVIEW,
                  TicketState.WAITING_MR_REVIEW]:
            assert is_approval_waiting(s), f"{s} should be approval state"
