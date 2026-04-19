"""Pydantic response models for the HTTP API.

Endpoint response shapes live here so they can be generated into TypeScript
types (the monorepo task, ENG-66, picks the codegen tool).

Where a response is just the persisted domain model, we re-export it from
`models/` rather than duplicating — e.g. `TicketContext` is both the on-disk
shape and the `/api/tickets/{key}` response.
"""

from task_summoner.api.schemas.agent_profile import (
    AgentProfileOut,
    AgentProfilePayload,
    AgentProfileSaveResponse,
    AgentProfilesResponse,
)
from task_summoner.api.schemas.config import (
    ConfigPayload,
    ConfigSaveResponse,
    ConfigStatus,
    ConfigTestResponse,
)
from task_summoner.api.schemas.cost import (
    BudgetStatus,
    CostByDay,
    CostByProfile,
    CostByState,
    CostByTicket,
    CostSummaryResponse,
    TurnsBucket,
)
from task_summoner.api.schemas.decision import (
    DecisionsResponse,
    DecisionSummary,
    OpenEditorPayload,
    OpenEditorResponse,
)
from task_summoner.api.schemas.event import EventResponse
from task_summoner.api.schemas.failure import (
    FailedTicket,
    FailureByCategory,
    FailureByPhase,
    FailureSummaryResponse,
    RetryResponse,
)
from task_summoner.api.schemas.gate import (
    GateActionResponse,
    GateApprovePayload,
    GateRequestChangesPayload,
    GateResponse,
    PrInfo,
)
from task_summoner.api.schemas.health import (
    AgentHealth,
    BoardHealth,
    CleanResponse,
    HealthResponse,
    LocalStateHealth,
    TestBoardResponse,
)
from task_summoner.api.schemas.rfc import RfcResponse
from task_summoner.api.schemas.setup import (
    LinearTeamsRequest,
    LinearTeamsResponse,
    LinearTeamSummary,
)
from task_summoner.api.schemas.skill import (
    SkillDetail,
    SkillSavePayload,
    SkillSaveResponse,
    SkillsResponse,
    SkillSummary,
)
from task_summoner.api.schemas.ticket import TicketResponse
from task_summoner.api.schemas.workflow import (
    WorkflowEdge,
    WorkflowLiveCount,
    WorkflowLiveResponse,
    WorkflowNode,
    WorkflowResponse,
)

__all__ = [
    "AgentProfileOut",
    "AgentProfilePayload",
    "AgentProfileSaveResponse",
    "AgentProfilesResponse",
    "BudgetStatus",
    "ConfigPayload",
    "ConfigSaveResponse",
    "ConfigStatus",
    "ConfigTestResponse",
    "CostByDay",
    "CostByProfile",
    "CostByState",
    "CostByTicket",
    "AgentHealth",
    "BoardHealth",
    "CleanResponse",
    "HealthResponse",
    "LinearTeamSummary",
    "LinearTeamsRequest",
    "LinearTeamsResponse",
    "LocalStateHealth",
    "TestBoardResponse",
    "CostSummaryResponse",
    "DecisionSummary",
    "DecisionsResponse",
    "EventResponse",
    "GateActionResponse",
    "GateApprovePayload",
    "GateRequestChangesPayload",
    "GateResponse",
    "OpenEditorPayload",
    "OpenEditorResponse",
    "PrInfo",
    "RfcResponse",
    "FailedTicket",
    "FailureByCategory",
    "FailureByPhase",
    "FailureSummaryResponse",
    "RetryResponse",
    "SkillDetail",
    "SkillSavePayload",
    "SkillSaveResponse",
    "SkillSummary",
    "SkillsResponse",
    "TicketResponse",
    "TurnsBucket",
    "WorkflowEdge",
    "WorkflowLiveCount",
    "WorkflowLiveResponse",
    "WorkflowNode",
    "WorkflowResponse",
]
