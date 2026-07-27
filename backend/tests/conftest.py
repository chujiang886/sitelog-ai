"""共享 RBAC 测试环境（Phase 2.2 / 2.2.6）。

提供 ``rbac_env`` fixture：
- 注入测试用 JWT_SECRET（``tests`` 目录被 ``check_hardcoded`` 排除，可安全放置）；
- 建立文件型 SQLite（sync + async 共享同一库）；
- 幂等种入 RBAC 目录 + admin/designer/viewer 演示用户（按租户隔离）；
- 覆盖 ``async_get_db`` 依赖到测试库；
- 暴露 ``client`` / 各角色 token / ``login`` / ``token_for`` 助手。

测试用 secret 仅用于本地测试，非生产密钥。
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.db import models  # noqa: F401  - 触发 ORM 注册
from app.db.base import Base
from app.db.models.tenant import Tenant
from app.db.models.user import User
from app.db.session import async_get_db
from app.main import app

TEST_JWT_SECRET = "test-jwt-secret-not-for-production"  # tests dir excluded from hardcoded scan


@pytest.fixture()
def rbac_env(monkeypatch, tmp_path):
    """搭建一个可登录、带 RBAC 目录与三角色的隔离测试环境。"""

    monkeypatch.setenv("JWT_SECRET", TEST_JWT_SECRET)
    from app.core.config import get_settings

    get_settings.cache_clear()

    db_file = tmp_path / "rbac.db"
    sync_url = f"sqlite+pysqlite:///{db_file}"
    async_url = f"sqlite+aiosqlite:///{db_file}"
    sync_engine = create_engine(sync_url, connect_args={"check_same_thread": False})
    async_engine = create_async_engine(async_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(sync_engine)

    # 同步种子：租户 + RBAC 目录 + 用户 + 角色关联
    SyncSession = sessionmaker(
        bind=sync_engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    from app.core import security

    with SyncSession() as s:
        ta = Tenant(name="TenantA", slug=f"ta-{uuid.uuid4().hex}", status="active")
        tb = Tenant(name="TenantB", slug=f"tb-{uuid.uuid4().hex}", status="active")
        s.add_all([ta, tb])
        s.flush()

        security.seed_rbac_catalog(s)

        pw = "password123"
        legacy = {"admin": "admin", "designer": "designer", "viewer": "customer"}

        def _make(email: str, role_name: str, tenant: Tenant) -> User:
            u = User(
                tenant_id=tenant.id,
                email=email,
                hashed_password=security.hash_password(pw),
                role=legacy[role_name],
                status="active",
            )
            s.add(u)
            s.flush()
            security.assign_user_role(s, u, role_name, tenant.id)
            return u

        admin_a = _make("admin@a.local", "admin", ta)
        designer_a = _make("designer@a.local", "designer", ta)
        viewer_a = _make("viewer@a.local", "viewer", ta)
        admin_b = _make("admin@b.local", "admin", tb)

        # 非 active 用户（用于测试 get_current_user 拒绝）
        suspended = User(
            tenant_id=ta.id,
            email="suspended@a.local",
            hashed_password=security.hash_password(pw),
            role="admin",
            status="suspended",
        )
        s.add(suspended)
        s.flush()
        security.assign_user_role(s, suspended, "admin", ta.id)
        s.commit()

        ids = {
            "ta": ta.id,
            "tb": tb.id,
            "admin_a": admin_a.id,
            "designer_a": designer_a.id,
            "viewer_a": viewer_a.id,
            "admin_b": admin_b.id,
            "suspended_a": suspended.id,
            "pw": pw,
        }

    # 覆盖 async_get_db 到测试库
    async def _override_get_db():
        async with AsyncSession(
            async_engine, autoflush=False, autocommit=False, expire_on_commit=False
        ) as sess:
            yield sess

    app.dependency_overrides[async_get_db] = _override_get_db

    client = TestClient(app)

    def _login(email: str, password: str):
        return client.post("/api/auth/login", json={"email": email, "password": password})

    def _token_for(email: str, password: str) -> str:
        resp = _login(email, password)
        assert resp.status_code == 200, resp.text
        return resp.json()["data"]["access_token"]

    env = {
        "client": client,
        "ids": ids,
        "login": _login,
        "token_for": _token_for,
        "admin_a_token": _token_for("admin@a.local", pw),
        "designer_a_token": _token_for("designer@a.local", pw),
        "viewer_a_token": _token_for("viewer@a.local", pw),
        "admin_b_token": _token_for("admin@b.local", pw),
        # 非 active 用户的 token（直接签发，因其无法登录）
        "suspended_a_token": security.create_access_token(
            sub=suspended.id,
            tenant_id=ta.id,
            email="suspended@a.local",
            role="admin",
            roles=["admin"],
            permissions=sorted(security.ROLE_PERMISSIONS["admin"]),
        ),
    }

    try:
        yield env
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(sync_engine)
        sync_engine.dispose()
        asyncio.run(async_engine.dispose())


__all__ = ["rbac_env"]
