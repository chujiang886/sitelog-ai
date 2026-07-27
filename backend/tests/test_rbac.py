"""Phase 2.2 / 2.2.6 RBAC 基础建设测试。

覆盖：
- 密码哈希/校验；
- JWT 签发/校验（roundtrip / 错误 secret / 过期 / 畸形 / 缺失 secret fail-closed）；
- 登录（成功 / 错误密码 / 未知用户）；
- 当前用户（无 token → 401 / 非法 token → 401 / 非 active → 401 / 正常返回主体）；
- 角色权限（admin 可 analysis:create；viewer 缺 upload:create → 403 明确信息）；
- 越权（无 token 访问受保护 API → 401）；
- tenant 隔离（不同租户 token 的 tenant_id 不同）。
"""

from __future__ import annotations

import uuid

import pytest

from app.core import security
from app.core.security import AuthError


# --------------------------------------------------------------------------- #
# 密码                                                                         #
# --------------------------------------------------------------------------- #


def test_password_hash_roundtrip() -> None:
    h = security.hash_password("secret123")
    assert h.startswith("pbkdf2_sha256$")
    assert security.verify_password("secret123", h) is True
    assert security.verify_password("wrong", h) is False


# --------------------------------------------------------------------------- #
# JWT                                                                          #
# --------------------------------------------------------------------------- #


def test_jwt_roundtrip(rbac_env) -> None:
    token = security.create_access_token(
        sub=rbac_env["ids"]["admin_a"],
        tenant_id=rbac_env["ids"]["ta"],
        email="admin@a.local",
        role="admin",
        roles=["admin"],
        permissions=["upload:create", "upload:read"],
    )
    claims = security.decode_access_token(token)
    assert claims["sub"] == str(rbac_env["ids"]["admin_a"])
    assert claims["tenant_id"] == str(rbac_env["ids"]["ta"])
    assert set(claims["permissions"]) == {"upload:create", "upload:read"}
    assert claims["type"] == "access"


def test_jwt_wrong_secret(monkeypatch, rbac_env) -> None:
    token = security.create_access_token(
        sub=rbac_env["ids"]["admin_a"],
        tenant_id=rbac_env["ids"]["ta"],
        email="a",
        role="admin",
        roles=["admin"],
        permissions=[],
    )
    monkeypatch.setenv("JWT_SECRET", "different-secret")
    from app.core.config import get_settings

    get_settings.cache_clear()
    with pytest.raises(AuthError):
        security.decode_access_token(token)


def test_jwt_expired(rbac_env) -> None:
    """负数 TTL 直接签发已过期 token → decode 必须拒绝。"""

    token = security.create_access_token(
        sub=rbac_env["ids"]["admin_a"],
        tenant_id=rbac_env["ids"]["ta"],
        email="a",
        role="admin",
        roles=["admin"],
        permissions=[],
        expires_minutes=-1,
    )
    with pytest.raises(AuthError):
        security.decode_access_token(token)


def test_jwt_malformed() -> None:
    with pytest.raises(AuthError):
        security.decode_access_token("not-a-jwt")


def test_missing_secret_fail_closed(monkeypatch) -> None:
    monkeypatch.delenv("JWT_SECRET", raising=False)
    from app.core.config import get_settings

    get_settings.cache_clear()
    with pytest.raises(security.AuthConfigError):
        security.create_access_token(
            sub=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            email="x",
            role="admin",
            roles=["admin"],
            permissions=[],
        )
    with pytest.raises(AuthError):
        security.decode_access_token("a.b.c")


# --------------------------------------------------------------------------- #
# 登录                                                                         #
# --------------------------------------------------------------------------- #


def test_login_success(rbac_env) -> None:
    resp = rbac_env["login"]("admin@a.local", rbac_env["ids"]["pw"])
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["token_type"] == "bearer"
    assert isinstance(data["access_token"], str) and data["access_token"]


def test_login_wrong_password(rbac_env) -> None:
    resp = rbac_env["login"]("admin@a.local", "wrong-pw")
    assert resp.status_code == 401


def test_login_unknown_user(rbac_env) -> None:
    resp = rbac_env["login"]("nobody@x.local", "x")
    assert resp.status_code == 401


# --------------------------------------------------------------------------- #
# 当前用户 & 依赖                                                              #
# --------------------------------------------------------------------------- #


def test_me_requires_token(rbac_env) -> None:
    resp = rbac_env["client"].get("/api/auth/me")
    assert resp.status_code == 401


def test_invalid_token_rejected(rbac_env) -> None:
    resp = rbac_env["client"].get(
        "/api/auth/me", headers={"Authorization": "Bearer not.a.valid.token"}
    )
    assert resp.status_code == 401


def test_me_returns_principals(rbac_env) -> None:
    resp = rbac_env["client"].get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {rbac_env['admin_a_token']}"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["tenant_id"] == str(rbac_env["ids"]["ta"])
    assert "admin" in data["roles"]
    assert "upload:create" in data["permissions"]
    assert "user:manage" in data["permissions"]


def test_suspended_user_rejected(rbac_env) -> None:
    resp = rbac_env["client"].get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {rbac_env['suspended_a_token']}"},
    )
    assert resp.status_code == 401


def test_protected_without_token(rbac_env) -> None:
    resp = rbac_env["client"].post("/api/analysis/run", json={"address": "x"})
    assert resp.status_code == 401


def test_admin_can_access_analysis(rbac_env, monkeypatch) -> None:
    monkeypatch.setattr(
        "agents.config_loader.load_llm_config",
        lambda: {"enabled": False, "track_a": {}, "track_b": {}},
    )
    resp = rbac_env["client"].post(
        "/api/analysis/run",
        json={"address": "x"},
        headers={"Authorization": f"Bearer {rbac_env['admin_a_token']}"},
    )
    assert resp.status_code == 200


def test_viewer_cannot_upload(rbac_env) -> None:
    files = {
        "file": (
            "a.jpg",
            b"\xff\xd8\xff\xe0BOIPx\x01\x02\x03\xff\xd9",
            "image/jpeg",
        )
    }
    resp = rbac_env["client"].post(
        "/api/uploads",
        files=files,
        headers={"Authorization": f"Bearer {rbac_env['viewer_a_token']}"},
    )
    assert resp.status_code == 403
    assert "Permission denied: requires 'upload:create'" in resp.json()["error"]["message"]


def test_tenant_isolation_token_claims(rbac_env) -> None:
    me_a = rbac_env["client"].get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {rbac_env['admin_a_token']}"},
    ).json()["data"]
    me_b = rbac_env["client"].get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {rbac_env['admin_b_token']}"},
    ).json()["data"]
    assert me_a["tenant_id"] == str(rbac_env["ids"]["ta"])
    assert me_b["tenant_id"] == str(rbac_env["ids"]["tb"])
    assert me_a["tenant_id"] != me_b["tenant_id"]


__all__: list[str] = []
