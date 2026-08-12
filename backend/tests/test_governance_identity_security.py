"""企业身份认证与权限治理安全测试（Phase 3.8.28 T5）。

本文件钉死 Phase 3.8.28 的全部 fail-closed 行为，是身份链路"只此一条路径、
任何失败都拒绝"的回归护栏。

六类 fail-closed：
  1. JWT 校验（签名坏 / 结构坏 / 缺 secret）  → 401 / 500
  2. 过期                                     → 401
  3. 非法身份（非真人 / 主体失效）           → 403 / 401
  4. 权限拒绝（默认拒绝）                    → 403
  5. 跨组织                                   → 403
  6. AI 伪造（agent / service 凭据）         → 403

外加两类：
  - 头伪造回归：``x-actor-id`` / ``x-actor-kind`` 一律 400（不静默忽略）
  - 词表对齐：前端 TS 词表与后端 Python 词表逐字一致（权限 / 角色权限 /
    禁语 / 治理角色命名空间）

设计原则：测试里**没有任何伪造身份的捷径**。想成为某人，必须真的以那个人
登录一次（``governance_env`` 的 token 都是真实登录签发的），或显式持有其
合法凭据——这正是本阶段要确立的纪律。
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import re
import time
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.core import security
from app.core.security import create_access_token
from app.identity import GOVERNANCE_ROLES
from app.identity.dependencies import (
    LEGACY_IDENTITY_HEADERS,
    assert_no_legacy_identity_headers,
    http_status_for,
    require_governance_permission,
    require_same_org,
)
from app.identity.errors import (
    IdentityConfigError,
    IdentityCrossOrgError,
    IdentityError,
    IdentityHeaderForgeryError,
    IdentityNotHumanError,
    IdentityPermissionDeniedError,
    IdentityRedLineViolationError,
    IdentitySubjectInactiveError,
    IdentityTokenExpiredError,
    IdentityTokenInvalidError,
    IdentityUnauthenticatedError,
)
from app.identity.permissions import (
    ALL_GOVERNANCE_PERMISSIONS,
    FORBIDDEN_PERMISSION_PATTERNS,
    GOVERNANCE_ROLE_PERMISSIONS,
    GovernancePermission,
    assert_no_forbidden_permission,
    permissions_for_roles,
)
from app.identity.principal import ActorKind, GovernancePrincipal, build_principal
from app.identity.resolver import ClaimsOnlyPrincipalResolver, _reject_non_human_claim
from app.identity.service import IdentityAuthenticationService
from app.identity.verifier import JwtTokenVerifier, VerifiedClaims
from tests.conftest import TEST_JWT_SECRET


# --------------------------------------------------------------------------- #
# 本地凭据锻造（仅用于"失败应当被拒"的负面用例）                              #
# --------------------------------------------------------------------------- #


def _forge_token(
    *,
    sub: str,
    tenant_id: str,
    email: str,
    roles: list[str],
    actor_kind: str | None = None,
    expires_minutes: int = 30,
    secret: str = TEST_JWT_SECRET,
) -> str:
    """用与 ``create_access_token`` 相同的 HS256 算法签一张可控制的凭据。

    仅用于构造"本应被拒绝"的负面场景（过期 / 跨组织 / AI 伪造），
    不用于任何"应当通过"的成功路径——那一侧一律走真实登录。
    """

    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {
        "sub": str(sub),
        "tenant_id": str(tenant_id),
        "email": email,
        "role": roles[0] if roles else "designer",
        "roles": list(roles),
        "permissions": [],
        "iat": now,
        "exp": now + expires_minutes * 60,
        "type": "access",
    }
    if actor_kind is not None:
        payload["actor_kind"] = actor_kind

    def _b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    signing_input = (
        f"{_b64(json.dumps(header, separators=(',', ':')).encode())}"
        f".{_b64(json.dumps(payload, separators=(',', ':')).encode())}"
    )
    sig = hmac.new(
        secret.encode(), signing_input.encode(), hashlib.sha256
    ).digest()
    return f"{signing_input}.{_b64(sig)}"


# --------------------------------------------------------------------------- #
# 1. JWT 校验 fail-closed                                                       #
# --------------------------------------------------------------------------- #


@pytest.fixture()
def _jwt_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", TEST_JWT_SECRET)
    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_jwt_verifier_rejects_empty_token(_jwt_secret) -> None:
    with pytest.raises(IdentityUnauthenticatedError):
        JwtTokenVerifier().verify("")


def test_jwt_verifier_rejects_malformed_token(_jwt_secret) -> None:
    with pytest.raises(IdentityTokenInvalidError):
        JwtTokenVerifier().verify("not-a-jwt")


def test_jwt_verifier_rejects_wrong_signature(_jwt_secret) -> None:
    good = create_access_token(
        sub="11111111-1111-1111-1111-111111111111",
        tenant_id="22222222-2222-2222-2222-222222222222",
        email="a@a.local",
        role="designer",
        roles=["designer"],
        permissions=[],
    )
    header, payload, _sig = good.split(".")
    tampered = f"{header}.{payload}.deadbeef"
    with pytest.raises(IdentityTokenInvalidError):
        JwtTokenVerifier().verify(tampered)


def test_jwt_verifier_rejects_missing_sub(_jwt_secret) -> None:
    tok = _forge_token(
        sub="", tenant_id="22222222-2222-2222-2222-222222222222",
        email="a@a.local", roles=["designer"],
    )
    # sub 空串经 strip 后为空，验证器应拒绝。
    with pytest.raises(IdentityTokenInvalidError):
        JwtTokenVerifier().verify(tok)


def test_jwt_verifier_rejects_missing_org(_jwt_secret) -> None:
    tok = _forge_token(
        sub="11111111-1111-1111-1111-111111111111", tenant_id="",
        email="a@a.local", roles=["designer"],
    )
    with pytest.raises(IdentityTokenInvalidError):
        JwtTokenVerifier().verify(tok)


def test_jwt_verifier_rejects_non_list_roles(_jwt_secret) -> None:
    # 直接构造一个 roles 为字符串的 payload（绕过 forge 的类型约束）。
    payload = {
        "sub": "11111111-1111-1111-1111-111111111111",
        "tenant_id": "22222222-2222-2222-2222-222222222222",
        "email": "a@a.local",
        "roles": "designer",  # 应为 list
        "exp": int(time.time()) + 3600,
        "type": "access",
    }
    header = {"alg": "HS256", "typ": "JWT"}
    def _b64(d): return base64.urlsafe_b64encode(d).rstrip(b"=").decode()
    signing_input = (
        f"{_b64(json.dumps(header, separators=(',', ':')).encode())}"
        f".{_b64(json.dumps(payload, separators=(',', ':')).encode())}"
    )
    sig = hmac.new(TEST_JWT_SECRET.encode(), signing_input.encode(),
                   hashlib.sha256).digest()
    tok = f"{signing_input}.{_b64(sig)}"
    with pytest.raises(IdentityTokenInvalidError):
        JwtTokenVerifier().verify(tok)


def test_jwt_verifier_config_missing_secret_fails_closed(monkeypatch) -> None:
    """JWT_SECRET 缺失时绝不降级放行，而是整体拒绝。

    注：直接用 delenv 不可靠——pydantic-settings 仍会从 ``.env`` 文件回读，
    因此这里把 ``get_settings`` 整体替换为一个"secret 为空"的替身，模拟
    "身份基础设施未配置"这一真正关心的失败模式。
    """

    class _EmptySecret:
        jwt_secret = ""

    # 必须同时替换两个命名空间：
    #  - ``app.core.config.get_settings``  ：被 ``verifier.is_configured`` 通过
    #    方法内的 ``from app.core.config import get_settings`` 局部导入在调用时查到；
    #  - ``app.core.security.get_settings``：被 ``decode_access_token`` →
    #    ``_get_jwt_secret`` 通过 ``security.py`` 顶层的
    #    ``from app.core.config import get_settings`` 绑定引用。
    # 只 patch config 一侧时，monkeypatch 只改写 config 模块的属性，不会改掉
    # security 模块里已绑定的同名引用，于是真实 secret 仍被读到、token 验签通过，
    # 导致"缺失 secret 必须 fail-closed"这一关键断言从未真正执行（历史误报为通过/
    # 实际 DID NOT RAISE）。本修复让该 fail-closed 路径真正被覆盖。
    monkeypatch.setattr("app.core.config.get_settings", lambda: _EmptySecret())
    monkeypatch.setattr("app.core.security.get_settings", lambda: _EmptySecret())
    verifier = JwtTokenVerifier()
    assert verifier.is_configured() is False
    # 需传结构合法的 3 段 token，decode 才会走到 secret 校验（空 secret）分支。
    structurally_valid = _forge_token(
        sub="11111111-1111-1111-1111-111111111111",
        tenant_id="22222222-2222-2222-2222-222222222222",
        email="a@a.local", roles=["designer"],
    )
    with pytest.raises(IdentityConfigError):
        verifier.verify(structurally_valid)


def test_jwt_verifier_carries_actor_kind_claim(_jwt_secret) -> None:
    tok = _forge_token(
        sub="11111111-1111-1111-1111-111111111111",
        tenant_id="22222222-2222-2222-2222-222222222222",
        email="a@a.local", roles=["designer"], actor_kind="agent",
    )
    claims = JwtTokenVerifier().verify(tok)
    assert claims.actor_kind_claim == "agent"
    assert claims.subject == "11111111-1111-1111-1111-111111111111"


# --------------------------------------------------------------------------- #
# 2. 过期 fail-closed                                                          #
# --------------------------------------------------------------------------- #


def test_jwt_verifier_rejects_expired_token(_jwt_secret) -> None:
    expired = _forge_token(
        sub="11111111-1111-1111-1111-111111111111",
        tenant_id="22222222-2222-2222-2222-222222222222",
        email="a@a.local", roles=["designer"], expires_minutes=-1,
    )
    with pytest.raises(IdentityTokenExpiredError):
        JwtTokenVerifier().verify(expired)


def test_expired_token_rejected_over_http(governance_env) -> None:
    env = governance_env
    expired = _forge_token(
        sub=env["ids"]["gov_admin"], tenant_id=env["ids"]["tenant_a"],
        email="gov-admin@a.local", roles=["governance-admin"],
        expires_minutes=-1,
    )
    r = env["client"].get(
        "/governance/me", headers={"Authorization": f"Bearer {expired}"}
    )
    assert r.status_code == 401


# --------------------------------------------------------------------------- #
# 3. 非法身份 fail-closed（非真人 / 主体失效）                                  #
# --------------------------------------------------------------------------- #


def test_build_principal_rejects_non_human() -> None:
    with pytest.raises(IdentityNotHumanError):
        build_principal(
            actor_id="u1", org_id="o1", roles=["governance-admin"],
            permissions=[], actor_kind=ActorKind.AGENT,
        )


def test_build_principal_rejects_missing_actor_id() -> None:
    with pytest.raises(IdentityTokenInvalidError):
        build_principal(
            actor_id="", org_id="o1", roles=[], permissions=[],
        )


def test_resolver_rejects_forbidden_role_name() -> None:
    """角色名本身命中禁语（如 auto-approve-role）即整份拒绝（红线②）。"""

    claims = VerifiedClaims(
        subject="u1", org_id="o1", roles=("auto-approve-role",),
    )
    resolver = ClaimsOnlyPrincipalResolver(trust_reason="unit-test")
    with pytest.raises(IdentityRedLineViolationError):
        asyncio.run(resolver.resolve(claims))


def test_resolver_rejects_non_human_claim() -> None:
    claims = VerifiedClaims(
        subject="u1", org_id="o1", roles=("governance-admin",),
        actor_kind_claim="agent",
    )
    with pytest.raises(IdentityNotHumanError):
        _reject_non_human_claim(claims)


def test_claims_only_resolver_rejects_non_human() -> None:
    claims = VerifiedClaims(
        subject="u1", org_id="o1", roles=("governance-admin",),
        actor_kind_claim="service",
    )
    resolver = ClaimsOnlyPrincipalResolver(trust_reason="unit-test")
    with pytest.raises(IdentityNotHumanError):
        asyncio.run(resolver.resolve(claims))


def test_suspended_subject_rejected_over_http(governance_env) -> None:
    """凭据仍在手上、但主体已停用 ⇒ 401（不是 403，也不是放行）。"""

    env = governance_env
    r = env["client"].get(
        "/governance/me", headers=env["bearer"](env["suspended_token"])
    )
    assert r.status_code == 401


# --------------------------------------------------------------------------- #
# 4. 权限拒绝 fail-closed（默认拒绝）                                           #
# --------------------------------------------------------------------------- #


def _principal_with(roles, permissions):
    return build_principal(
        actor_id="u1", org_id="o1", roles=roles,
        permissions=permissions,
    )


def test_require_governance_permission_denies_by_default() -> None:
    # 没有任何权限的主体尝试需要 WORKFLOW_CLOSE 的动作 → 403。
    principal = _principal_with(
        ["governance-viewer"], [GovernancePermission.WORKFLOW_READ]
    )
    dep = require_governance_permission(GovernancePermission.WORKFLOW_CLOSE)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(dep(principal))
    assert exc.value.status_code == 403


def test_require_governance_permission_allows_when_held() -> None:
    principal = _principal_with(
        ["governance-admin"], list(ALL_GOVERNANCE_PERMISSIONS)
    )
    dep = require_governance_permission(GovernancePermission.WORKFLOW_CLOSE)

    got = asyncio.run(dep(principal))
    assert got is principal


@pytest.mark.parametrize(
    "token_key,endpoint,expect_status",
    [
        # 默认拒绝：只有业务角色的人访问受治理权限保护的路由 → 403
        ("business_only_token", "/governance/reviews", 403),
        ("business_only_token", "/governance/summary", 403),
        ("business_only_token", "/governance/audit", 403),
        # 职责分离：viewer 能读 reviews（WORKFLOW_READ）但读不了 audit（AUDIT_READ）
        ("viewer_token", "/governance/reviews", 200),
        ("viewer_token", "/governance/audit", 403),
        # admin 全通
        ("admin_token", "/governance/audit", 200),
        ("admin_token", "/governance/reviews", 200),
    ],
)
def test_permission_denial_over_http(governance_env, token_key, endpoint, expect_status) -> None:
    env = governance_env
    r = env["client"].get(endpoint, headers=env["bearer"](env[token_key]))
    assert r.status_code == expect_status, r.text


def test_permissions_for_roles_default_deny_unknown_role() -> None:
    # 未知角色贡献空集，而不是"认识就给权限"。
    assert permissions_for_roles(["nonexistent-role"]) == frozenset()
    # 纯业务角色在治理维度上给空集。
    assert permissions_for_roles(["admin", "designer"]) == frozenset()


# --------------------------------------------------------------------------- #
# 5. 跨组织 fail-closed                                                        #
# --------------------------------------------------------------------------- #


def test_require_same_org_rejects_cross_org() -> None:
    principal = _principal_with(["governance-admin"], list(ALL_GOVERNANCE_PERMISSIONS))
    with pytest.raises(HTTPException) as exc:
        require_same_org(principal, "some-other-org")
    assert exc.value.status_code == 403


def test_require_same_org_allows_same_org() -> None:
    principal = _principal_with(["governance-admin"], list(ALL_GOVERNANCE_PERMISSIONS))
    assert require_same_org(principal, principal.org_id) == principal.org_id


def test_cross_org_token_reuse_rejected_over_http(governance_env) -> None:
    """A 租户用户的凭据若声明属于 B 租户（跨租户复用）⇒ 401。"""

    env = governance_env
    # sub 是 A 租户真实用户，但伪造 tenant_id 为 B。
    tok = _forge_token(
        sub=env["ids"]["gov_admin"], tenant_id=env["ids"]["tenant_b"],
        email="gov-admin@a.local", roles=["governance-admin"],
    )
    r = env["client"].get(
        "/governance/me", headers={"Authorization": f"Bearer {tok}"}
    )
    assert r.status_code == 401


# --------------------------------------------------------------------------- #
# 6. AI 伪造 fail-closed（agent / service 凭据）                               #
# --------------------------------------------------------------------------- #


def test_ai_forgery_rejected_over_http(governance_env) -> None:
    """持有合法用户 id、但凭据自称 actor_kind=agent ⇒ 403（红线⑥）。"""

    env = governance_env
    tok = _forge_token(
        sub=env["ids"]["gov_admin"], tenant_id=env["ids"]["tenant_a"],
        email="gov-admin@a.local", roles=["governance-admin"],
        actor_kind="agent",
    )
    r = env["client"].get(
        "/governance/me", headers={"Authorization": f"Bearer {tok}"}
    )
    assert r.status_code == 403


def test_service_forgery_rejected_over_http(governance_env) -> None:
    env = governance_env
    tok = _forge_token(
        sub=env["ids"]["gov_admin"], tenant_id=env["ids"]["tenant_a"],
        email="gov-admin@a.local", roles=["governance-admin"],
        actor_kind="service",
    )
    r = env["client"].get(
        "/governance/me", headers={"Authorization": f"Bearer {tok}"}
    )
    assert r.status_code == 403


def test_forbidden_permission_claim_rejected(governance_env) -> None:
    """凭据声明了 auto_approve ⇒ 整份凭据不可信 ⇒ 拒绝。"""

    env = governance_env
    # 在 token 里塞一个禁语权限名（permissions 字段）。
    tok = _forge_token(
        sub=env["ids"]["gov_admin"], tenant_id=env["ids"]["tenant_a"],
        email="gov-admin@a.local", roles=["governance-admin"],
    )
    # 直接打 /governance/me 时权限来自后端 DB，不会带禁语；这里改测底层断言。
    with pytest.raises(IdentityRedLineViolationError):
        assert_no_forbidden_permission(["governance:auto_approve"])


# --------------------------------------------------------------------------- #
# 头伪造回归：x-actor-id / x-actor-kind 一律 400                               #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("header_name,header_value", [
    ("x-actor-id", "someone"),
    ("x-actor-kind", "user"),
    ("X-Actor-Id", "someone"),  # 大小写变体
    ("X-ACTOR-KIND", "user"),
])
def test_legacy_identity_header_rejected(governance_env, header_name, header_value) -> None:
    env = governance_env
    headers = {"Authorization": f"Bearer {env['admin_token']}"}
    # 多写一行确保两个头都带上时仍只报 400；逐个用例只带一个。
    if header_name.lower() == "x-actor-id":
        headers["x-actor-id"] = header_value
    else:
        headers["x-actor-kind"] = header_value
    r = env["client"].get("/governance/me", headers=headers)
    assert r.status_code == 400, r.text


def test_both_legacy_headers_rejected(governance_env) -> None:
    env = governance_env
    r = env["client"].get(
        "/governance/me",
        headers={
            "Authorization": f"Bearer {env['admin_token']}",
            "x-actor-id": "someone",
            "x-actor-kind": "user",
        },
    )
    assert r.status_code == 400


def test_assert_no_legacy_identity_headers_helper() -> None:
    # 两个头都不在 → 不抛；任一在 → 抛。
    assert_no_legacy_identity_headers(None, None)
    with pytest.raises(IdentityHeaderForgeryError):
        assert_no_legacy_identity_headers("x", None)
    with pytest.raises(IdentityHeaderForgeryError):
        assert_no_legacy_identity_headers(None, "user")


def test_legacy_header_constant_regression() -> None:
    # 如果有人在前端/后端新增了"身份头"，必须同步到这里，否则视为回归。
    assert set(LEGACY_IDENTITY_HEADERS) == {"x-actor-id", "x-actor-kind"}


# --------------------------------------------------------------------------- #
# HTTP 状态码映射 fail-closed（未知身份异常一律 403）                           #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("error,expected_status", [
    (IdentityHeaderForgeryError("x"), 400),
    (IdentityConfigError("x"), 500),
    (IdentityTokenExpiredError("x"), 401),
    (IdentityTokenInvalidError("x"), 401),
    (IdentityUnauthenticatedError("x"), 401),
    (IdentitySubjectInactiveError("x"), 401),
    (IdentityNotHumanError("x"), 403),
    (IdentityRedLineViolationError("x"), 403),
    (IdentityPermissionDeniedError("x"), 403),
    (IdentityCrossOrgError("x"), 403),
])
def test_http_status_mapping(error, expected_status) -> None:
    assert http_status_for(error) == expected_status


def test_unknown_identity_error_fails_closed() -> None:
    class _Weird(IdentityError):
        pass
    assert http_status_for(_Weird("x")) == 403


# --------------------------------------------------------------------------- #
# 身份端点基础契约（认证即可访问，无需治理权限）                                #
# --------------------------------------------------------------------------- #


def test_governance_me_returns_self_for_admin(governance_env) -> None:
    env = governance_env
    r = env["client"].get(
        "/governance/me", headers=env["bearer"](env["admin_token"])
    )
    assert r.status_code == 200
    data = r.json()
    assert data["actor_id"] == env["ids"]["gov_admin"]
    assert data["has_governance_access"] is True
    assert "governance:workflow:close" in data["permissions"]


def test_governance_me_no_permission_is_empty_but_ok(governance_env) -> None:
    """登录了但没有任何治理角色 ⇒ 看到"你没权限"而不是 403 白屏；权限集为空。"""

    env = governance_env
    r = env["client"].get(
        "/governance/me", headers=env["bearer"](env["business_only_token"])
    )
    assert r.status_code == 200
    data = r.json()
    assert data["has_governance_access"] is False
    assert data["permissions"] == []


def test_governance_me_requires_auth(governance_env) -> None:
    env = governance_env
    r = env["client"].get("/governance/me")
    assert r.status_code == 401


def test_governance_catalog_authenticated_only(governance_env) -> None:
    env = governance_env
    r = env["client"].get(
        "/governance/catalog", headers=env["bearer"](env["viewer_token"])
    )
    assert r.status_code == 200
    body = r.json()
    assert {p["name"] for p in body["permissions"]} == {
        p.value for p in ALL_GOVERNANCE_PERMISSIONS
    }
    assert {role["name"] for role in body["roles"]} == set(GOVERNANCE_ROLES)


# --------------------------------------------------------------------------- #
# 词表对齐：前端 TS 词表与后端 Python 词表逐字一致                             #
# --------------------------------------------------------------------------- #

_FRONTEND_ROOT = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "identity"


def _read_frontend(rel: str) -> str:
    return (_FRONTEND_ROOT / rel).read_text(encoding="utf-8")


def _decl_index(src: str, name: str) -> int:
    m = re.search(r"const\s+" + re.escape(name) + r"\b", src)
    if not m:
        raise AssertionError(f"{name} not found in frontend source")
    return m.start()


def _extract_const_array(src: str, name: str) -> list[str]:
    i = _decl_index(src, name)
    m = re.search(r"=\s*\[", src[i:])
    b = i + m.end() - 1
    e = src.find("]", b)
    out = []
    for raw in src[b + 1:e].split(","):
        s = raw.split("//")[0].strip().strip('"').strip("'").strip()
        if s:
            out.append(s)
    return out


def _extract_role_permissions(src: str, name: str) -> dict[str, list[str]]:
    i = _decl_index(src, name)
    m = re.search(r"=\s*\{", src[i:])
    b = i + m.end() - 1
    depth = 0
    end = None
    for k in range(b, len(src)):
        if src[k] == "{":
            depth += 1
        elif src[k] == "}":
            depth -= 1
            if depth == 0:
                end = k
                break
    body = src[b + 1:end]
    out: dict[str, list[str]] = {}
    for rm in re.finditer(r'"([^"]+)":\s*\[(.*?)\]', body, re.DOTALL):
        role = rm.group(1)
        perms = [
            p.strip().strip('"').strip("'")
            for p in rm.group(2).split(",")
            if p.strip()
        ]
        out[role] = perms
    return out


def test_vocabulary_permissions_aligned() -> None:
    fe = _extract_const_array(_read_frontend("types.ts"), "ALL_GOVERNANCE_PERMISSIONS")
    be = [p.value for p in ALL_GOVERNANCE_PERMISSIONS]
    assert set(fe) == set(be), f"前端/后端治理权限词表不一致：{set(fe) ^ set(be)}"
    assert len(fe) == len(ALL_GOVERNANCE_PERMISSIONS)  # 无重复


def test_vocabulary_forbidden_patterns_aligned() -> None:
    fe = _extract_const_array(_read_frontend("types.ts"), "FORBIDDEN_PERMISSION_PATTERNS")
    be = list(FORBIDDEN_PERMISSION_PATTERNS)
    assert set(fe) == set(be), (
        f"前端/后端禁语词表不一致：{set(fe) ^ set(be)}"
    )
    assert len(fe) == len(be)  # 无重复、无遗漏


def test_vocabulary_role_permissions_aligned() -> None:
    fe_roles = _extract_role_permissions(_read_frontend("guards.ts"), "ROLE_PERMISSIONS")
    # 前端治理角色集合 == 后端治理角色集合
    assert set(fe_roles.keys()) == set(GOVERNANCE_ROLES)
    for role in GOVERNANCE_ROLES:
        fe = set(fe_roles.get(role, []))
        be = {p.value for p in GOVERNANCE_ROLE_PERMISSIONS[role]}
        assert fe == be, f"角色 {role} 的权限映射前后端不一致：{fe ^ be}"


def test_governance_roles_do_not_collide_with_business_roles() -> None:
    """治理角色与业务角色不共用命名空间（业务管理员 ≠ 治理审批人）。"""

    from app.core.security import RBAC_ROLES

    collision = set(GOVERNANCE_ROLES) & set(RBAC_ROLES)
    assert collision == set(), f"角色命名空间冲突：{collision}"
