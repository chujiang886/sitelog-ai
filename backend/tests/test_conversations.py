"""Phase 1 / T06b 会话 API 集成测试。

覆盖：
- 4 条主路由（POST create / GET id / POST messages / GET messages）
- tenant 隔离：跨租户访问应返回 404
- 异常路径：缺 header / 非法 UUID / 非法 role / 不存在的会话
- 编排降级：即便 Core Agent chat 抛出，assistant 消息也会被持久化（pending_verification=True）
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import models as _models  # noqa: F401  - 触发 ORM 注册
from app.db.base import Base
from app.db.models.tenant import Tenant
from app.db.models.user import User
from app.main import app


# --------------------------------------------------------------------------- #
# Fixtures                                                                     #
# --------------------------------------------------------------------------- #


@pytest.fixture()
def conversation_db() -> Iterator[Session]:
    """独立 in-memory SQLite 会话，含 conversations/messages 表。"""

    engine: Engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, class_=Session
    )
    session: Session = session_factory()
    tenant = Tenant(name="T06 Tenant", slug=f"t06-{uuid.uuid4().hex}", status="active")
    session.add(tenant)
    session.flush()
    user = User(
        tenant_id=tenant.id,
        email=f"user-{uuid.uuid4().hex}@boip.local",
        hashed_password="phase1-placeholder",
        role="customer",
        status="active",
    )
    session.add(user)
    session.flush()
    session._tenant_id = tenant.id  # type: ignore[attr-defined]
    session._user_id = user.id  # type: ignore[attr-defined]
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture()
def conversation_client(conversation_db: Session) -> Iterator[TestClient]:
    """FastAPI TestClient；用 ``conversation_db`` 替换 ``get_db`` 依赖。"""

    from app.api import conversations as conversations_module

    def _override_get_db() -> Iterator[Session]:
        try:
            yield conversation_db
        finally:
            pass  # 关闭交给 fixture

    app.dependency_overrides[conversations_module.get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _tenant_header(db: Session) -> dict[str, str]:
    return {
        "X-Tenant-Id": str(db._tenant_id),  # type: ignore[attr-defined]
        "X-User-Id": str(db._user_id),  # type: ignore[attr-defined]
    }


# --------------------------------------------------------------------------- #
# POST /api/conversations                                                      #
# --------------------------------------------------------------------------- #


def test_create_conversation_returns_envelope(conversation_client: TestClient, conversation_db: Session) -> None:
    """创建会话必须返回 ``{success, data}`` + 持久化记录。"""

    response = conversation_client.post(
        "/api/conversations",
        json={"title": "T06 测试会话"},
        headers=_tenant_header(conversation_db),
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["success"] is True
    data = payload["data"]
    assert data["title"] == "T06 测试会话"
    assert data["status"] == "Active"
    assert data["state"] == "Active"
    assert data["tenant_id"] == str(conversation_db._tenant_id)  # type: ignore[attr-defined]
    # 持久化校验
    refreshed = conversation_db.execute(
        __import__("sqlalchemy").text("SELECT COUNT(*) FROM conversations")
    ).scalar()
    assert refreshed == 1


def test_create_conversation_missing_tenant_returns_400(conversation_client: TestClient) -> None:
    """缺少 ``X-Tenant-Id`` 头必须返回 400。"""

    response = conversation_client.post(
        "/api/conversations",
        json={"title": "no-tenant"},
        headers={"X-User-Id": str(uuid.uuid4())},
    )
    assert response.status_code == 400


def test_create_conversation_invalid_user_returns_400(conversation_client: TestClient, conversation_db: Session) -> None:
    """非法 ``X-User-Id`` 必须返回 400。"""

    headers = {"X-Tenant-Id": str(conversation_db._tenant_id), "X-User-Id": "not-a-uuid"}  # type: ignore[attr-defined]
    response = conversation_client.post(
        "/api/conversations",
        json={},
        headers=headers,
    )
    assert response.status_code == 400


# --------------------------------------------------------------------------- #
# GET /api/conversations/{id}                                                  #
# --------------------------------------------------------------------------- #


def test_get_conversation_returns_messages(conversation_client: TestClient, conversation_db: Session) -> None:
    """GET 必须返回会话对象 + 关联消息数组（空数组可接受）。"""

    created = conversation_client.post(
        "/api/conversations",
        json={},
        headers=_tenant_header(conversation_db),
    ).json()["data"]
    conv_id = created["id"]

    response = conversation_client.get(
        f"/api/conversations/{conv_id}",
        headers=_tenant_header(conversation_db),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["conversation"]["id"] == conv_id
    assert payload["data"]["messages"] == []


def test_get_conversation_unknown_returns_404(conversation_client: TestClient, conversation_db: Session) -> None:
    """不存在的会话必须返回 404 + 错误信封。"""

    response = conversation_client.get(
        f"/api/conversations/{uuid.uuid4()}",
        headers=_tenant_header(conversation_db),
    )
    assert response.status_code == 404
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] in {"HTTP_404", "NOT_FOUND"}


def test_get_conversation_cross_tenant_is_404(conversation_client: TestClient, conversation_db: Session) -> None:
    """跨租户访问会话必须返回 404（禁止泄漏存在性）。"""

    created = conversation_client.post(
        "/api/conversations",
        json={},
        headers=_tenant_header(conversation_db),
    ).json()["data"]
    conv_id = created["id"]

    foreign_tenant_id = str(uuid.uuid4())
    response = conversation_client.get(
        f"/api/conversations/{conv_id}",
        headers={"X-Tenant-Id": foreign_tenant_id, "X-User-Id": str(uuid.uuid4())},
    )
    assert response.status_code == 404


# --------------------------------------------------------------------------- #
# POST /api/conversations/{id}/messages                                        #
# --------------------------------------------------------------------------- #


def test_append_message_persists_user_and_assistant(conversation_client: TestClient, conversation_db: Session) -> None:
    """POST messages 必须同时持久化 user / assistant 两条消息 + 返回 envelope。"""

    created = conversation_client.post(
        "/api/conversations",
        json={},
        headers=_tenant_header(conversation_db),
    ).json()["data"]
    conv_id = created["id"]

    response = conversation_client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"role": "user", "content": "我想了解 BOIP 是什么"},
        headers=_tenant_header(conversation_db),
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["success"] is True
    data = payload["data"]
    assert data["message_id"]
    assert data["user_message_id"]
    assert isinstance(data["intent"], dict)
    assert "agent_steps" in data
    assert data["pending_verification"] is True

    # 校验数据库
    rows = conversation_db.execute(
        __import__("sqlalchemy").text(
            "SELECT role, content FROM messages WHERE conversation_id = :cid ORDER BY created_at"
        ),
        {"cid": conv_id},
    ).fetchall()
    assert [r[0] for r in rows] == ["user", "assistant"]


def test_append_message_invalid_role_returns_400(conversation_client: TestClient, conversation_db: Session) -> None:
    """role 不在枚举中必须返回 400。"""

    created = conversation_client.post(
        "/api/conversations",
        json={},
        headers=_tenant_header(conversation_db),
    ).json()["data"]

    response = conversation_client.post(
        f"/api/conversations/{created['id']}/messages",
        json={"role": "admin", "content": "x"},
        headers=_tenant_header(conversation_db),
    )
    assert response.status_code == 400


def test_append_message_unknown_conversation_returns_404(conversation_client: TestClient, conversation_db: Session) -> None:
    """不存在的会话追加消息必须返回 404。"""

    response = conversation_client.post(
        f"/api/conversations/{uuid.uuid4()}/messages",
        json={"role": "user", "content": "x"},
        headers=_tenant_header(conversation_db),
    )
    assert response.status_code == 404


# --------------------------------------------------------------------------- #
# GET /api/conversations/{id}/messages                                         #
# --------------------------------------------------------------------------- #


def test_list_messages_returns_paginated_envelope(conversation_client: TestClient, conversation_db: Session) -> None:
    """GET messages 必须返回分页结构 + items 数组。"""

    created = conversation_client.post(
        "/api/conversations",
        json={},
        headers=_tenant_header(conversation_db),
    ).json()["data"]
    conv_id = created["id"]

    # 追加 3 条
    for text in ["你好", "请解释方案", "触发人工复核"]:
        conversation_client.post(
            f"/api/conversations/{conv_id}/messages",
            json={"role": "user", "content": text},
            headers=_tenant_header(conversation_db),
        )

    response = conversation_client.get(
        f"/api/conversations/{conv_id}/messages",
        params={"page": 1, "page_size": 10},
        headers=_tenant_header(conversation_db),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    data = payload["data"]
    assert data["page"] == 1
    assert data["page_size"] == 10
    # user + assistant = 2 message per call * 3 calls = 6
    assert data["total"] == 6
    assert len(data["items"]) == 6


def test_list_messages_invalid_conversation_id_returns_400(conversation_client: TestClient, conversation_db: Session) -> None:
    """非法 UUID 必须返回 400。"""

    response = conversation_client.get(
        "/api/conversations/not-a-uuid/messages",
        headers=_tenant_header(conversation_db),
    )
    assert response.status_code == 400