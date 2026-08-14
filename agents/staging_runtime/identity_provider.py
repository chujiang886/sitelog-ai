"""Phase 3.9.9 Real Staging Runtime Integration & Validation Layer —— Staging Identity Provider（Task 15）。

``StagingIdentityProvider`` 描述本地预生产的非生产 IdP（issuer），拒绝复用 Production
IdP（红线：禁止复用 Production identity_provider）。

fail-closed：staging issuer 命中已知 Production issuer 引用即拒绝；绝不连接生产 IdP。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from agents.staging_runtime.environment import EnvironmentIdentity, RuntimeEnvironment
from agents.staging_runtime.isolation_guard import EnvironmentIsolationGuard


class StagingIdentityProviderError(Exception):
    """Staging IdP 接入违例（fail-closed）。"""


@dataclass(frozen=True)
class StagingIdentityDescriptor:
    """Staging IdP 描述（不连接、不执行）。"""

    issuer_present: bool
    is_production: bool = False
    non_production: bool = True
    target: str = "local_staging"

    def to_dict(self) -> dict[str, Any]:
        return {
            "issuer_present": self.issuer_present,
            "is_production": self.is_production,
            "non_production": self.non_production,
            "target": self.target,
        }


class StagingIdentityProvider:
    """本地预生产 IdP 提供方（只描述形态，绝不连接生产 IdP）。"""

    def __init__(
        self,
        identity: EnvironmentIdentity,
        *,
        production_issuer_refs: Iterable[str] = (),
        staging_issuer: str | None = None,
    ) -> None:
        guard = EnvironmentIsolationGuard()
        guard.assert_staging_integration_permitted(identity)
        self._identity = identity
        self._production_issuer_refs = frozenset(production_issuer_refs)
        self._staging_issuer = staging_issuer

    def describe(self) -> StagingIdentityDescriptor:
        issuer = self._staging_issuer
        if issuer is not None and issuer in self._production_issuer_refs:
            raise StagingIdentityProviderError(
                "staging issuer 命中 Production IdP 引用集合，拒绝复用"
                "（红线：禁止复用 Production identity_provider）。"
            )
        present = issuer is not None and issuer != "pending_verification"
        return StagingIdentityDescriptor(issuer_present=present)

    def connect(self) -> StagingIdentityDescriptor:
        """**永不**连接 IdP；调用即抛。"""

        raise StagingIdentityProviderError(
            "StagingIdentityProvider.connect() 被调用：系统禁止自动连接 IdP。"
        )


__all__ = [
    "StagingIdentityProviderError",
    "StagingIdentityDescriptor",
    "StagingIdentityProvider",
]
