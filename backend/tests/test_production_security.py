"""生产安全测试（Phase 3.8.29 T7）—— 六类 fail-closed 断言。

覆盖范围与对应任务：

1. **Cookie 安全**（T1）：HttpOnly / Secure / SameSite / 双 Cookie 职责分离；
2. **CSRF 双提交**（T1）：缺令牌、令牌不匹配、安全方法豁免、正确令牌放行；
3. **凭据通道优先级**（T1）：显式 Bearer 头优先、显式头独占、Cookie 兜底；
4. **OIDC / SSO 失败**（T2）：配置不全、依赖缺失一律 fail-closed，绝不降级；
5. **环境隔离**（T3）：生产禁 static-dev、禁测试密钥、强制 Secure、CORS 表态；
6. **安全审计**（T4）：动作白名单、append-only、权限拒绝与身份失败留痕。

所有断言的方向都是「不满足条件时必须拒绝」，而不是「满足条件时能通过」——
安全测试证明的是**关不上的门不存在**，不是**门能打开**。
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from app.core.auth_cookies import (
    DEFAULT_AUTH_COOKIE_NAME,
    DEFAULT_CSRF_COOKIE_NAME,
    DEFAULT_CSRF_HEADER_NAME,
    generate_csrf_token,
    resolve_bearer_credential,
    resolve_raw_token,
)
from app.core.config import (
    KNOWN_TEST_SECRETS,
    PRODUCTION_FORBIDDEN_IDENTITY_PROVIDERS,
    Settings,
)
from app.core.security_audit import (
    SECURITY_AUDIT_ACTIONS,
    SECURITY_AUDIT_SYSTEM_TENANT,
    SecurityAuditError,
    record_security_event,
)


# --------------------------------------------------------------------------- #
# 工具：伪造一个只带 cookies/headers 的最小 Request                            #
# --------------------------------------------------------------------------- #


class _FakeRequest:
    """只实现 ``cookies`` / ``headers`` 的最小请求替身。

    凭据解析函数只读这两处，用真 ``Request`` 需要构造 ASGI scope，噪音大于收益。
    """

    def __init__(self, cookies: dict | None = None, headers: dict | None = None):
        self.cookies = cookies or {}
        self.headers = headers or {}


def _prod_settings(**overrides) -> Settings:
    """构造一份"生产且合规"的基线配置，再按需覆盖单项制造违规。"""

    base = {
        "APP_ENV": "production",
        "JWT_SECRET": "a-real-and-sufficiently-long-production-secret",
        "CORS_ORIGINS": "https://boip.example.com",
        "IDENTITY_PROVIDER": "jwt",
        "STATIC_DEV_IDENTITY_ENABLED": False,
    }
    base.update(overrides)
    return Settings(**base)


# --------------------------------------------------------------------------- #
# 1. Cookie 安全属性                                                            #
# --------------------------------------------------------------------------- #


def test_login_sets_httponly_credential_cookie(rbac_env) -> None:
    """登录必须把凭据种在 HttpOnly Cookie 上 —— JS 读不到才挡得住 XSS。"""

    resp = rbac_env["login"]("admin@a.local", rbac_env["ids"]["pw"])
    assert resp.status_code == 200, resp.text

    set_cookie_headers = resp.headers.get_list("set-cookie")
    auth_cookie = next(
        (h for h in set_cookie_headers if h.startswith(f"{DEFAULT_AUTH_COOKIE_NAME}=")),
        None,
    )
    assert auth_cookie is not None, f"未种凭据 Cookie：{set_cookie_headers}"

    lowered = auth_cookie.lower()
    # 这是本阶段替换 sessionStorage 的全部意义所在：JS 不可读。
    assert "httponly" in lowered, auth_cookie
    assert "samesite=" in lowered, auth_cookie
    assert "path=/" in lowered, auth_cookie


def test_csrf_cookie_is_readable_by_js_and_separate_from_credential(rbac_env) -> None:
    """CSRF Cookie 必须**非** HttpOnly（要给 JS 读），且与凭据 Cookie 分离。"""

    resp = rbac_env["login"]("admin@a.local", rbac_env["ids"]["pw"])
    headers = resp.headers.get_list("set-cookie")

    csrf_cookie = next(
        (h for h in headers if h.startswith(f"{DEFAULT_CSRF_COOKIE_NAME}=")), None
    )
    assert csrf_cookie is not None, f"未种 CSRF Cookie：{headers}"
    # 双提交要求 JS 能读到它并回填到请求头，所以这一条**不能**有 HttpOnly。
    assert "httponly" not in csrf_cookie.lower(), csrf_cookie

    # 两条 Cookie 名字不同、值不同：CSRF 令牌不得等于凭据本身。
    body = resp.json()["data"]
    assert body["csrf_token"] != body["access_token"]


def test_production_forces_secure_cookie_even_if_disabled() -> None:
    """生产环境即便显式关掉 Secure，也必须被强制打开（不给自伤的口子）。"""

    s = _prod_settings(COOKIE_SECURE=False)
    assert s.effective_cookie_secure is True

    dev = Settings(APP_ENV="development", COOKIE_SECURE=False)
    # 非生产允许关闭：本地 http://localhost 上带 Secure 的 Cookie 根本发不出去。
    assert dev.effective_cookie_secure is False


def test_production_forces_csrf_even_if_disabled() -> None:
    """同理，生产环境的 CSRF 开关不可被配置关掉。"""

    s = _prod_settings(CSRF_PROTECTION_ENABLED=False)
    assert s.effective_csrf_enabled is True


def test_logout_clears_both_cookies(rbac_env) -> None:
    """登出必须同时清掉凭据与 CSRF Cookie，不留半个会话。"""

    client = rbac_env["client"]
    login = client.post(
        "/api/auth/login",
        json={"email": "admin@a.local", "password": rbac_env["ids"]["pw"]},
    )
    assert login.status_code == 200
    csrf = login.json()["data"]["csrf_token"]

    resp = client.post("/api/auth/logout", headers={DEFAULT_CSRF_HEADER_NAME: csrf})
    assert resp.status_code == 200, resp.text

    cleared = " ".join(resp.headers.get_list("set-cookie"))
    assert DEFAULT_AUTH_COOKIE_NAME in cleared
    assert DEFAULT_CSRF_COOKIE_NAME in cleared
    # 清除后该 client 已无有效会话。
    client.cookies.clear()
    assert client.get("/api/auth/me").status_code == 401


# --------------------------------------------------------------------------- #
# 2. CSRF 双提交                                                                #
# --------------------------------------------------------------------------- #


@pytest.fixture()
def csrf_on(monkeypatch):
    """在测试内打开 CSRF（非生产默认关闭，便于既有联调）。"""

    from app.core.config import get_settings

    monkeypatch.setenv("CSRF_PROTECTION_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_state_changing_request_without_csrf_token_is_rejected(
    rbac_env, csrf_on
) -> None:
    """有合法凭据 Cookie 但没有 CSRF 头 ⇒ 403（这正是 CSRF 攻击的形状）。"""

    client = rbac_env["client"]
    login = client.post(
        "/api/auth/login",
        json={"email": "admin@a.local", "password": rbac_env["ids"]["pw"]},
    )
    assert login.status_code == 200
    # 浏览器会自动带上两个 Cookie，但攻击者站点读不到 CSRF 值、无法设置该头。
    resp = client.post("/api/auth/logout")
    assert resp.status_code == 403, resp.text
    assert "CSRF" in resp.text


def test_mismatched_csrf_token_is_rejected(rbac_env, csrf_on) -> None:
    """CSRF 头与 Cookie 不一致 ⇒ 403（猜值不管用）。"""

    client = rbac_env["client"]
    client.post(
        "/api/auth/login",
        json={"email": "admin@a.local", "password": rbac_env["ids"]["pw"]},
    )
    resp = client.post(
        "/api/auth/logout",
        headers={DEFAULT_CSRF_HEADER_NAME: generate_csrf_token()},
    )
    assert resp.status_code == 403, resp.text


def test_matching_csrf_token_is_accepted(rbac_env, csrf_on) -> None:
    """双提交一致 ⇒ 放行（证明防护不是"一律拒绝"的假安全）。"""

    client = rbac_env["client"]
    login = client.post(
        "/api/auth/login",
        json={"email": "admin@a.local", "password": rbac_env["ids"]["pw"]},
    )
    csrf = login.json()["data"]["csrf_token"]
    resp = client.post("/api/auth/logout", headers={DEFAULT_CSRF_HEADER_NAME: csrf})
    assert resp.status_code == 200, resp.text


def test_safe_methods_are_exempt_from_csrf(rbac_env, csrf_on) -> None:
    """GET 不改状态，不该被强加 CSRF 头（否则只读接口全废）。"""

    client = rbac_env["client"]
    client.post(
        "/api/auth/login",
        json={"email": "admin@a.local", "password": rbac_env["ids"]["pw"]},
    )
    assert client.get("/api/auth/me").status_code == 200


# --------------------------------------------------------------------------- #
# 3. 凭据通道优先级（本阶段修复的真实越权面，必须有回归防护）                    #
# --------------------------------------------------------------------------- #


def test_explicit_bearer_header_wins_over_cookie() -> None:
    """显式头优先于 Cookie。

    反例的危害：浏览器登录过 A，脚本用 B 的 Bearer 头调接口，若 Cookie 压过
    头，系统会以 A 的身份执行并把责任记到 A 头上 —— 跨主体越权 + 审计失真。
    """

    req = _FakeRequest(
        cookies={DEFAULT_AUTH_COOKIE_NAME: "cookie-token-A"},
        headers={"Authorization": "Bearer header-token-B"},
    )
    assert resolve_raw_token(req, "Bearer header-token-B") == "header-token-B"
    assert resolve_bearer_credential(req, "Bearer header-token-B") == (
        "Bearer header-token-B"
    )


def test_cookie_is_used_only_when_header_absent() -> None:
    """没有显式头时，Cookie 兜底生效，并被补回 ``Bearer `` 前缀。"""

    req = _FakeRequest(cookies={DEFAULT_AUTH_COOKIE_NAME: "cookie-token"})
    assert resolve_raw_token(req, None) == "cookie-token"
    # 身份服务只认 "Bearer x"；不补前缀的话 Cookie 通道整条不通。
    assert resolve_bearer_credential(req, None) == "Bearer cookie-token"


def test_explicit_invalid_header_does_not_fall_back_to_cookie() -> None:
    """显式头存在但非法（如 Basic）⇒ 不回落 Cookie，判无凭据。

    静默回落会造成"调用方以为自己是 X、系统记成 Y"的身份替换。
    """

    req = _FakeRequest(
        cookies={DEFAULT_AUTH_COOKIE_NAME: "cookie-token"},
        headers={"Authorization": "Basic dXNlcjpwYXNz"},
    )
    assert resolve_raw_token(req, "Basic dXNlcjpwYXNz") is None
    # 原样透传给身份服务，以便报出精确的"不支持的认证方式"。
    assert resolve_bearer_credential(req, "Basic dXNlcjpwYXNz") == "Basic dXNlcjpwYXNz"


def test_no_credentials_at_all_resolves_to_none() -> None:
    req = _FakeRequest()
    assert resolve_raw_token(req, None) is None
    assert resolve_bearer_credential(req, None) is None


def test_cookie_credential_channel_works_end_to_end(rbac_env) -> None:
    """Cookie 通道必须真的能认证成功（否则 HttpOnly 方案形同虚设）。"""

    client = rbac_env["client"]
    login = client.post(
        "/api/auth/login",
        json={"email": "admin@a.local", "password": rbac_env["ids"]["pw"]},
    )
    assert login.status_code == 200
    # 不带任何 Authorization 头，只靠浏览器自动携带的 HttpOnly Cookie。
    me = client.get("/api/auth/me")
    assert me.status_code == 200, me.text
    assert me.json()["data"]["email"] == "admin@a.local"


# --------------------------------------------------------------------------- #
# 4. OIDC / SSO fail-closed                                                     #
# --------------------------------------------------------------------------- #


def _build_service(settings_overrides: dict):
    """在给定配置下装配身份服务，返回异常或服务实例。"""

    from app.core.config import get_settings
    from app.identity.dependencies import build_identity_service

    get_settings.cache_clear()
    return build_identity_service, settings_overrides


@pytest.mark.parametrize(
    "env_overrides, missing",
    [
        ({"IDENTITY_PROVIDER": "oidc"}, "issuer/audience/jwks"),
        (
            {"IDENTITY_PROVIDER": "oidc", "OIDC_ISSUER": "https://idp.example.com"},
            "audience/jwks",
        ),
        (
            {
                "IDENTITY_PROVIDER": "oidc",
                "OIDC_ISSUER": "https://idp.example.com",
                "OIDC_AUDIENCE": "boip",
            },
            "jwks",
        ),
    ],
)
def test_oidc_without_full_config_fails_closed(
    monkeypatch, env_overrides, missing
) -> None:
    """OIDC 配置不全 ⇒ 装配即抛错，绝不"先跑起来再说"。"""

    from app.core.config import get_settings
    from app.identity.dependencies import build_identity_service
    from app.identity.errors import IdentityConfigError

    for k, v in env_overrides.items():
        monkeypatch.setenv(k, str(v))
    monkeypatch.setenv("JWT_SECRET", "test-secret-for-config-assembly")
    get_settings.cache_clear()

    with pytest.raises(IdentityConfigError) as exc:
        build_identity_service(db=None)
    # 报错必须指明缺什么，否则运维只能靠猜。
    assert "OIDC" in str(exc.value) or "oidc" in str(exc.value)
    get_settings.cache_clear()


def test_sso_gateway_requires_explicit_trust(monkeypatch) -> None:
    """SSO 网关模式必须显式声明信任边界，否则拒绝装配。

    未声明就启用 = 后端可被绕过网关直连，网关注入的身份头就成了任人伪造的入口。
    """

    from app.core.config import get_settings
    from app.identity.dependencies import build_identity_service
    from app.identity.errors import IdentityConfigError

    monkeypatch.setenv("IDENTITY_PROVIDER", "sso-gateway")
    monkeypatch.setenv("SSO_GATEWAY_TRUSTED", "false")
    monkeypatch.setenv("JWT_SECRET", "test-secret-for-config-assembly")
    get_settings.cache_clear()

    with pytest.raises(IdentityConfigError):
        build_identity_service(db=None)
    get_settings.cache_clear()


def test_unknown_identity_provider_is_rejected(monkeypatch) -> None:
    """未知身份提供方 ⇒ 拒绝，而不是悄悄退回默认 jwt。"""

    from app.core.config import get_settings
    from app.identity.dependencies import build_identity_service
    from app.identity.errors import IdentityConfigError

    monkeypatch.setenv("IDENTITY_PROVIDER", "magic-sso")
    monkeypatch.setenv("JWT_SECRET", "test-secret-for-config-assembly")
    get_settings.cache_clear()

    with pytest.raises(IdentityConfigError):
        build_identity_service(db=None)
    get_settings.cache_clear()


def test_oidc_verifier_does_not_fake_signature_verification() -> None:
    """OIDC 验证器在缺少 RS256 后端时必须报错，**不得**放行未验签的 token。

    这是整个身份体系最危险的一处捷径：只要"先解析出 claims 用着"，
    任何人自签一个 JWT 就是管理员。宁可不可用，不可假可用。
    """

    from app.identity.errors import IdentityConfigError, IdentityError
    from app.identity.verifier import HttpJwksResolver, OidcTokenVerifier

    # 随便一个结构合法的 JWT：不能被"解析成功"就当作验签通过。
    fake = "eyJhbGciOiJSUzI1NiIsImtpZCI6ImsxIn0.eyJzdWIiOiJhZG1pbiJ9.c2ln"

    # ① 未配置（无 JWKS 解析器）⇒ 拒绝，而不是"没配就放行"。
    unconfigured = OidcTokenVerifier(issuer="https://idp.example.com", audience="boip")
    assert unconfigured.is_configured() is False
    with pytest.raises(IdentityConfigError):
        unconfigured.verify(fake)

    # ② JWKS 拉取失败（IdP 不可达 / kid 找不到）⇒ 拒绝。
    #    用 stub 而非真实 URL：这里要验的是"解析失败即拒绝"的契约，
    #    打真实 DNS 会让测试依赖网络，在 CI 里变成随机失败。
    class _FailingResolver:
        def resolve_signing_key(self, token: str):
            raise RuntimeError("JWKS endpoint unreachable")

    unreachable = OidcTokenVerifier(
        issuer="https://idp.example.com",
        audience="boip",
        jwks_resolver=_FailingResolver(),
    )
    assert unreachable.is_configured() is True
    with pytest.raises((IdentityConfigError, IdentityError)):
        unreachable.verify(fake)

    # ③ 最危险的路径：JWKS **拿到了**密钥，但 RS256 验签后端未启用。
    #    此时绝不能"既然解析出了 claims 就放行" —— 那等于任何人自签即管理员。
    class _SucceedingResolver:
        def resolve_signing_key(self, token: str):
            return {"kty": "RSA", "kid": "k1", "n": "fake", "e": "AQAB"}

    with_key = OidcTokenVerifier(
        issuer="https://idp.example.com",
        audience="boip",
        jwks_resolver=_SucceedingResolver(),
    )
    with pytest.raises((IdentityConfigError, IdentityError)):
        with_key.verify(fake)

    # ④ HttpJwksResolver 存在且是真实 HTTP 实现（不是占位桩）。
    assert hasattr(HttpJwksResolver, "resolve_signing_key")


# --------------------------------------------------------------------------- #
# 5. 环境隔离与生产启动红线                                                     #
# --------------------------------------------------------------------------- #


def test_production_rejects_known_test_secret() -> None:
    """生产用测试密钥 ⇒ 拒绝启动。"""

    for secret in sorted(KNOWN_TEST_SECRETS):
        s = _prod_settings(JWT_SECRET=secret)
        with pytest.raises(RuntimeError) as exc:
            s.assert_production_safe()
        assert "JWT_SECRET" in str(exc.value)


def test_production_rejects_static_dev_identity_provider() -> None:
    """生产用 static-dev 身份提供方 ⇒ 拒绝启动。"""

    for provider in sorted(PRODUCTION_FORBIDDEN_IDENTITY_PROVIDERS):
        s = _prod_settings(IDENTITY_PROVIDER=provider)
        with pytest.raises(RuntimeError) as exc:
            s.assert_production_safe()
        assert provider in str(exc.value)


def test_production_rejects_static_dev_flag() -> None:
    s = _prod_settings(STATIC_DEV_IDENTITY_ENABLED=True)
    with pytest.raises(RuntimeError) as exc:
        s.assert_production_safe()
    assert "STATIC_DEV_IDENTITY_ENABLED" in str(exc.value)


def test_production_requires_cors_decision() -> None:
    """生产必须就 CORS **表态**：给白名单，或明写 none。空着不算表态。"""

    with pytest.raises(RuntimeError) as exc:
        _prod_settings(CORS_ORIGINS="").assert_production_safe()
    assert "CORS_ORIGINS" in str(exc.value)

    # 同源部署的正当出口：明确声明不需要跨域。
    same_origin = _prod_settings(CORS_ORIGINS="none")
    same_origin.assert_production_safe()
    assert same_origin.parsed_cors_origins == ()
    assert same_origin.cors_explicitly_disabled is True


def test_production_rejects_wildcard_cors() -> None:
    """通配来源 + 凭据 Cookie = 任意站点可携带用户凭据，生产严禁。"""

    with pytest.raises(RuntimeError) as exc:
        _prod_settings(CORS_ORIGINS="*").assert_production_safe()
    assert "*" in str(exc.value)


def test_production_safe_config_passes() -> None:
    """一份合规的生产配置必须能通过 —— 否则红线就是"永远启动不了"。"""

    _prod_settings().assert_production_safe()


def test_non_production_never_blocks_startup() -> None:
    """开发/测试环境不做生产红线校验，否则本地根本跑不起来。"""

    for env in ("development", "testing"):
        s = Settings(APP_ENV=env, JWT_SECRET="test", CORS_ORIGINS="")
        s.assert_production_safe()  # no-op，不抛


def test_environment_flags_are_mutually_exclusive() -> None:
    prod = Settings(APP_ENV="production")
    test = Settings(APP_ENV="testing")
    dev = Settings(APP_ENV="development")

    assert (prod.is_production, prod.is_testing, prod.is_development) == (
        True,
        False,
        False,
    )
    assert (test.is_production, test.is_testing, test.is_development) == (
        False,
        True,
        False,
    )
    assert (dev.is_production, dev.is_testing, dev.is_development) == (
        False,
        False,
        True,
    )


# --------------------------------------------------------------------------- #
# 6. 安全审计（append-only）                                                    #
# --------------------------------------------------------------------------- #


def test_audit_rejects_action_outside_whitelist() -> None:
    """写入未授权动作 ⇒ 直接拒绝。审计范围由白名单锁死。"""

    async def _run():
        await record_security_event(
            None,  # 到不了用 db 的那一步
            action="grant_himself_admin",
            tenant_id=None,
            actor_id=None,
        )

    import asyncio

    with pytest.raises(SecurityAuditError) as exc:
        asyncio.run(_run())
    assert "grant_himself_admin" in str(exc.value)


def test_audit_action_whitelist_matches_required_events() -> None:
    """T4 要求的五类事件必须都在白名单内，一个都不能少。"""

    required = {
        "login",
        "logout",
        "token_refresh",
        "permission_denied",
        "identity_failure",
    }
    assert required <= SECURITY_AUDIT_ACTIONS


def test_audit_module_exposes_no_mutation_path() -> None:
    """审计模块**只提供写入** —— 没有任何 update/delete 出口。

    append-only 若只靠"大家别改"的约定，等于没有。这里从模块导出面上确认：
    对外可用的动词只有"记录"。
    """

    import app.core.security_audit as audit_mod

    exported = set(audit_mod.__all__)
    forbidden_verbs = {"update", "delete", "modify", "purge", "erase", "rewrite"}
    for name in exported:
        assert not any(v in name.lower() for v in forbidden_verbs), name


def test_unknown_tenant_events_use_system_tenant() -> None:
    """身份失败时往往不知道租户，用全零系统租户标记而不是编一个。"""

    assert SECURITY_AUDIT_SYSTEM_TENANT == uuid.UUID(int=0)


def test_permission_denied_is_audited(governance_env) -> None:
    """治理权限被拒 ⇒ 必须留痕（谁、要什么权限、被拒了）。"""

    env = governance_env
    before = _count_audit(env, "permission_denied")

    r = env["client"].get(
        "/governance/audit", headers=env["bearer"](env["business_only_token"])
    )
    assert r.status_code == 403, r.text

    after = _count_audit(env, "permission_denied")
    assert after > before, "权限拒绝未产生审计记录"


def test_identity_failure_is_audited(governance_env) -> None:
    """身份校验失败 ⇒ 必须留痕（坏 token 的探测行为要看得见）。"""

    env = governance_env
    before = _count_audit(env, "identity_failure")

    r = env["client"].get(
        "/governance/audit", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert r.status_code == 401, r.text

    after = _count_audit(env, "identity_failure")
    assert after > before, "身份失败未产生审计记录"


def test_login_is_audited(rbac_env) -> None:
    """登录成功 ⇒ 留痕。"""

    resp = rbac_env["login"]("admin@a.local", rbac_env["ids"]["pw"])
    assert resp.status_code == 200
    assert _count_audit_rbac(rbac_env, "login") > 0


def _count_audit(env, action: str) -> int:
    """统计治理测试库里某类安全审计的条数。"""

    from sqlalchemy import func, select

    from app.db.models.audit import AuditLog

    session_factory = env.get("sync_session_factory")
    if session_factory is None:
        return _count_via_client(env, action)
    with session_factory() as s:
        return s.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == action)
        )


def _count_via_client(env, action: str) -> int:
    """没有暴露 session 工厂时，退回用 app 的 db 依赖直接查。"""

    import asyncio

    from sqlalchemy import func, select

    from app.db.models.audit import AuditLog
    from app.db.session import async_get_db
    from app.main import app

    override = app.dependency_overrides.get(async_get_db)
    assert override is not None, "测试环境应已覆盖 async_get_db"

    async def _run() -> int:
        agen = override()
        session = await agen.__anext__()
        try:
            return await session.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == action)
            )
        finally:
            await agen.aclose()

    return asyncio.run(_run())


def _count_audit_rbac(env, action: str) -> int:
    return _count_via_client(env, action)


# --------------------------------------------------------------------------- #
# 7. CI 生产门禁扫描器自身的有效性（T5）                                          #
# --------------------------------------------------------------------------- #
#
# 一个抓不到违规的扫描器，比没有扫描器更危险 —— 它会让所有人以为这条路已经被
# 堵死。所以每条规则都要用"合成的违规样本"证明它真的会失败，同时用"干净样本"
# 证明它不会误报（误报会逼着后来人给红线加豁免，那才是真正的溃堤起点）。


def _load_scanner():
    """从仓库根加载 ``scripts/lint/check_production_security.py``。

    它是 CLI 脚本而非包内模块，用文件路径动态载入，避免为了测试去改项目布局。
    """

    import importlib.util
    import sys
    from pathlib import Path

    name = "boip_prod_security_lint"
    cached = sys.modules.get(name)
    if cached is not None:
        return cached

    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "lint" / "check_production_security.py"
    assert script.exists(), f"生产安全扫描器缺失：{script}"
    spec = importlib.util.spec_from_file_location(name, script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # 必须先登记再 exec：模块里的 @dataclass 会回查 sys.modules[cls.__module__]
    # 解析注解，未登记时抛 AttributeError('NoneType' has no '__dict__')。
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


def _write(root, rel: str, content: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_scanner_catches_cookie_written_outside_single_exit(tmp_path) -> None:
    """路由自己 set_cookie ⇒ 必须被抓。属性漏一个，HttpOnly 方案就归零。"""

    scanner = _load_scanner()
    _write(
        tmp_path,
        "backend/app/api/rogue.py",
        "def handler(response):\n    response.set_cookie('boip_access_token', 'x')\n",
    )
    found = scanner.rule_cookie_single_exit(tmp_path)
    assert len(found) == 1
    assert found[0].rel_path == "backend/app/api/rogue.py"


def test_scanner_allows_cookie_in_blessed_module(tmp_path) -> None:
    """统一出口自己当然要 set_cookie —— 不能把唯一合法实现也判违规。"""

    scanner = _load_scanner()
    _write(
        tmp_path,
        "backend/app/core/auth_cookies.py",
        "def set_auth_cookie(response):\n    response.set_cookie(key='k', value='v')\n",
    )
    assert scanner.rule_cookie_single_exit(tmp_path) == []


def test_scanner_catches_credential_written_to_web_storage(tmp_path) -> None:
    """页面把 token 塞进 sessionStorage ⇒ 必须被抓（3.8.28 的原始缺陷）。"""

    scanner = _load_scanner()
    _write(
        tmp_path,
        "frontend/src/app/login/page.tsx",
        'const t = "x";\nwindow.sessionStorage.setItem("access_token", t);\n',
    )
    found = scanner.rule_no_js_credential_storage(tmp_path)
    assert len(found) == 1


def test_scanner_catches_token_store_call_in_page_layer(tmp_path) -> None:
    """页面重新调用 writeGovernanceToken ⇒ 视为回退到 JS 保管凭据。"""

    scanner = _load_scanner()
    _write(
        tmp_path,
        "frontend/src/app/login/page.tsx",
        "writeGovernanceToken(token);\n",
    )
    found = scanner.rule_no_js_credential_storage(tmp_path)
    assert len(found) == 1
    assert "HttpOnly" in found[0].hint


def test_scanner_ignores_storage_mentions_in_comments(tmp_path) -> None:
    """注释里解释"为什么不再用 sessionStorage"不构成违规，否则没人敢写文档。"""

    scanner = _load_scanner()
    _write(
        tmp_path,
        "frontend/src/app/login/page.tsx",
        " * 旧版把 access_token 写进 sessionStorage，本阶段已废止。\n",
    )
    assert scanner.rule_no_js_credential_storage(tmp_path) == []


def test_scanner_catches_cors_wildcard(tmp_path) -> None:
    """``allow_origins=["*"]`` + 凭据 Cookie = 任意站点可代用户发请求。"""

    scanner = _load_scanner()
    _write(
        tmp_path,
        "backend/app/middleware/cors.py",
        'app.add_middleware(CORSMiddleware, allow_origins=["*"])\n',
    )
    assert len(scanner.rule_no_cors_wildcard(tmp_path)) == 1


def test_scanner_catches_disabled_tls_and_fake_signature_verification(
    tmp_path,
) -> None:
    """关闭证书校验 / 关闭验签 ⇒ 后续所有权限判定都建立在可伪造凭据上。"""

    scanner = _load_scanner()
    _write(
        tmp_path,
        "backend/app/identity/rogue_verifier.py",
        "r = httpx.get(url, verify=False)\n"
        'claims = jwt.decode(t, key, options={"verify_signature": False})\n',
    )
    found = scanner.rule_no_insecure_tls(tmp_path)
    assert len(found) == 2


def test_scanner_allows_insecure_patterns_inside_tests(tmp_path) -> None:
    """测试里构造"关掉验签会怎样"是正当的；扫描只约束生产源码。"""

    scanner = _load_scanner()
    _write(
        tmp_path,
        "backend/app/identity/tests/test_rogue.py",
        "r = httpx.get(url, verify=False)\n",
    )
    assert scanner.rule_no_insecure_tls(tmp_path) == []


def test_scanner_catches_test_secret_leaking_into_source(tmp_path) -> None:
    """把已知测试密钥当默认值写进生产源码 ⇒ 必须被抓。"""

    scanner = _load_scanner()
    _write(
        tmp_path,
        "backend/app/core/tokens.py",
        'SECRET = "test-jwt-secret-not-for-production"\n',
    )
    assert len(scanner.rule_no_test_secret_in_source(tmp_path)) == 1


def test_scanner_allows_test_secret_in_blacklist_definition(tmp_path) -> None:
    """黑名单定义处必须写出这个字面量，否则无从拒绝它。"""

    scanner = _load_scanner()
    _write(
        tmp_path,
        "backend/app/core/config.py",
        'KNOWN_TEST_SECRETS = {"test-jwt-secret-not-for-production"}\n',
    )
    assert scanner.rule_no_test_secret_in_source(tmp_path) == []


def test_scanner_catches_engineering_flag_flipped_true(tmp_path) -> None:
    """最高红线①：任何把 engineering_enabled 置真的提交都必须在 CI 被拦下。"""

    scanner = _load_scanner()
    _write(tmp_path, "agents/config.yaml", "engineering:\n  engineering_enabled: true\n")
    found = scanner.rule_engineering_flag_disabled(tmp_path)
    assert len(found) == 1
    assert "最高红线" in found[0].hint


def test_scanner_accepts_engineering_flag_false(tmp_path) -> None:
    """现状（false）必须判通过，否则红线扫描会把主干永久卡死。"""

    scanner = _load_scanner()
    _write(
        tmp_path, "agents/config.yaml", "engineering:\n  engineering_enabled: false\n"
    )
    assert scanner.rule_engineering_flag_disabled(tmp_path) == []


def test_scanner_catches_static_dev_as_default_identity_provider(tmp_path) -> None:
    """static-dev 作缺省 = "忘了配就自动有身份"，是身份链路最危险的默认值。"""

    scanner = _load_scanner()
    _write(
        tmp_path,
        "backend/app/core/config.py",
        '    identity_provider: str = Field(default="static-dev", '
        'validation_alias="IDENTITY_PROVIDER")\n',
    )
    assert len(scanner.rule_no_static_dev_default(tmp_path)) == 1


def test_scanner_passes_on_current_repository() -> None:
    """当前仓库必须通过全部规则 —— 这就是"合并门禁"本身。"""

    from pathlib import Path

    scanner = _load_scanner()
    repo_root = Path(__file__).resolve().parents[2]
    assert scanner.main(["--root", str(repo_root)]) == 0
