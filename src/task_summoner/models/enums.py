"""Ticket lifecycle state enum and label-based recovery."""

from __future__ import annotations

from enum import Enum


class TicketState(str, Enum):
    """Full lifecycle states for the task-summoner."""

    # Initial
    QUEUED = "QUEUED"

    # Doc phase
    CHECKING_DOC = "CHECKING_DOC"
    CREATING_DOC = "CREATING_DOC"
    WAITING_DOC_REVIEW = "WAITING_DOC_REVIEW"
    IMPROVING_DOC = "IMPROVING_DOC"

    # Planning phase
    PLANNING = "PLANNING"
    WAITING_PLAN_REVIEW = "WAITING_PLAN_REVIEW"

    # Implementation phase
    IMPLEMENTING = "IMPLEMENTING"
    WAITING_MR_REVIEW = "WAITING_MR_REVIEW"
    FIXING_MR = "FIXING_MR"

    # Terminal
    DONE = "DONE"
    FAILED = "FAILED"


# Ordered from earliest to latest — used to pick the most advanced state from labels.
_STATE_ORDER: list[TicketState] = list(TicketState)


def state_from_labels(labels: list[str]) -> TicketState | None:
    """Extract the most advanced ts:<state> from Jira labels.

    Returns None if no task-summoner state labels are found.
    """
    found: list[TicketState] = []
    for label in labels:
        if label.startswith("ts:"):
            state_str = label.removeprefix("ts:").upper()
            try:
                found.append(TicketState(state_str))
            except ValueError:
                continue
    if not found:
        return None
    return max(found, key=lambda s: _STATE_ORDER.index(s))


def branch_from_labels(labels: list[str]) -> str | None:
    """Extract branch name from a branch:<name> Jira label.

    Returns None if no branch label is found.
    """
    for label in labels:
        if label.startswith("branch:"):
            return label.removeprefix("branch:")
    return None
