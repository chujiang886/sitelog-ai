"""Phase 1 / T08 图片上传 API 集成测试（RBAC 改造后）。

覆盖：
- 上传合法 jpeg / png / webp → 200 + envelope；
- 上传非法 mime / 空文件 → 400；
- 鉴权：无 token → 401；viewer 缺 upload:create → 403；
- tenant 隔离：跨租户访问 → 404；
- GET /api/uploads/{id} → 元数据 + tenant 隔离；
- 重复 sha256 → 复用行（dedup）。

鉴权改造：原 X-Tenant-Id / X-User-Id 头改为 JWT Bearer token，租户取自
token 的 tenant_id（服务端可信）。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core import storage as storage_module


@pytest.fixture()
def storage_tmp(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """把 STORAGE_ROOT 重定向到 tmp_path；测试结束后还原。"""

    path = Path(tmp_path)
    monkeypatch.setattr(storage_module, "DEFAULT_STORAGE_ROOT", path, raising=False)
    monkeypatch.setattr(storage_module, "resolve_storage_root", lambda: path, raising=False)
    return path


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _make_image_bytes(seed: int = 0) -> bytes:
    """构造一个最小的合法 JPEG 字节流（仅供 hash / 大小校验，不校验像素）。"""

    payload = (
        bytes([0xFF, 0xD8, 0xFF, 0xE0])
        + b"BOIP_TEST"
        + bytes([seed] * 16)
        + bytes([0xFF, 0xD9])
    )
    return payload


# --------------------------------------------------------------------------- #
# POST /api/uploads                                                             #
# --------------------------------------------------------------------------- #


def test_upload_jpeg_returns_envelope_and_storage(
    rbac_env, storage_tmp
) -> None:
    """合法 JPEG 上传 → 200 + 写盘 + 落库。"""

    client: TestClient = rbac_env["client"]
    files = {"file": ("balcony.jpg", _make_image_bytes(1), "image/jpeg")}
    response = client.post(
        "/api/uploads",
        files=files,
        headers=_headers(rbac_env["admin_a_token"]),
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["success"] is True
    data = payload["data"]
    assert data["vision_status"] in {"Pending", "Processing", "Done", "Failed"}
    assert data["mime_type"] == "image/jpeg"
    assert data["size_bytes"] == len(_make_image_bytes(1))

    storage_dir = storage_tmp / str(rbac_env["ids"]["ta"])
    written_files = list(storage_dir.glob("*.jpg"))
    assert written_files, "expected at least one stored image"


def test_upload_png_accepted(rbac_env) -> None:
    client: TestClient = rbac_env["client"]
    files = {"file": ("plan.png", _make_image_bytes(2), "image/png")}
    response = client.post(
        "/api/uploads", files=files, headers=_headers(rbac_env["admin_a_token"])
    )
    assert response.status_code == 200
    assert response.json()["data"]["mime_type"] == "image/png"


def test_upload_webp_accepted(rbac_env) -> None:
    client: TestClient = rbac_env["client"]
    files = {"file": ("plan.webp", _make_image_bytes(3), "image/webp")}
    response = client.post(
        "/api/uploads", files=files, headers=_headers(rbac_env["admin_a_token"])
    )
    assert response.status_code == 200
    assert response.json()["data"]["mime_type"] == "image/webp"


def test_upload_unsupported_mime_rejected(rbac_env) -> None:
    client: TestClient = rbac_env["client"]
    files = {"file": ("a.gif", _make_image_bytes(4), "image/gif")}
    response = client.post(
        "/api/uploads", files=files, headers=_headers(rbac_env["admin_a_token"])
    )
    assert response.status_code == 400
    assert "Unsupported mime_type" in response.json()["detail"]


def test_upload_empty_file_rejected(rbac_env) -> None:
    client: TestClient = rbac_env["client"]
    files = {"file": ("empty.jpg", b"", "image/jpeg")}
    response = client.post(
        "/api/uploads", files=files, headers=_headers(rbac_env["admin_a_token"])
    )
    assert response.status_code == 400


def test_upload_without_token_rejected(rbac_env) -> None:
    """未携带 token 上传 → 401（受保护 API 必须失败）。"""

    client: TestClient = rbac_env["client"]
    files = {"file": ("a.jpg", _make_image_bytes(5), "image/jpeg")}
    response = client.post("/api/uploads", files=files)
    assert response.status_code == 401


def test_upload_viewer_forbidden(rbac_env) -> None:
    """viewer 缺 upload:create → 403 明确信息。"""

    client: TestClient = rbac_env["client"]
    files = {"file": ("a.jpg", _make_image_bytes(5), "image/jpeg")}
    response = client.post(
        "/api/uploads", files=files, headers=_headers(rbac_env["viewer_a_token"])
    )
    assert response.status_code == 403
    assert "Permission denied: requires 'upload:create'" in response.json()["error"]["message"]


def test_upload_dedup_by_sha256(rbac_env) -> None:
    """同一图片上传两次 → 第二次复用行，image_id 相同。"""

    client: TestClient = rbac_env["client"]
    payload_bytes = _make_image_bytes(6)
    files1 = {"file": ("a.jpg", payload_bytes, "image/jpeg")}
    response1 = client.post(
        "/api/uploads", files=files1, headers=_headers(rbac_env["admin_a_token"])
    )
    assert response1.status_code == 200
    id_1 = response1.json()["data"]["image_id"]

    files2 = {"file": ("b.jpg", payload_bytes, "image/jpeg")}
    response2 = client.post(
        "/api/uploads", files=files2, headers=_headers(rbac_env["admin_a_token"])
    )
    assert response2.status_code == 200
    id_2 = response2.json()["data"]["image_id"]
    assert id_1 == id_2


# --------------------------------------------------------------------------- #
# GET /api/uploads/{id}                                                         #
# --------------------------------------------------------------------------- #


def test_get_image_returns_metadata(rbac_env) -> None:
    client: TestClient = rbac_env["client"]
    files = {"file": ("a.jpg", _make_image_bytes(7), "image/jpeg")}
    upload_response = client.post(
        "/api/uploads", files=files, headers=_headers(rbac_env["admin_a_token"])
    )
    image_id = upload_response.json()["data"]["image_id"]

    response = client.get(
        f"/api/uploads/{image_id}",
        headers=_headers(rbac_env["admin_a_token"]),
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == image_id
    assert data["tenant_id"] == str(rbac_env["ids"]["ta"])
    assert data["mime_type"] == "image/jpeg"


def test_get_image_cross_tenant_returns_404(rbac_env) -> None:
    """tenant B 不能读 tenant A 的图片（tenant 隔离）。"""

    client: TestClient = rbac_env["client"]
    files = {"file": ("a.jpg", _make_image_bytes(8), "image/jpeg")}
    upload_response = client.post(
        "/api/uploads", files=files, headers=_headers(rbac_env["admin_a_token"])
    )
    image_id = upload_response.json()["data"]["image_id"]

    response = client.get(
        f"/api/uploads/{image_id}",
        headers=_headers(rbac_env["admin_b_token"]),
    )
    assert response.status_code == 404


def test_get_image_invalid_uuid_rejected(rbac_env) -> None:
    client: TestClient = rbac_env["client"]
    response = client.get(
        "/api/uploads/not-a-uuid",
        headers=_headers(rbac_env["admin_a_token"]),
    )
    assert response.status_code == 400


__all__: list[str] = []
