"""State handler registry — maps each TicketState to its handler class."""

from task_summoner.config import TaskSummonerConfig
from task_summoner.models import TicketState

from .base import BaseApprovalState, BaseState, StateServices
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


def build_state_registry(config: TaskSummonerConfig) -> dict[TicketState, BaseState]:
    """Create one handler instance per state."""
    states: list[BaseState] = [
        QueuedState(config),
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
