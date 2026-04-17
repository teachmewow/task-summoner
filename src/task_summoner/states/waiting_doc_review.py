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
        return "checking_doc"

    @property
    def trigger_on_approve(self) -> str:
        return "approved"

    @property
    def trigger_on_retry(self) -> str:
        return "retry"
