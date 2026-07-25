"""SQLAlchemy 2.0 DeclarativeBase 与命名约定。

约定要点：
- 使用 DeclarativeBase 风格（非 legacy declarative_base）；
- 全局统一命名约定（fk/ix/uq/pk 前缀），alembic 生成的迁移可读；
- 单一 Base 被所有模型与 alembic env.py 共享。
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# 命名约定：与 alembic autogenerate 输出对齐，便于审计与回滚。
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

naming_convention = NAMING_CONVENTION  # 给 db/__init__.py 复用


class Base(DeclarativeBase):
    """所有 BOIP ORM 模型的统一基类。"""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        cls_name = type(self).__name__
        pk_cols = [c.name for c in self.__table__.primary_key.columns]
        return f"<{cls_name} pk={pk_cols}>"
