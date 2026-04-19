"""Domain routers — each module covers one slice of the API surface."""

from task_summoner.api.routers.agent_profiles import router as agent_profiles_router
from task_summoner.api.routers.config import router as config_router
from task_summoner.api.routers.cost import router as cost_router
from task_summoner.api.routers.decisions import router as decisions_router
from task_summoner.api.routers.events import router as events_router
from task_summoner.api.routers.failures import router as failures_router
from task_summoner.api.routers.gates import router as gates_router
from task_summoner.api.routers.health import router as health_router
from task_summoner.api.routers.rfcs import router as rfcs_router
from task_summoner.api.routers.setup import router as setup_router
from task_summoner.api.routers.skills import router as skills_router
from task_summoner.api.routers.streams import router as streams_router
from task_summoner.api.routers.tickets import router as tickets_router
from task_summoner.api.routers.workflow import router as workflow_router

__all__ = [
    "agent_profiles_router",
    "config_router",
    "cost_router",
    "decisions_router",
    "events_router",
    "failures_router",
    "gates_router",
    "health_router",
    "rfcs_router",
    "setup_router",
    "skills_router",
    "streams_router",
    "tickets_router",
    "workflow_router",
]
