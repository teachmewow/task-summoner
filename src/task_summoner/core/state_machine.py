"""Deterministic state machine — pure data, no I/O.

The orchestrator owns all trigger logic. The LLM never decides transitions.
"""

from __future__ import annotations

from task_summoner.models import TicketState


class InvalidTransitionError(Exception):
    """Raised when a trigger has no valid transition from the current state."""


# (current_state, trigger) → next_state
TRANSITIONS: dict[tuple[TicketState, str], TicketState] = {
    # --- Queued ---
    (TicketState.QUEUED, "start"): TicketState.CHECKING_DOC,

    # --- Doc phase ---
    (TicketState.CHECKING_DOC, "doc_exists"): TicketState.WAITING_DOC_REVIEW,
    (TicketState.CHECKING_DOC, "doc_needed"): TicketState.CREATING_DOC,
    (TicketState.CHECKING_DOC, "doc_not_needed"): TicketState.WAITING_DOC_REVIEW,

    (TicketState.CREATING_DOC, "doc_created"): TicketState.WAITING_DOC_REVIEW,
    (TicketState.CREATING_DOC, "doc_failed"): TicketState.FAILED,

    (TicketState.WAITING_DOC_REVIEW, "approved"): TicketState.PLANNING,
    (TicketState.WAITING_DOC_REVIEW, "retry"): TicketState.IMPROVING_DOC,

    (TicketState.IMPROVING_DOC, "improved"): TicketState.WAITING_DOC_REVIEW,
    (TicketState.IMPROVING_DOC, "improve_failed"): TicketState.FAILED,

    # --- Planning phase ---
    (TicketState.PLANNING, "plan_complete"): TicketState.WAITING_PLAN_REVIEW,
    (TicketState.PLANNING, "plan_failed"): TicketState.FAILED,

    (TicketState.WAITING_PLAN_REVIEW, "approved"): TicketState.IMPLEMENTING,
    (TicketState.WAITING_PLAN_REVIEW, "retry"): TicketState.PLANNING,

    # --- Implementation phase ---
    (TicketState.IMPLEMENTING, "mr_created"): TicketState.WAITING_MR_REVIEW,
    (TicketState.IMPLEMENTING, "impl_failed"): TicketState.FAILED,

    (TicketState.WAITING_MR_REVIEW, "approved"): TicketState.DONE,
    (TicketState.WAITING_MR_REVIEW, "retry"): TicketState.FIXING_MR,

    (TicketState.FIXING_MR, "fixed"): TicketState.WAITING_MR_REVIEW,
    (TicketState.FIXING_MR, "fix_failed"): TicketState.FAILED,

    # --- Recovery ---
    (TicketState.FAILED, "reset"): TicketState.QUEUED,
}

TERMINAL_STATES = frozenset({TicketState.DONE, TicketState.FAILED})

AGENT_STATES = frozenset({
    TicketState.CHECKING_DOC,
    TicketState.CREATING_DOC,
    TicketState.IMPROVING_DOC,
    TicketState.PLANNING,
    TicketState.IMPLEMENTING,
    TicketState.FIXING_MR,
})

APPROVAL_STATES = frozenset({
    TicketState.WAITING_DOC_REVIEW,
    TicketState.WAITING_PLAN_REVIEW,
    TicketState.WAITING_MR_REVIEW,
})


def transition(current: TicketState, trigger: str) -> TicketState:
    """Advance the state machine. Raises InvalidTransitionError if invalid."""
    key = (current, trigger)
    if key not in TRANSITIONS:
        raise InvalidTransitionError(
            f"No transition: {current.value} --({trigger})--> ???"
        )
    return TRANSITIONS[key]


def is_terminal(state: TicketState) -> bool:
    return state in TERMINAL_STATES


def is_agent_running(state: TicketState) -> bool:
    return state in AGENT_STATES


def is_approval_waiting(state: TicketState) -> bool:
    return state in APPROVAL_STATES
