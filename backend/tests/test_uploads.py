"""Phase 1 / T08 图片上传 API 集成测试。

覆盖：
- 上传合法 jpeg / png / webp → 200 + envelope；
- 上传非法 mime / 空文件 → 400；
- tenant 隔离：跨租户访问 → 404；
- GET /api/uploads/{id} → 元数据 + tenant 隔离；
- 重复 sha256 → 复用行（dedup）。
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
from app.db.models.tenant import Tenant
from app.db.models.user import User
from app.main import app
from app.core import storage as storage_module


# --------------------------------------------------------------------------- #
# 固定 storage 根（每个测试 tmp_path 隔离）                                       #
# --------------------------------------------------------------------------- #


@pytest.fixture()
def storage_tmp(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """把 STORAGE_ROOT 重定向到 tmp_path；测试结束后还原。"""

    monkeypatch.setattr(storage_module, "DEFAULT_STORAGE_ROOT", tmp_path, raising=False)
    monkeypatch.setattr(storage_module, "resolve_storage_root", lambda: tmp_path, raising=False)
    return tmp_path


# --------------------------------------------------------------------------- #
# SQLite in-memory db                                                          #
# --------------------------------------------------------------------------- #


@pytest.fixture()
def uploads_db() -> Iterator[Session]:
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
    tenant_a = Tenant(name="TenantA", slug=f"ta-{uuid.uuid4().hex}", status="active")
    tenant_b = Tenant(name="TenantB", slug=f"tb-{uuid.uuid4().hex}", status="active")
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
    session._user_id = user.id  # type: ignore[attr-defined]
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture()
def uploads_client(
    uploads_db: Session, storage_tmp: Path
) -> Iterator[TestClient]:
    """FastAPI TestClient；用 uploads_db 替换 get_db。"""

    from app.api import uploads as uploads_module

    def _override_get_db() -> Iterator[Session]:
        try:
            yield uploads_db
        finally:
            pass

    app.dependency_overrides[uploads_module.get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _tenant_headers(tenant_id: uuid.UUID, user_id: uuid.UUID | None = None) -> dict[str, str]:
    headers = {"X-Tenant-Id": str(tenant_id)}
    if user_id:
        headers["X-User-Id"] = str(user_id)
    return headers


def _make_image_bytes(seed: int = 0) -> bytes:
    """构造一个最小的合法 JPEG 字节流（仅供 hash / 大小校验，不校验像素）。

    这里我们直接构造字节序列：JPEG SOI / EOI 标记 + 任意填充，
    足以触发 MIME / size 校验通过。
    """

    payload = bytes([0xFF, 0xD8, 0xFF, 0xE0]) + b"BOIP_TEST" + bytes([seed] * 16) + bytes([0xFF, 0xD9])
    return payload


# --------------------------------------------------------------------------- #
# POST /api/uploads                                                             #
# --------------------------------------------------------------------------- #


def test_upload_jpeg_returns_envelope_and_storage(
    uploads_client: TestClient, uploads_db: Session, storage_tmp: Path
) -> None:
    """合法 JPEG 上传 → 200 + 写盘 + 落库。"""

    files = {"file": ("balcony.jpg", _make_image_bytes(1), "image/jpeg")}
    response = uploads_client.post(
        "/api/uploads",
        files=files,
        headers=_tenant_headers(uploads_db._tenant_a, uploads_db._user_id),  # type: ignore[attr-defined]
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["success"] is True
    data = payload["data"]
    assert data["vision_status"] in {"Pending", "Processing", "Done", "Failed"}
    assert data["mime_type"] == "image/jpeg"
    assert data["size_bytes"] == len(_make_image_bytes(1))

    # 写盘确认
    storage_dir = storage_tmp / str(uploads_db._tenant_a)  # type: ignore[attr-defined]
    written_files = list(storage_dir.glob("*.jpg"))
    assert written_files, "expected at least one stored image"


def test_upload_png_accepted(uploads_client: TestClient, uploads_db: Session) -> None:
    files = {"file": ("plan.png", _make_image_bytes(2), "image/png")}
    response = uploads_client.post(
        "/api/uploads",
        files=files,
        headers=_tenant_headers(uploads_db._tenant_a, uploads_db._user_id),  # type: ignore[attr-defined]
    )
    assert response.status_code == 200
    assert response.json()["data"]["mime_type"] == "image/png"


def test_upload_webp_accepted(uploads_client: TestClient, uploads_db: Session) -> None:
    files = {"file": ("plan.webp", _make_image_bytes(3), "image/webp")}
    response = uploads_client.post(
        "/api/uploads",
        files=files,
        headers=_tenant_headers(uploads_db._tenant_a, uploads_db._user_id),  # type: ignore[attr-defined]
    )
    assert response.status_code == 200
    assert response.json()["data"]["mime_type"] == "image/webp"


def test_upload_unsupported_mime_rejected(
    uploads_client: TestClient, uploads_db: Session
) -> None:
    files = {"file": ("a.gif", _make_image_bytes(4), "image/gif")}
    response = uploads_client.post(
        "/api/uploads",
        files=files,
        headers=_tenant_headers(uploads_db._tenant_a, uploads_db._user_id),  # type: ignore[attr-defined]
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "Unsupported mime_type" in detail


def test_upload_empty_file_rejected(
    uploads_client: TestClient, uploads_db: Session
) -> None:
    files = {"file": ("empty.jpg", b"", "image/jpeg")}
    response = uploads_client.post(
        "/api/uploads",
        files=files,
        headers=_tenant_headers(uploads_db._tenant_a, uploads_db._user_id),  # type: ignore[attr-defined]
    )
    assert response.status_code == 400


def test_upload_missing_tenant_header_rejected(uploads_client: TestClient) -> None:
    files = {"file": ("a.jpg", _make_image_bytes(5), "image/jpeg")}
    response = uploads_client.post("/api/uploads", files=files)
    assert response.status_code == 400


def test_upload_dedup_by_sha256(
    uploads_client: TestClient, uploads_db: Session
) -> None:
    """同一图片上传两次 → 第二次复用行，image_id 相同。"""

    payload_bytes = _make_image_bytes(6)
    files1 = {"file": ("a.jpg", payload_bytes, "image/jpeg")}
    response1 = uploads_client.post(
        "/api/uploads",
        files=files1,
        headers=_tenant_headers(uploads_db._tenant_a, uploads_db._user_id),  # type: ignore[attr-defined]
    )
    assert response1.status_code == 200
    id_1 = response1.json()["data"]["image_id"]

    files2 = {"file": ("b.jpg", payload_bytes, "image/jpeg")}
    response2 = uploads_client.post(
        "/api/uploads",
        files=files2,
        headers=_tenant_headers(uploads_db._tenant_a, uploads_db._user_id),  # type: ignore[attr-defined]
    )
    assert response2.status_code == 200
    id_2 = response2.json()["data"]["image_id"]
    assert id_1 == id_2


# --------------------------------------------------------------------------- #
# GET /api/uploads/{id}                                                         #
# --------------------------------------------------------------------------- #


def test_get_image_returns_metadata(
    uploads_client: TestClient, uploads_db: Session
) -> None:
    files = {"file": ("a.jpg", _make_image_bytes(7), "image/jpeg")}
    upload_response = uploads_client.post(
        "/api/uploads",
        files=files,
        headers=_tenant_headers(uploads_db._tenant_a, uploads_db._user_id),  # type: ignore[attr-defined]
    )
    image_id = upload_response.json()["data"]["image_id"]

    response = uploads_client.get(
        f"/api/uploads/{image_id}",
        headers=_tenant_headers(uploads_db._tenant_a),  # type: ignore[attr-defined]
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == image_id
    assert data["tenant_id"] == str(uploads_db._tenant_a)  # type: ignore[attr-defined]
    assert data["mime_type"] == "image/jpeg"


def test_get_image_cross_tenant_returns_404(
    uploads_client: TestClient, uploads_db: Session
) -> None:
    """tenant B 不能读 tenant A 的图片。"""

    files = {"file": ("a.jpg", _make_image_bytes(8), "image/jpeg")}
    upload_response = uploads_client.post(
        "/api/uploads",
        files=files,
        headers=_tenant_headers(uploads_db._tenant_a, uploads_db._user_id),  # type: ignore[attr-defined]
    )
    image_id = upload_response.json()["data"]["image_id"]

    response = uploads_client.get(
        f"/api/uploads/{image_id}",
        headers=_tenant_headers(uploads_db._tenant_b),  # type: ignore[attr-defined]
    )
    assert response.status_code == 404


def test_get_image_invalid_uuid_rejected(
    uploads_client: TestClient, uploads_db: Session
) -> None:
    response = uploads_client.get(
        "/api/uploads/not-a-uuid",
        headers=_tenant_headers(uploads_db._tenant_a),  # type: ignore[attr-defined]
    )
    assert response.status_code == 400


__all__: list[str] = []