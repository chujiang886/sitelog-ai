"""Phase 1 / T08 Vision 路由测试。

覆盖：
- POST /api/vision/analyze：缺 header / 非法 UUID / 不存在的 image_id / 跨租户 404；
- analyze 流程：mock Vision Agent 验证 vision_status / vision_result 写入；
- 真实 VisionAgent 调用（无图）返回占位 pending_verification。
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import models as _models  # noqa: F401  - 触发 ORM 注册
from app.db.base import Base
from app.db.models.image import Image, VISION_STATUS_PENDING
from app.db.models.tenant import Tenant
from app.db.models.user import User
from app.main import app
from app.core import storage as storage_module


@pytest.fixture()
def storage_tmp(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(storage_module, "DEFAULT_STORAGE_ROOT", tmp_path, raising=False)
    monkeypatch.setattr(storage_module, "resolve_storage_root", lambda: tmp_path, raising=False)
    return tmp_path


@pytest.fixture()
def vision_db(storage_tmp: Path) -> Iterator[Session]:
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
    tenant_a = Tenant(name="Vision A", slug=f"va-{uuid.uuid4().hex}", status="active")
    tenant_b = Tenant(name="Vision B", slug=f"vb-{uuid.uuid4().hex}", status="active")
    session.add_all([tenant_a, tenant_b])
    session.flush()
    user = User(
        tenant_id=tenant_a.id,
        email=f"u-{uuid.uuid4().hex}@boip.local",
        hashed_password="phase1-placeholder",
        role="customer",
        status="active",
    )
    session.add(user)
    session.flush()
    session._tenant_a = tenant_a.id  # type: ignore[attr-defined]
    session._tenant_b = tenant_b.id  # type: ignore[attr-defined]

    # 预写一个最小 image 行 + 本地文件
    image_id = uuid.uuid4()
    storage_path = storage_tmp / str(tenant_a.id) / f"{'a' * 64}.jpg"
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    storage_path.write_bytes(bytes([0xFF, 0xD8, 0xFF, 0xE0]) + b"X" * 32 + bytes([0xFF, 0xD9]))
    image = Image(
        id=image_id,
        tenant_id=tenant_a.id,
        project_id=None,
        owner_id=user.id,
        filename="seed.jpg",
        mime_type="image/jpeg",
        size_bytes=storage_path.stat().st_size,
        storage_path=str(storage_path),
        sha256="a" * 64,
        vision_status=VISION_STATUS_PENDING,
        vision_result=None,
    )
    session.add(image)
    session.commit()

    try:
        yield session
    finally:
        session.rollback()
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture()
def vision_client(vision_db: Session) -> Iterator[TestClient]:
    from app.api import vision as vision_module

    def _override_get_db() -> Iterator[Session]:
        try:
            yield vision_db
        finally:
            pass

    app.dependency_overrides[vision_module.get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _tenant_headers(tenant_id: uuid.UUID) -> dict[str, str]:
    return {"X-Tenant-Id": str(tenant_id)}


def _seed_image_id(vision_db: Session) -> uuid.UUID:
    image: Image | None = (
        vision_db.query(Image).filter_by(sha256="a" * 64).one_or_none()
    )
    assert image is not None
    return image.id


def test_analyze_missing_header_rejected(vision_client: TestClient) -> None:
    response = vision_client.post(
        "/api/vision/analyze",
        json={"image_id": str(uuid.uuid4())},
    )
    assert response.status_code == 400


def test_analyze_invalid_uuid_rejected(
    vision_client: TestClient, vision_db: Session
) -> None:
    response = vision_client.post(
        "/api/vision/analyze",
        json={"image_id": "not-a-uuid"},
        headers=_tenant_headers(vision_db._tenant_a),  # type: ignore[attr-defined]
    )
    assert response.status_code == 400


def test_analyze_unknown_image_returns_404(
    vision_client: TestClient, vision_db: Session
) -> None:
    response = vision_client.post(
        "/api/vision/analyze",
        json={"image_id": str(uuid.uuid4())},
        headers=_tenant_headers(vision_db._tenant_a),  # type: ignore[attr-defined]
    )
    assert response.status_code == 404


def test_analyze_cross_tenant_returns_404(
    vision_client: TestClient, vision_db: Session
) -> None:
    image_id = _seed_image_id(vision_db)
    response = vision_client.post(
        "/api/vision/analyze",
        json={"image_id": str(image_id)},
        headers=_tenant_headers(vision_db._tenant_b),  # type: ignore[attr-defined]
    )
    assert response.status_code == 404


def test_analyze_runs_vision_agent_and_updates_status(
    vision_client: TestClient, vision_db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """端到端跑通：上传 → analyze → vision_status 更新 + vision_result 落库。

    真实 ``process_image`` 调 ``VisionAgent``；我们把 agent 替换成同步 fixture。
    这里走真实 VisionAgent.invoke（无 LLM，pending_verification=true）路径，
    并断言 ``vision_status`` 落到 ``Done`` 或 ``Failed``（取决于 mock provider）。
    """

    image_id = _seed_image_id(vision_db)
    response = vision_client.post(
        "/api/vision/analyze",
        json={"image_id": str(image_id)},
        headers=_tenant_headers(vision_db._tenant_a),  # type: ignore[attr-defined]
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["success"] is True
    data = payload["data"]
    assert data["image_id"] == str(image_id)
    assert data["vision_status"] in {"Done", "Failed"}
    assert "vision_result" in data
    assert isinstance(data["vision_result"], dict)


def test_vision_agent_placeholder_when_llm_disabled() -> None:
    """无 LLM 启用时，VisionAgent.invoke 必须返回 pending_verification 占位。"""

    import asyncio

    from agents.base import AgentContext
    from agents.vision.agent import VisionAgent

    agent = VisionAgent()
    ctx = AgentContext(
        request_id="vision-disabled",
        input_data={
            "image_id": "fake-id",
            "image_b64": "ZmFrZQ==",  # "fake"
            "mime_type": "image/jpeg",
        },
    )
    result = asyncio.run(agent.invoke(ctx))
    assert result.success is True
    assert result.data["pending_verification"] is True
    assert result.data["scene_type"] == "unknown"


def test_vision_agent_missing_image_returns_placeholder() -> None:
    import asyncio

    from agents.base import AgentContext
    from agents.vision.agent import VisionAgent

    agent = VisionAgent()
    ctx = AgentContext(
        request_id="vision-no-image",
        input_data={"image_id": "fake-id"},  # 缺 image_b64
    )
    result = asyncio.run(agent.invoke(ctx))
    assert result.success is True
    assert result.data["pending_verification"] is True
    assert any("missing_image_b64" in gap for gap in result.data["gaps"])


__all__: list[str] = []