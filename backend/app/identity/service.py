"""身份认证服务（Phase 3.8.28 T1）—— 认证链路的唯一编排点。

```
Authorization: Bearer <token>
        │
        ├─ 1. 拆解 scheme，选择验证器            （本模块）
        ├─ 2. 密码学校验 → VerifiedClaims        （verifier）
        ├─ 3. 回权威源确认主体仍有效 → Principal （resolver）
        └─ 4. 权限判定                            （dependencies）
```

把这四步收在一条链上、且只有这一条链，是为了让"治理身份从哪来"这个问题
在代码库里**只有一个答案**。Phase 3.8.27 收敛双实现时得到的教训是：只要
存在第二条路径，迟早会有调用方走上那条更宽松的。
"""

from __future__ import annotations

from typing import Mapping

from app.identity.errors import (
    IdentityConfigError,
    IdentityUnauthenticatedError,
)
from app.identity.principal import GovernancePrincipal
from app.identity.resolver import PrincipalResolver
from app.identity.verifier import TokenVerifier, VerifiedClaims

#: 支持的 Authorization scheme（小写比较）。
_BEARER = "bearer"


class IdentityAuthenticationService:
    """认证编排：凭据 → 治理主体。"""

    def __init__(
        self,
        *,
        verifiers: Mapping[str, TokenVerifier],
        resolver: PrincipalResolver,
        default_scheme: str = "jwt",
    ) -> None:
        if not verifiers:
            raise IdentityConfigError(
                "身份认证服务至少需要一个验证器；空配置意味着无人可被认证，"
                "而不是所有人都可通过。"
            )
        if default_scheme not in verifiers:
            raise IdentityConfigError(
                f"默认认证方式 {default_scheme!r} 不在已注册验证器 "
                f"{sorted(verifiers)} 中。"
            )
        self._verifiers = dict(verifiers)
        self._resolver = resolver
        self._default_scheme = default_scheme

    # ------------------------------------------------------------------ #
    # 查询                                                                #
    # ------------------------------------------------------------------ #

    @property
    def schemes(self) -> tuple[str, ...]:
        return tuple(sorted(self._verifiers))

    @property
    def default_scheme(self) -> str:
        return self._default_scheme

    def verifier_for(self, scheme: str) -> TokenVerifier:
        try:
            return self._verifiers[scheme]
        except KeyError as exc:
            raise IdentityConfigError(
                f"未注册的认证方式 {scheme!r}；已注册：{self.schemes}"
            ) from exc

    # ------------------------------------------------------------------ #
    # 认证                                                                #
    # ------------------------------------------------------------------ #

    @staticmethod
    def extract_bearer_token(authorization: str | None) -> str:
        """从 Authorization 头取出 bearer token。

        不接受 ``?token=`` 查询参数形式：查询串会进 access log、浏览器历史与
        Referer，治理凭据落到这些地方等同泄露。
        """

        if not authorization or not str(authorization).strip():
            raise IdentityUnauthenticatedError(
                "缺少 Authorization 请求头：治理接口不接受匿名访问。"
            )
        scheme, _, token = str(authorization).partition(" ")
        if scheme.strip().lower() != _BEARER:
            raise IdentityUnauthenticatedError(
                f"不支持的认证方式 {scheme!r}，治理接口只接受 Bearer。"
            )
        token = token.strip()
        if not token:
            raise IdentityUnauthenticatedError("Bearer 凭据为空。")
        return token

    def verify_token(
        self, token: str, *, scheme: str | None = None
    ) -> VerifiedClaims:
        """只做密码学校验（不查权威源），便于单测与诊断。"""

        verifier = self.verifier_for(scheme or self._default_scheme)
        if not verifier.is_configured():
            raise IdentityConfigError(
                f"认证方式 {verifier.scheme!r} 未完成配置，拒绝一切请求。"
                "身份基础设施缺失时，安全的行为是整体不可用，而不是放行。"
            )
        return verifier.verify(token)

    async def authenticate(
        self, authorization: str | None, *, scheme: str | None = None
    ) -> GovernancePrincipal:
        """完整认证链路：取 token → 验签 → 回权威源解析主体。"""

        token = self.extract_bearer_token(authorization)
        claims = self.verify_token(token, scheme=scheme)
        return await self._resolver.resolve(claims)


__all__ = ["IdentityAuthenticationService"]
