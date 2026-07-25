"""Alembic 环境脚本。

要点：
- 从环境变量读取 DATABASE_URL（缺省时回落到 SQLite 内存，便于离线演练）；
- target_metadata 指向 app.db.base.Base.metadata，autogenerate 可识别 8 张表；
- 支持 offline/online 两种模式，Phase 0 不连接真实 PG。
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# 保证 backend/ 目录在 sys.path 上，能 import app.db
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.base import Base  # noqa: E402  - 必须在 sys.path 之后
from app.db import models  # noqa: F401, E402  - 触发模型注册到 Base.metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# DATABASE_URL 缺省时回落到 SQLite 内存（Phase 0 不连真实 PG）。
db_url = os.getenv("DATABASE_URL", "").strip() or "sqlite+pysqlite:///:memory:"
config.set_main_option("sqlalchemy.url", db_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""

    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=url.startswith("sqlite"),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        url = config.get_main_option("sqlalchemy.url") or ""
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=url.startswith("sqlite"),
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
