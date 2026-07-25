"""验证 SQLAlchemy Base、Session 与 8 个核心模型可正常导入与建表。"""

from __future__ import annotations

from sqlalchemy import inspect

from app.db import Base, SessionLocal, engine, get_db
from app.db.models import (
    Agent,
    AuditLog,
    Conversation,
    KnowledgeCase,
    KnowledgeRule,
    Message,
    Project,
    Tenant,
    ThresholdConfig,
    User,
)


EXPECTED_TABLES: set[str] = {
    "agents",
    "audit_logs",
    "conversations",
    "knowledge_cases",
    "knowledge_rules",
    "messages",
    "projects",
    "tenants",
    "threshold_configs",
    "users",
}


def test_base_metadata_lists_business_tables() -> None:
    """Base.metadata 必须包含 Phase 1 / T06b 引入的全部业务表。"""

    registered = set(Base.metadata.tables.keys())
    assert EXPECTED_TABLES.issubset(registered), (
        f"缺少表：{EXPECTED_TABLES - registered}"
    )


def test_session_factory_returns_session() -> None:
    """SessionLocal 必须能产出 Session，并保证 engine 绑定。"""

    with SessionLocal() as session:
        assert session.bind is engine


def test_get_db_dependency_yields_session() -> None:
    """get_db 必须产出 Session 并在 finally 中关闭。"""

    gen = get_db()
    session = next(gen)
    try:
        assert session is not None
    finally:
        with_stop(gen)


def with_stop(gen) -> None:
    """收尾 get_db 生成器，吞掉 StopIteration。"""

    try:
        next(gen)
    except StopIteration:
        pass


def test_create_all_creates_business_tables_on_sqlite() -> None:
    """create_all 必须在 SQLite 上生成全部业务表（含 conversations/messages）。"""

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    names = set(inspector.get_table_names())
    assert EXPECTED_TABLES.issubset(names), f"实际建表：{names}"
    # 清理，避免污染后续测试
    Base.metadata.drop_all(engine)


def test_models_have_expected_columns() -> None:
    """模型字段必须在 create_all 后落到实际表结构。"""

    Base.metadata.create_all(engine)
    inspector = inspect(engine)

    tenant_cols = {c["name"] for c in inspector.get_columns("tenants")}
    assert {"id", "name", "slug", "status", "created_at"}.issubset(tenant_cols)

    project_cols = {c["name"] for c in inspector.get_columns("projects")}
    assert {
        "id",
        "tenant_id",
        "owner_id",
        "address",
        "floor",
        "orientation",
        "status",
        "state",
        "input_payload",
        "output_payload",
        "evidence_payload",
        "created_at",
        "updated_at",
    }.issubset(project_cols)

    audit_cols = {c["name"] for c in inspector.get_columns("audit_logs")}
    assert {"id", "tenant_id", "actor_id", "action", "target_type"}.issubset(audit_cols)

    Base.metadata.drop_all(engine)


def test_model_classes_are_importable() -> None:
    """所有模型类都必须可从 app.db.models 直接导入。"""

    for cls in (
        Tenant,
        User,
        Project,
        Agent,
        KnowledgeRule,
        KnowledgeCase,
        AuditLog,
        ThresholdConfig,
        Conversation,
        Message,
    ):
        assert cls.__tablename__, f"{cls.__name__} 缺少 __tablename__"
