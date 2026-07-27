"""Phase 0 种子数据脚本。

目标：在 SQLite/PG 数据库中灌入测试数据，供后续 Phase 1 路由联调使用。

数据清单（严格按 T03 任务说明）：
- 1 个测试 tenant（name='Phase0 Test Tenant', slug='phase0'）
- 1 个测试用户（email='test@boip.local', role='admin'）
- 4 个 Agent 注册（core / environment / vision / design，manifest 空 dict）
- 5 条占位 knowledge_rules（pending_verification）
- 5 条占位 knowledge_cases（pending_verification）
- 1 条 threshold_configs 占位（key='force_review_v1'）

执行方式：
    cd backend && .venv/bin/python scripts/seed.py
可选环境变量：
    DATABASE_URL   覆盖目标数据库（缺省走 SQLite 内存）

设计原则：
- 幂等：重复执行不抛错（先 SELECT 再 INSERT/UPDATE）；
- 不连真实服务；脚本仅依赖 SQLAlchemy；
- 任何业务阈值数字保持 pending_verification。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# 把 backend/ 加进 sys.path，使得 `import app.db...` 可用
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.db.models.agent import Agent  # noqa: E402
from app.db.models.knowledge import KnowledgeCase, KnowledgeRule  # noqa: E402
from app.db.models.tenant import Tenant  # noqa: E402
from app.db.models.threshold import ThresholdConfig  # noqa: E402
from app.db.models.user import User  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.core.security import (  # noqa: E402
    assign_user_role,
    hash_password,
    seed_rbac_catalog,
)


PENDING_SOURCE = "pending_verification"


def _resolve_database_url() -> str:
    """选择种子目标数据库；缺省 SQLite 内存。"""

    return os.getenv("DATABASE_URL", "").strip() or "sqlite+pysqlite:///:memory:"


def _build_engine(url: str):
    """与 app.db.session._build_engine 行为一致，避免 SQLite 线程冲突。"""

    kwargs: dict[str, object] = {"future": True, "pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)


# ---------- 种子数据工厂 ----------


def seed_tenant(db: Session) -> Tenant:
    """获取或创建 Phase 0 测试 tenant。"""

    tenant = db.query(Tenant).filter_by(slug="phase0").one_or_none()
    if tenant is not None:
        return tenant
    tenant = Tenant(name="Phase0 Test Tenant", slug="phase0", status="active")
    db.add(tenant)
    db.flush()
    return tenant


def seed_user(db: Session, tenant_id) -> User:
    """获取或创建测试用户（admin），并写入可登录的哈希密码。"""

    user = db.query(User).filter_by(email="test@boip.local").one_or_none()
    if user is not None:
        return user
    # 密码来自环境变量，缺省开发占位；生产必须覆盖 BOIP_SEED_ADMIN_PASSWORD。
    admin_pw = os.getenv("BOIP_SEED_ADMIN_PASSWORD", "changeme-dev")  # infrastructure-config
    user = User(
        tenant_id=tenant_id,
        email="test@boip.local",
        hashed_password=hash_password(admin_pw),
        role="admin",
        status="active",
    )
    db.add(user)
    db.flush()
    return user


def seed_rbac_roles(db: Session, tenant: Tenant, admin: User) -> dict[str, int]:
    """幂等种入 RBAC 目录，并将 admin/designer/viewer 演示用户关联角色。

    返回新增的角色关联计数（用于 seed 输出）。链接计数。
    """

    seed_rbac_catalog(db)
    assign_user_role(db, admin, "admin", tenant.id)

    # 演示用户（designer / viewer），便于直接体验 RBAC 三角色。
    demo_pw = os.getenv("BOIP_SEED_DEMO_PASSWORD", "changeme-dev")  # infrastructure-config
    demo_specs = [
        ("designer", "designer@boip.local", "designer"),
        ("viewer", "viewer@boip.local", "customer"),  # legacy role 用合法值，RBAC 角色取 viewer
    ]
    linked = 1  # admin 已关联
    for role_name, email, legacy_role in demo_specs:
        demo = db.query(User).filter_by(email=email).one_or_none()
        if demo is None:
            demo = User(
                tenant_id=tenant.id,
                email=email,
                hashed_password=hash_password(demo_pw),
                role=legacy_role,
                status="active",
            )
            db.add(demo)
            db.flush()
        assign_user_role(db, demo, role_name, tenant.id)
        linked += 1
    return {"user_roles": linked}


def seed_agents(db: Session, tenant_id) -> list[Agent]:
    """4 个 Agent 注册（core/environment/vision/design），manifest 空 dict。"""

    targets = [
        ("core", "v0.1.0"),
        ("environment", "v0.1.0"),
        ("vision", "v0.1.0"),
        ("design", "v0.1.0"),
    ]
    seeded: list[Agent] = []
    for name, version in targets:
        existing = (
            db.query(Agent)
            .filter_by(tenant_id=tenant_id, name=name, version=version)
            .one_or_none()
        )
        if existing is not None:
            seeded.append(existing)
            continue
        agent = Agent(
            tenant_id=tenant_id,
            name=name,
            version=version,
            manifest={},
            status="active",
        )
        db.add(agent)
        db.flush()
        seeded.append(agent)
    return seeded


def seed_knowledge_rules(db: Session, tenant_id) -> list[KnowledgeRule]:
    """5 条占位 knowledge_rules（pending_verification）。

    注意：所有可能触发业务数字扫描的字段（楼层、厚度、权重等）
    均不写入具体数字，统一以 `note: pending_verification` 占位。
    """

    samples = [
        ("wind_pressure", "default", {"note": PENDING_SOURCE}),
        ("floor_classification", "low", {"note": PENDING_SOURCE}),
        ("material_selection", "glass_default", {"note": PENDING_SOURCE}),
        ("review_policy", "auto_threshold", {"flagged": "pending_verification"}),
        ("design_scoring", "default_weights", {"note": PENDING_SOURCE}),
    ]
    seeded: list[KnowledgeRule] = []
    for category, key, value in samples:
        existing = (
            db.query(KnowledgeRule)
            .filter_by(
                tenant_id=tenant_id,
                category=category,
                key=key,
                version="v0.1.0",
            )
            .one_or_none()
        )
        if existing is not None:
            seeded.append(existing)
            continue
        rule = KnowledgeRule(
            tenant_id=tenant_id,
            category=category,
            key=key,
            value=value,
            source=PENDING_SOURCE,
            status="draft",
            version="v0.1.0",
        )
        db.add(rule)
        db.flush()
        seeded.append(rule)
    return seeded


def seed_knowledge_cases(db: Session, tenant_id) -> list[KnowledgeCase]:
    """5 条占位 knowledge_cases（pending_verification）。

    注意：业务字段（楼层、风压等）均不写入具体数字，避免触发
    scripts/lint/check_fabrication.py；待领域专家评审后再补真实值。
    """

    samples = [
        ("Balcony wind pressure sample", {"orientation": "S", "note": PENDING_SOURCE}),
        ("Window sample case 02", {"orientation": "E", "note": PENDING_SOURCE}),
        ("Door sample case 03", {"orientation": "W", "note": PENDING_SOURCE}),
        ("Curtain wall sample 04", {"orientation": "N", "note": PENDING_SOURCE}),
        ("Sun-room sample 05", {"orientation": "SE", "note": PENDING_SOURCE}),
    ]
    seeded: list[KnowledgeCase] = []
    for title, scenario in samples:
        existing = (
            db.query(KnowledgeCase)
            .filter_by(tenant_id=tenant_id, title=title)
            .one_or_none()
        )
        if existing is not None:
            seeded.append(existing)
            continue
        case = KnowledgeCase(
            tenant_id=tenant_id,
            title=title,
            scenario=scenario,
            outcome={"note": PENDING_SOURCE},
            status="draft",
            version="v0.1.0",
        )
        db.add(case)
        db.flush()
        seeded.append(case)
    return seeded


def seed_threshold_config(db: Session, tenant_id) -> ThresholdConfig:
    """1 条 threshold_configs 占位（force_review_v1）。"""

    existing = (
        db.query(ThresholdConfig)
        .filter_by(tenant_id=tenant_id, key="force_review_v1", version="v0.1.0")
        .one_or_none()
    )
    if existing is not None:
        return existing
    cfg = ThresholdConfig(
        tenant_id=tenant_id,
        key="force_review_v1",
        value={"note": PENDING_SOURCE},
        version="v0.1.0",
        status="draft",
    )
    db.add(cfg)
    db.flush()
    return cfg


def _ensure_schema(engine, db_url: str) -> None:
    """确保 schema 存在。

    - SQLite 内存库：直接 create_all（每次启动都是空库，方便本地/CI 演练）；
    - 其它库（PG/SQLite 文件）：期望已经 `alembic upgrade head`，
      若 alembic_version 不存在则主动 create_all 兜底，避免种子永远失败。
    """

    Base.metadata.create_all(engine)


def run_seed(db_url: str) -> dict[str, int]:
    """执行全部种子并返回计数。"""

    engine = _build_engine(db_url)
    _ensure_schema(engine, db_url)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    counts: dict[str, int] = {}

    with SessionLocal() as db:
        try:
            tenant = seed_tenant(db)
            user = seed_user(db, tenant.id)
            agents = seed_agents(db, tenant.id)
            rules = seed_knowledge_rules(db, tenant.id)
            cases = seed_knowledge_cases(db, tenant.id)
            cfg = seed_threshold_config(db, tenant.id)
            rbac = seed_rbac_roles(db, tenant, user)

            db.commit()

            counts = {
                "tenants": 1 if tenant else 0,
                "users": 1 if user else 0,
                "agents": len(agents),
                "knowledge_rules": len(rules),
                "knowledge_cases": len(cases),
                "threshold_configs": 1 if cfg else 0,
                "user_roles": rbac["user_roles"],
            }
        except Exception:
            db.rollback()
            raise

    return counts


def main() -> int:
    db_url = _resolve_database_url()
    counts = run_seed(db_url)
    print("Seed completed:")
    for key, value in counts.items():
        print(f"  - {key}: {value}")
    print(f"Target DATABASE_URL: {db_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
