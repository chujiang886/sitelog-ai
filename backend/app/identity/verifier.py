"""令牌验证适配层（Phase 3.8.28 T1）。

职责边界非常窄：**把一串凭据变成一组"经过密码学校验的声明"**，仅此而已。
它不查数据库、不解析权限、不判断是不是真人 —— 那些属于 ``resolver`` 与
``principal``。分开的理由是这两件事的失效方式完全不同：

- 验证失败 ⇒ 凭据不可信（攻击信号 / 过期）
- 解析失败 ⇒ 凭据可信但主体状态变了（离职 / 停用 / 角色被收回）

混在一起会导致运维在日志里分不清"有人在打我"和"有人该重新登录了"。

## 三个适配器的成熟度

- ``JwtTokenVerifier``  —— **本阶段启用**。复用 Phase 2.2 的 HS256 实现
  （标准库，secret 只来自环境变量，缺失即 fail-closed）。
- ``OidcTokenVerifier`` —— 骨架。RS256/JWKS 需要外部身份提供商与公钥轮换
  机制，属于"缺少必须外部资源"，本阶段不猜测其配置。未配置时**抛错而非
  降级**，避免有人以为接上了 OIDC 其实走的是别的路径。
- ``SsoGatewayVerifier`` —— 骨架。要求部署方**显式声明**网关已完成校验且
  后端不可从网关外直达，这个前提无法由代码自证，只能要求人来确认。
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Mapping

from app.identity.errors import (
    IdentityConfigError,
    IdentityTokenExpiredError,
    IdentityTokenInvalidError,
    IdentityUnauthenticatedError,
)


@dataclass(frozen=True, slots=True)
class VerifiedClaims:
    """密码学校验通过后的原始声明。

    注意 ``actor_kind_claim`` 是**声明**而非结论：它记录凭据自称的主体类别，
    真正的类别由 resolver 结合权威数据源裁定。命名上刻意带 ``_claim`` 后缀，
    就是为了让任何直接采信它的代码在 review 时显得刺眼。
    """

    subject: str
    org_id: str
    email: str = ""
    display_name: str = ""
    roles: tuple[str, ...] = ()
    actor_kind_claim: str = ""
    issued_at: int = 0
    expires_at: int = 0
    scheme: str = "jwt"
    raw: Mapping[str, Any] = field(default_factory=dict)


class TokenVerifier(ABC):
    """凭据验证器端口。"""

    #: 适配器标识，进入审计的 ``authenticated_via``。
    scheme: str = "unknown"

    @abstractmethod
    def verify(self, token: str) -> VerifiedClaims:
        """校验凭据并返回声明；任何不可信情形抛 ``IdentityError`` 子类。"""

    @abstractmethod
    def is_configured(self) -> bool:
        """基础设施是否就绪（缺配置时上层必须整体拒绝，而非放行）。"""


# --------------------------------------------------------------------------- #
# JWT（HS256）—— 本阶段启用                                                     #
# --------------------------------------------------------------------------- #


class JwtTokenVerifier(TokenVerifier):
    """HS256 JWT 验证器，复用 Phase 2.2 的标准库实现。

    复用而非重写的理由：``app.core.security.decode_access_token`` 已经做了
    签名比对（``hmac.compare_digest``，常量时间）、过期校验、token 类型校验，
    并且 secret 缺失时抛 ``AuthConfigError``。再写一份只会制造两处可能不一致
    的密码学代码 —— 这类重复是安全缺陷的经典来源。
    """

    scheme = "jwt"

    def __init__(self, *, org_claim: str = "tenant_id") -> None:
        self._org_claim = org_claim

    def is_configured(self) -> bool:
        from app.core.config import get_settings

        return bool(get_settings().jwt_secret)

    def verify(self, token: str) -> VerifiedClaims:
        from app.core.security import (
            AuthConfigError,
            AuthError,
            decode_access_token,
        )

        if not token or not str(token).strip():
            raise IdentityUnauthenticatedError("凭据为空。")

        try:
            payload = decode_access_token(token)
        except AuthConfigError as exc:
            # 基础设施没配好：绝不因此放行，也不降级为匿名。
            raise IdentityConfigError(str(exc)) from exc
        except AuthError as exc:
            message = str(exc)
            if "expired" in message.lower():
                raise IdentityTokenExpiredError(message) from exc
            raise IdentityTokenInvalidError(message) from exc

        subject = str(payload.get("sub") or "").strip()
        if not subject:
            raise IdentityTokenInvalidError("凭据缺少 sub 声明。")

        org_id = str(payload.get(self._org_claim) or "").strip()
        if not org_id:
            raise IdentityTokenInvalidError(
                f"凭据缺少组织声明 {self._org_claim!r}：无法判定组织边界。"
            )

        roles_raw = payload.get("roles") or []
        if not isinstance(roles_raw, (list, tuple)):
            raise IdentityTokenInvalidError("凭据 roles 声明格式非法。")

        return VerifiedClaims(
            subject=subject,
            org_id=org_id,
            email=str(payload.get("email") or ""),
            display_name=str(payload.get("name") or ""),
            roles=tuple(str(r) for r in roles_raw),
            # Phase 2.2 的 token 不带 actor_kind；缺失时留空，
            # 由 resolver 依据数据库中是否存在真实用户来裁定。
            actor_kind_claim=str(payload.get("actor_kind") or ""),
            issued_at=int(payload.get("iat") or 0),
            expires_at=int(payload.get("exp") or 0),
            scheme=self.scheme,
            raw=payload,
        )


# --------------------------------------------------------------------------- #
# OIDC —— 骨架（需外部 IdP，本阶段不启用）                                       #
# --------------------------------------------------------------------------- #


class OidcTokenVerifier(TokenVerifier):
    """OpenID Connect（RS256 + JWKS）验证器。

    **接口已标准化、生产就绪，但签名验签后端在本阶段保持 fail-closed**：
    未接入真实身份提供商（issuer / audience / JWKS）时 ``verify`` 直接抛
    ``IdentityConfigError``，绝不降级、绝不假装验过。

    一旦三方信息齐备，``_jwks_resolver`` 会真实拉取 IdP 的 JWKS（见
    ``HttpJwksResolver``）；签名验签本身需要 ``cryptography`` 后端，缺失时
    同样 fail-closed 并明确告知——这不是"先放行后补验"的临时版，而是一个
    明确报错的真实装配点。
    """

    scheme = "oidc"

    def __init__(
        self,
        *,
        issuer: str = "",
        audience: str = "",
        jwks_resolver: Any = None,
        org_claim: str = "org_id",
    ) -> None:
        self._issuer = issuer
        self._audience = audience
        self._jwks_resolver = jwks_resolver
        self._org_claim = org_claim

    def is_configured(self) -> bool:
        return bool(self._issuer and self._audience and self._jwks_resolver)

    def verify(self, token: str) -> VerifiedClaims:
        if not self.is_configured():
            raise IdentityConfigError(
                "OIDC 验证器未配置（需 issuer / audience / JWKS 解析器）。"
                "缺少真实身份提供商时，系统整体拒绝，而非降级放行。"
            )
        # 配置齐全：真实拉取 JWKS 并定位签名密钥；签名验签后端（cryptography）
        # 缺失时仍 fail-closed，绝不以"已解析"冒充"已验签"。
        try:
            self._jwks_resolver.resolve_signing_key(token)
        except IdentityConfigError:
            raise
        except Exception as exc:  # noqa: BLE001 - 任何解析异常都归为配置/验签失败
            raise IdentityConfigError(
                f"OIDC JWKS 解析失败：{exc}。未接入可验证的 IdP 前，拒绝放行。"
            ) from exc
        raise IdentityConfigError(
            "OIDC JWKS 已解析，但 RS256 签名验签后端（cryptography）在本阶段未启用；"
            "启用真实 IdP 前，系统保持 fail-closed，不假装验签。"
        )


class JwksResolver:
    """JWKS 解析端口：把 token 映射到 IdP 提供的签名公钥。"""

    def resolve_signing_key(self, token: str) -> Any:
        """返回与 token 头 ``kid`` 对应的公钥材料；找不到即抛 ``IdentityConfigError``。"""

        raise NotImplementedError


class HttpJwksResolver(JwksResolver):
    """通过 HTTP(S) 真实拉取 IdP 的 JWKS（生产就绪接口，无假数据）。

    仅做"拉取 + 按 kid 定位"，不做签名验签——后者交给 RS256 后端。
    拉取失败或 kid 缺失一律抛 ``IdentityConfigError``，确保"没验过就不放行"。
    """

    def __init__(self, jwks_url: str, *, client: Any = None) -> None:
        self._jwks_url = jwks_url
        self._client = client

    def _fetch(self) -> dict:
        if self._client is not None:
            resp = self._client.get(self._jwks_url, timeout=5.0)
            if getattr(resp, "status_code", 200) >= 400:
                raise IdentityConfigError(
                    f"JWKS 端点返回 {getattr(resp, 'status_code', '?')}。"
                )
            return resp.json()
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover - httpx 为后端依赖
            raise IdentityConfigError("缺少 httpx，无法拉取 JWKS。") from exc
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(self._jwks_url)
            if resp.status_code >= 400:
                raise IdentityConfigError(
                    f"JWKS 端点返回 {resp.status_code}。"
                )
            return resp.json()

    def resolve_signing_key(self, token: str) -> Any:
        import base64
        import json

        try:
            header_b64 = token.split(".")[0]
        except (ValueError, AttributeError) as exc:
            raise IdentityConfigError("OIDC token 格式非法。") from exc
        try:
            header = json.loads(
                base64.urlsafe_b64decode(header_b64 + "==")
            )
        except Exception as exc:  # noqa: BLE001
            raise IdentityConfigError("OIDC token 头无法解析。") from exc
        kid = header.get("kid")
        if not kid:
            raise IdentityConfigError("OIDC token 头缺少 kid。")

        jwks = self._fetch()
        keys = jwks.get("keys") or []
        for key in keys:
            if key.get("kid") == kid:
                return key  # 找到签名密钥材料（交由 RS256 后端验签）
        raise IdentityConfigError(f"JWKS 中找不到 kid={kid!r} 的密钥。")


# --------------------------------------------------------------------------- #
# SSO 网关 —— 骨架（需部署侧确认，本阶段不启用）                                 #
# --------------------------------------------------------------------------- #


class SsoGatewayVerifier(TokenVerifier):
    """可信网关注入身份的验证器骨架。

    该模式的安全性**不来自本进程**，而来自"后端只能经网关访问"这一部署事实。
    代码无法自证这件事，因此要求构造时显式传入 ``gateway_verified=True``：
    把一个隐含前提抬成一次有意识的确认，让它出现在 code review 与配置审计里。
    """

    scheme = "sso-gateway"

    def __init__(
        self,
        *,
        gateway_verified: bool = False,
        claims_reader: Any = None,
    ) -> None:
        self._gateway_verified = bool(gateway_verified)
        self._claims_reader = claims_reader

    def is_configured(self) -> bool:
        return self._gateway_verified and self._claims_reader is not None

    def verify(self, token: str) -> VerifiedClaims:
        if not self._gateway_verified:
            raise IdentityConfigError(
                "SSO 网关验证器未获部署确认：必须显式声明 gateway_verified=True，"
                "并保证后端不可从网关之外直达，否则任何人都能伪造网关头。"
            )
        if self._claims_reader is None:
            raise IdentityConfigError("SSO 网关验证器缺少 claims_reader。")
        raise IdentityConfigError(
            "SSO 网关验证器为 Phase 3.8.28 预留骨架，尚未实装。"
        )


def now_ts() -> int:
    """当前 Unix 秒（便于测试注入）。"""

    return int(time.time())


__all__ = [
    "JwtTokenVerifier",
    "OidcTokenVerifier",
    "SsoGatewayVerifier",
    "TokenVerifier",
    "VerifiedClaims",
    "now_ts",
]
