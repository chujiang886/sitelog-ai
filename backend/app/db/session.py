"""同步 SQLAlchemy 引擎与 Session 工厂。

Phase 0 决策：
- 走同步 ORM（alembic 默认同步），FastAPI 路由可使用 Depends(get_db)；
- DATABASE_URL 缺省时退回 SQLite 内存，便于本地/CI 零依赖启动；
- 业务路由尚未真正落库，依赖注入仅供健康检查 + 种子脚本演练。
"""

from __future__ import annotations

import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def _resolve_database_url() -> str:
    """读取 DATABASE_URL，未配置则使用 SQLite 内存占位。

    注意：Phase 0 不连接真实 PostgreSQL，避免在没有 Docker / DB 的开发环境硬失败。
    """

    url = os.getenv("DATABASE_URL", "").strip()
    if url:
        return url
    # SQLite 占位：内存数据库，连接断开即销毁，仅用于本地/CI 演练。
    return "sqlite+pysqlite:///:memory:"


def _build_engine(url: str) -> Engine:
    """根据 URL 创建引擎；SQLite 需要关闭连接检查 + 允许跨线程使用。"""

    connect_args: dict[str, object] = {}
    engine_kwargs: dict[str, object] = {"future": True, "pool_pre_ping": True}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    if connect_args:
        engine_kwargs["connect_args"] = connect_args
    return create_engine(url, **engine_kwargs)


engine: Engine = _build_engine(_resolve_database_url())

SessionLocal: sessionmaker[Session] = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：每次请求一个 Session，结束后关闭。

    Phase 0 路由暂未使用；保留接口供后续业务模块接入。
    """

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
