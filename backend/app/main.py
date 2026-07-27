"""FastAPI application entry point."""

# 根目录 .env（含 LLM_A_* 等真实 key）的加载在 app.core.config 模块导入时完成，
# 早于任何 Agent 运行，确保 agents.config_loader 的 os.environ 插值在运行时生效。

from fastapi import FastAPI

from app.api import (
    agents_router,
    analysis_router,
    auth_router,
    conversations_router,
    health_router,
    knowledge_router,
    projects_router,
    rag_router,
    report_router,
    uploads_router,
    vision_router,
)
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.middleware.cors import register_cors
from app.middleware.error_handler import register_exception_handlers

settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(
    title="BOIP Backend",
    description="建筑开口智能设计平台后端 API",
    version="0.1.0",
)
app.include_router(health_router)
app.include_router(projects_router)
app.include_router(agents_router)
app.include_router(conversations_router)
app.include_router(knowledge_router)
app.include_router(uploads_router)
app.include_router(vision_router)
app.include_router(report_router)
app.include_router(rag_router)
app.include_router(auth_router)
app.include_router(analysis_router)
register_cors(app)
register_exception_handlers(app)