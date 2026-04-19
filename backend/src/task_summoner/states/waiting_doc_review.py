"""WAITING_DOC_REVIEW → polls for ✅ or 🔄 reaction on the doc comment."""

from __future__ import annotations

from task_summoner.models import TicketState

from .base import BaseApprovalState


class WaitingDocReviewState(BaseApprovalState):
    @property
    def state(self) -> TicketState:
        return TicketState.WAITING_DOC_REVIEW

    @property
    def comment_meta_key(self) -> str:
        return "doc_comment_id"

    @property
    def ts_tag_state(self) -> str:
        # The tag is posted by CreatingDocState (and ImprovingDocState on retry).
        # Legacy tags with the old ``checking_doc`` state name are still read
        # directly from ``doc_comment_id`` when the metadata survives; only new
        # recoveries need to find this name.
        return "creating_doc"

    @property
    def trigger_on_approve(self) -> str:
        return "approved"

    @property
    def trigger_on_retry(self) -> str:
        return "retry"
