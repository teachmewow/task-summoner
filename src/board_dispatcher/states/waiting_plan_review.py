"""WAITING_PLAN_REVIEW → polls for ✅ or 🔄 reaction on the plan comment."""

from __future__ import annotations

from board_dispatcher.models import TicketState

from .base import BaseApprovalState


class WaitingPlanReviewState(BaseApprovalState):

    @property
    def state(self) -> TicketState:
        return TicketState.WAITING_PLAN_REVIEW

    @property
    def comment_meta_key(self) -> str:
        return "plan_comment_id"

    @property
    def bd_tag_state(self) -> str:
        return "planning"

    @property
    def trigger_on_approve(self) -> str:
        return "approved"

    @property
    def trigger_on_retry(self) -> str:
        return "retry"
