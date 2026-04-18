"""Workflow designer endpoints — FSM definition + live per-state counts."""

from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends

from task_summoner.api.deps import get_store
from task_summoner.api.schemas import (
    WorkflowEdge,
    WorkflowLiveCount,
    WorkflowLiveResponse,
    WorkflowNode,
    WorkflowResponse,
)
from task_summoner.core import StateStore
from task_summoner.core.state_machine import (
    AGENT_STATES,
    APPROVAL_STATES,
    TERMINAL_STATES,
    TRANSITIONS,
)
from task_summoner.models import TicketState

router = APIRouter(prefix="/api/workflow", tags=["workflow"])

# Hand-picked positions so the graph reads left-to-right like the lifecycle diagram.
_LAYOUT: dict[TicketState, tuple[float, float]] = {
    TicketState.QUEUED: (0, 0),
    TicketState.CHECKING_DOC: (240, 0),
    TicketState.CREATING_DOC: (480, -140),
    TicketState.IMPROVING_DOC: (480, 140),
    TicketState.WAITING_DOC_REVIEW: (720, 0),
    TicketState.PLANNING: (960, 0),
    TicketState.WAITING_PLAN_REVIEW: (1200, 0),
    TicketState.IMPLEMENTING: (1440, 0),
    TicketState.WAITING_MR_REVIEW: (1680, 0),
    TicketState.FIXING_MR: (1680, 180),
    TicketState.DONE: (1920, 0),
    TicketState.FAILED: (960, 320),
}


def _kind(state: TicketState) -> str:
    if state == TicketState.QUEUED:
        return "start"
    if state in TERMINAL_STATES:
        return "terminal"
    if state in APPROVAL_STATES:
        return "approval"
    if state in AGENT_STATES:
        return "agent"
    return "other"


@router.get("", response_model=WorkflowResponse)
async def get_workflow() -> WorkflowResponse:
    nodes = [
        WorkflowNode(
            id=state.value,
            label=state.value.replace("_", " "),
            kind=_kind(state),
            x=_LAYOUT.get(state, (0, 0))[0],
            y=_LAYOUT.get(state, (0, 0))[1],
        )
        for state in TicketState
    ]
    edges = [
        WorkflowEdge(
            id=f"{src.value}-{trigger}-{dst.value}",
            source=src.value,
            target=dst.value,
            trigger=trigger,
        )
        for (src, trigger), dst in TRANSITIONS.items()
    ]
    return WorkflowResponse(nodes=nodes, edges=edges)


@router.get("/live", response_model=WorkflowLiveResponse)
async def get_live_counts(store: StateStore = Depends(get_store)) -> WorkflowLiveResponse:
    counts: dict[str, int] = defaultdict(int)
    contexts = store.list_all()
    for ctx in contexts:
        counts[ctx.state.value] += 1
    return WorkflowLiveResponse(
        total_tickets=len(contexts),
        counts=[WorkflowLiveCount(state=s, count=c) for s, c in sorted(counts.items())],
    )
