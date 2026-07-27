"""Database layer for BOIP backend.

包含：
- DeclarativeBase + NamingConvention
- 引擎与 Session 工厂
- 8 张核心 SQLAlchemy 模型（tenant/user/project/agent/knowledge/audit/threshold）

Phase 0 范围内：仅 PG/SQLite 兼容的同步 ORM 骨架；Phase 1+ 再补异步与连接池调优。
"""

from app.db.base import Base, naming_convention
from app.db.session import (
    SessionLocal,
    engine,
    get_db,
    async_engine,
    AsyncSessionLocal,
    async_get_db,
)

__all__ = [
    "Base",
    "SessionLocal",
    "engine",
    "get_db",
    "async_engine",
    "AsyncSessionLocal",
    "async_get_db",
    "naming_convention",
]
