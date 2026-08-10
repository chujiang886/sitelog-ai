"""共享 RBAC 测试环境（Phase 2.2 / 2.2.6；Phase 3.8.28 增补治理身份环境）。

提供 ``rbac_env`` fixture：
- 注入测试用 JWT_SECRET（``tests`` 目录被 ``check_hardcoded`` 排除，可安全放置）；
- 建立文件型 SQLite（sync + async 共享同一库）；
- 幂等种入 RBAC 目录 + admin/designer/viewer 演示用户（按租户隔离）；
- 覆盖 ``async_get_db`` 依赖到测试库；
- 暴露 ``client`` / 各角色 token / ``login`` / ``token_for`` 助手。

提供 ``governance_env`` fixture（Phase 3.8.28）：
- 在 ``rbac_env`` 同款隔离库上**额外**种入治理 RBAC 目录（``app.identity.seed``）；
- 建立四类治理角色用户 + 一个只有业务角色的用户（验证默认拒绝）
  + 一个 B 租户治理管理员（验证跨组织）+ 一个被停用的治理管理员；
- 同时覆盖 ``async_get_db``（身份解析）与 ``get_db``（治理持久化路由）；
- 暴露每个用户的真实登录 token —— 测试里**没有任何**伪造身份的捷径，
  这正是本阶段要求的：想在测试里成为某人，必须真的以那个人登录一次。

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
        """只取 token 字符串，并清掉登录带来的 Cookie 会话副作用。

        自 Phase 3.8.29 起 ``/api/auth/login`` 会种 HttpOnly 凭据 Cookie，
        而 ``TestClient`` 自带 cookie jar 会把它持久化到后续每个请求上。
        若不清理，"不带凭据应 401"这类断言会因为残留 Cookie 而拿到 200 ——
        测试想验的是 Bearer 头通道，不该被隐式 Cookie 会话污染。
        Cookie 通道本身由 ``test_production_security.py`` 专门覆盖。
        """

        resp = _login(email, password)
        assert resp.status_code == 200, resp.text
        token = resp.json()["data"]["access_token"]
        client.cookies.clear()
        return token

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


# --------------------------------------------------------------------------- #
# Phase 3.8.28：治理身份测试环境                                                #
# --------------------------------------------------------------------------- #


@pytest.fixture()
def governance_env(monkeypatch, tmp_path):
    """可登录、带治理 RBAC 目录与四类治理角色的隔离测试环境。

    与 ``rbac_env`` 并列而不是扩展它，原因有两个：

    1. 业务测试不应该因为治理目录被种进去而改变行为 —— 治理权限"默认没有"
       这件事本身就是被测对象；
    2. 治理测试需要额外覆盖同步 ``get_db``（``/governance/ops/*`` 走同步会话），
       把这段装配塞进 ``rbac_env`` 会让所有业务测试白白多接一个依赖覆盖。
    """

    monkeypatch.setenv("JWT_SECRET", TEST_JWT_SECRET)
    from app.core.config import get_settings

    get_settings.cache_clear()

    db_file = tmp_path / "governance.db"
    sync_url = f"sqlite+pysqlite:///{db_file}"
    async_url = f"sqlite+aiosqlite:///{db_file}"
    sync_engine = create_engine(sync_url, connect_args={"check_same_thread": False})
    async_engine = create_async_engine(
        async_url, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(sync_engine)

    SyncSession = sessionmaker(
        bind=sync_engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    from app.core import security
    from app.identity.seed import assign_governance_role, seed_governance_rbac

    pw = "password123"
    ids: dict = {}

    with SyncSession() as s:
        ta = Tenant(name="GovA", slug=f"gov-a-{uuid.uuid4().hex}", status="active")
        tb = Tenant(name="GovB", slug=f"gov-b-{uuid.uuid4().hex}", status="active")
        s.add_all([ta, tb])
        s.flush()

        # 业务目录 + 治理目录：两份 seed 各司其职，互不代劳。
        security.seed_rbac_catalog(s)
        seed_governance_rbac(s)

        def _user(
            email: str,
            tenant: Tenant,
            *,
            governance_role: str | None = None,
            business_role: str = "designer",
            status: str = "active",
        ) -> User:
            legacy = {"admin": "admin", "designer": "designer", "viewer": "customer"}
            u = User(
                tenant_id=tenant.id,
                email=email,
                hashed_password=security.hash_password(pw),
                role=legacy[business_role],
                status=status,
            )
            s.add(u)
            s.flush()
            security.assign_user_role(s, u, business_role, tenant.id)
            if governance_role:
                assign_governance_role(s, u, governance_role, tenant.id)
            return u

        gov_admin = _user(
            "gov-admin@a.local", ta, governance_role="governance-admin"
        )
        gov_reviewer = _user(
            "gov-reviewer@a.local", ta, governance_role="governance-reviewer"
        )
        gov_auditor = _user(
            "gov-auditor@a.local", ta, governance_role="governance-auditor"
        )
        gov_viewer = _user(
            "gov-viewer@a.local", ta, governance_role="governance-viewer"
        )
        # 只有业务角色：登录成功但治理权限为空（默认拒绝的主证人）。
        business_only = _user("business-only@a.local", ta, business_role="admin")
        # B 租户治理管理员：用于跨组织隔离用例。
        gov_admin_b = _user(
            "gov-admin@b.local", tb, governance_role="governance-admin"
        )
        # 停用的治理管理员：凭据有效但主体失效（离职/停用）。
        suspended = _user(
            "gov-suspended@a.local",
            ta,
            governance_role="governance-admin",
            status="suspended",
        )
        s.commit()

        ids = {
            "tenant_a": str(ta.id),
            "tenant_b": str(tb.id),
            "gov_admin": str(gov_admin.id),
            "gov_reviewer": str(gov_reviewer.id),
            "gov_auditor": str(gov_auditor.id),
            "gov_viewer": str(gov_viewer.id),
            "business_only": str(business_only.id),
            "gov_admin_b": str(gov_admin_b.id),
            "suspended": str(suspended.id),
            "pw": pw,
        }
        suspended_id = suspended.id
        tenant_a_id = ta.id

    async def _override_async_get_db():
        async with AsyncSession(
            async_engine, autoflush=False, autocommit=False, expire_on_commit=False
        ) as sess:
            yield sess

    def _override_get_db():
        sess = SyncSession()
        try:
            yield sess
        finally:
            sess.close()

    from app.api.governance_dashboard import (
        _build_demo_service,
        reset_dashboard_service,
    )
    from app.db.session import get_db

    reset_dashboard_service()
    app.dependency_overrides[async_get_db] = _override_async_get_db
    app.dependency_overrides[get_db] = _override_get_db

    client = TestClient(app)

    def _token_for(email: str) -> str:
        """只取 token 字符串，并清掉登录带来的 Cookie 会话副作用。

        理由同 ``rbac_env._token_for``：3.8.29 起登录会种 HttpOnly Cookie，
        ``TestClient`` 的 cookie jar 会让它渗进后续每个请求，把"匿名应 401"
        和"跨租户应不可见"这类断言污染成误通过 / 误失败。
        """

        resp = client.post(
            "/api/auth/login", json={"email": email, "password": pw}
        )
        assert resp.status_code == 200, resp.text
        token = resp.json()["data"]["access_token"]
        client.cookies.clear()
        return token

    def _bearer(token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    env = {
        "client": client,
        "ids": ids,
        "pw": pw,
        "token_for": _token_for,
        "bearer": _bearer,
        "admin_token": _token_for("gov-admin@a.local"),
        "reviewer_token": _token_for("gov-reviewer@a.local"),
        "auditor_token": _token_for("gov-auditor@a.local"),
        "viewer_token": _token_for("gov-viewer@a.local"),
        "business_only_token": _token_for("business-only@a.local"),
        "admin_b_token": _token_for("gov-admin@b.local"),
        # 停用账号无法登录，token 直接签发：模拟"凭据仍在手上，人已停用"。
        "suspended_token": security.create_access_token(
            sub=suspended_id,
            tenant_id=tenant_a_id,
            email="gov-suspended@a.local",
            role="designer",
            roles=["designer", "governance-admin"],
            permissions=[],
        ),
        # 供用例按需构造演示驾驶舱服务（按组织隔离）。
        "build_demo_service": _build_demo_service,
        "reset_dashboard_service": reset_dashboard_service,
    }

    try:
        yield env
    finally:
        reset_dashboard_service()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(sync_engine)
        sync_engine.dispose()
        asyncio.run(async_engine.dispose())


__all__ = ["governance_env", "rbac_env"]
