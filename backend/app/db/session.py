"""同步 / 异步 SQLAlchemy 引擎与 Session 工厂。

Phase 0 决策（同步，保留）：
- 走同步 ORM（alembic 默认同步），FastAPI 路由可使用 Depends(get_db)；
- DATABASE_URL 缺省时退回 SQLite 内存，便于本地/CI 零依赖启动；
- 业务路由尚未真正落库，依赖注入仅供健康检查 + 种子脚本演练。

Phase 2.1.4 决策（异步，新增）：
- 引入 async_engine / AsyncSessionLocal / async_get_db 供请求路径路由使用，
  消除 async 路由内同步 DB 阻塞事件循环的风险；
- 缺省 ``DATABASE_URL_ASYNC`` 未配时退回 ``sqlite+aiosqlite:///:memory:``
  （StaticPool 保证单连接共享内存库，与现有同步测试行为对齐）；
- 同步 ``engine / SessionLocal / get_db`` 原样保留，供后台任务
  （vision_tasks.process_image）、alembic 与 test_db.py 兼容使用。
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


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


# --------------------------------------------------------------------------- #
# 同步（保留：后台任务 / alembic / 兼容测试）                                    #
# --------------------------------------------------------------------------- #

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

    Phase 0 路由暂未使用；保留接口供后续业务模块接入与测试兼容。
    """

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# 异步（新增：请求路径路由，避免阻塞事件循环）                                  #
# --------------------------------------------------------------------------- #


def _resolve_async_url() -> str:
    """读取 DATABASE_URL_ASYNC；未配置则使用 aiosqlite 内存占位。

    与同步引擎对称：缺省退回内存库，避免无 DB 开发环境硬失败。
    异步内存库必须用 StaticPool + check_same_thread=False，保证单连接共享内存库。
    """

    url = os.getenv("DATABASE_URL_ASYNC", "").strip()
    if url:
        return url
    return "sqlite+aiosqlite:///:memory:"


_async_url: str = _resolve_async_url()
_async_engine_kwargs: dict[str, object] = {"pool_pre_ping": True}
if _async_url.startswith("sqlite"):
    _async_engine_kwargs["poolclass"] = StaticPool
    _async_engine_kwargs["connect_args"] = {"check_same_thread": False}

async_engine = create_async_engine(_async_url, **_async_engine_kwargs)

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=async_engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def async_get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI 依赖：每次请求一个 AsyncSession，结束后关闭。

    供请求路径路由替换原 ``get_db``，避免同步 DB 操作阻塞事件循环。
    """

    async with AsyncSessionLocal() as session:
        yield session
