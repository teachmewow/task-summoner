"""Workflow designer response schemas — FSM nodes/edges + live counts."""

from __future__ import annotations

from pydantic import BaseModel


class WorkflowNode(BaseModel):
    id: str
    label: str
    kind: str  # start | agent | approval | terminal
    x: float
    y: float


class WorkflowEdge(BaseModel):
    id: str
    source: str
    target: str
    trigger: str


class WorkflowResponse(BaseModel):
    nodes: list[WorkflowNode]
    edges: list[WorkflowEdge]


class WorkflowLiveCount(BaseModel):
    state: str
    count: int


class WorkflowLiveResponse(BaseModel):
    total_tickets: int
    counts: list[WorkflowLiveCount]


__all__ = [
    "WorkflowEdge",
    "WorkflowLiveCount",
    "WorkflowLiveResponse",
    "WorkflowNode",
    "WorkflowResponse",
]
