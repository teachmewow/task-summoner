"""Feedback extraction — parses human replies into decision + feedback text.

Isolates the parsing logic: given a raw comment body, determines the decision
(approve/retry) and extracts any feedback text that follows the keyword.

Examples:
    "lgtm"                          → (APPROVED, "")
    "lgtm but watch the edge cases" → (APPROVED, "but watch the edge cases")
    "retry the tests are failing"   → (RETRY, "the tests are failing")
    "fix error handling please"     → (RETRY, "error handling please")
    "random comment"                → (WAITING, "")
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ReactionDecision(str, Enum):
    APPROVED = "approved"
    RETRY = "retry"
    WAITING = "waiting"


_APPROVE_KEYWORDS = [
    "approved",
    "approve",
    "lgtm",
    "go ahead",
    "looks good",
    "ship it",
    "proceed",
]

_RETRY_KEYWORDS = [
    "retry",
    "redo",
    "fix",
    "changes needed",
    "update",
    "revise",
    "rejected",
    "reject",
]


@dataclass(frozen=True)
class ReactionResult:
    """Decision + optional feedback text from a human reply."""

    decision: ReactionDecision
    feedback: str = ""

    @property
    def has_feedback(self) -> bool:
        return bool(self.feedback.strip())


class FeedbackExtractor:
    """Parses a comment body into a ReactionResult (decision + feedback).

    The first matching keyword determines the decision.
    Everything after the keyword is captured as feedback text.
    """

    def extract(self, body: str) -> ReactionResult:
        """Parse a single reply body into decision + feedback."""
        if not body:
            return ReactionResult(decision=ReactionDecision.WAITING)

        body_stripped = body.strip()
        body_lower = body_stripped.lower()

        for kw in _APPROVE_KEYWORDS:
            pos = body_lower.find(kw)
            if pos != -1:
                after = body_stripped[pos + len(kw) :].strip()
                return ReactionResult(decision=ReactionDecision.APPROVED, feedback=after)

        for kw in _RETRY_KEYWORDS:
            pos = body_lower.find(kw)
            if pos != -1:
                after = body_stripped[pos + len(kw) :].strip()
                return ReactionResult(decision=ReactionDecision.RETRY, feedback=after)

        return ReactionResult(decision=ReactionDecision.WAITING)
