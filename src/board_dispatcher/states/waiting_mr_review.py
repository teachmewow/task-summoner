"""WAITING_MR_REVIEW → polls for ✅ or 🔄 reaction on the MR comment."""

from __future__ import annotations

from board_dispatcher.models import TicketState

from .base import BaseApprovalState


class WaitingMrReviewState(BaseApprovalState):

    @property
    def state(self) -> TicketState:
        return TicketState.WAITING_MR_REVIEW

    @property
    def comment_meta_key(self) -> str:
        return "mr_comment_id"

    @property
    def bd_tag_state(self) -> str:
        return "implementing"

    @property
    def trigger_on_approve(self) -> str:
        return "approved"

    @property
    def trigger_on_retry(self) -> str:
        return "retry"
