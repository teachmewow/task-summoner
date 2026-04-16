"""State handler registry — maps each TicketState to its handler class."""

from board_dispatcher.config import BoardDispatcherConfig
from board_dispatcher.models import TicketState

from .base import BaseApprovalState, BaseState, StateServices
from .checking_doc import CheckingDocState
from .creating_doc import CreatingDocState
from .fixing_mr import FixingMrState
from .implementing import ImplementingState
from .improving_doc import ImprovingDocState
from .planning import PlanningState
from .queued import QueuedState
from .terminal import DoneState, FailedState
from .waiting_doc_review import WaitingDocReviewState
from .waiting_mr_review import WaitingMrReviewState
from .waiting_plan_review import WaitingPlanReviewState


def build_state_registry(config: BoardDispatcherConfig) -> dict[TicketState, BaseState]:
    """Create one handler instance per state."""
    states: list[BaseState] = [
        QueuedState(config),
        CheckingDocState(config),
        CreatingDocState(config),
        WaitingDocReviewState(config),
        ImprovingDocState(config),
        PlanningState(config),
        WaitingPlanReviewState(config),
        ImplementingState(config),
        WaitingMrReviewState(config),
        FixingMrState(config),
        DoneState(config),
        FailedState(config),
    ]
    return {s.state: s for s in states}


__all__ = [
    "BaseState",
    "BaseApprovalState",
    "StateServices",
    "build_state_registry",
]
