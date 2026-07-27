"""HTTP API routers."""

from app.api.agents import router as agents_router
from app.api.analysis import router as analysis_router
from app.api.auth import router as auth_router
from app.api.conversations import router as conversations_router
from app.api.health import router as health_router
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
    "knowledge_router",
    "projects_router",
    "rag_router",
    "report_router",
    "uploads_router",
    "vision_router",
]