"""HTTP API routers."""

from app.api.agents import router as agents_router
from app.api.analysis import router as analysis_router
from app.api.auth import router as auth_router
from app.api.conversations import router as conversations_router
from app.api.health import router as health_router
from app.api.governance_dashboard import router as governance_dashboard_router
from app.api.governance_identity import router as governance_identity_router
from app.api.governance_operations import router as governance_operations_router
from app.api.governance_release import router as governance_release_router
from app.api.governance_activation import router as governance_activation_router
from app.api.governance_activation_simulation import (
    router as governance_activation_simulation_router,
)
from app.api.governance_change import router as governance_change_router
from app.api.governance_observability import router as governance_observability_router
from app.api.governance_telemetry import router as governance_telemetry_router
from app.api.knowledge import router as knowledge_router
from app.api.projects import router as projects_router
from app.api.rag import router as rag_router
from app.api.report import router as report_router
from app.api.uploads import router as uploads_router
from app.api.vision import router as vision_router

__all__ = [
    "agents_router",
    "analysis_router",
    "auth_router",
    "conversations_router",
    "health_router",
    "governance_dashboard_router",
    "governance_identity_router",
    "governance_operations_router",
    "governance_release_router",
    "governance_activation_router",
    "governance_activation_simulation_router",
    "governance_change_router",
    "governance_observability_router",
    "governance_telemetry_router",
    "knowledge_router",
    "projects_router",
    "rag_router",
    "report_router",
    "uploads_router",
    "vision_router",
]