"""Domain routers — each module covers one slice of the API surface."""

from task_summoner.api.routers.agent_profiles import router as agent_profiles_router
from task_summoner.api.routers.config import router as config_router
from task_summoner.api.routers.cost import router as cost_router
from task_summoner.api.routers.events import router as events_router
from task_summoner.api.routers.failures import router as failures_router
from task_summoner.api.routers.skills import router as skills_router
from task_summoner.api.routers.tickets import router as tickets_router

__all__ = [
    "agent_profiles_router",
    "config_router",
    "cost_router",
    "events_router",
    "failures_router",
    "skills_router",
    "tickets_router",
]
