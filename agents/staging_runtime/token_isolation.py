"""Phase 3.9.9 Real Staging Runtime Integration & Validation Layer —— Staging Token Isolation（Task 16）。

``StagingTokenIsolation`` 保证 staging 令牌与 production 令牌**隔离**：staging 令牌
不得等于任何 production 令牌引用（红线：禁止复用 Production 资源 / 改真实权限授予）。

fail-closed：命中 production 令牌引用即拒绝；不签发、不授予、不验证生产令牌。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from agents.staging_runtime.environment import EnvironmentIdentity
from agents.staging_runtime.isolation_guard import EnvironmentIsolationGuard


class StagingTokenIsolationError(Exception):
    """Staging 令牌隔离违例（fail-closed）。"""


@dataclass(frozen=True)
class TokenIsolationVerdict:
    """令牌隔离结论（结构化）。"""

    token_name: str
    isolated: bool
    conflicts_production: bool
    reason: str


class StagingTokenIsolation:
    """Staging 令牌隔离校验（staging 令牌 ≠ production 令牌）。"""

    def __init__(
        self,
        identity: EnvironmentIdentity,
        *,
        production_token_refs: Iterable[str] = (),
    ) -> None:
        guard = EnvironmentIsolationGuard()
        guard.assert_staging_integration_permitted(identity)
        self._identity = identity
        self._production_token_refs = frozenset(production_token_refs)

    def check_token(self, name: str, value: str | None) -> TokenIsolationVerdict:
        """校验某 staging 令牌不与 production 令牌引用冲突。"""

        if value is not None and value in self._production_token_refs:
            return TokenIsolationVerdict(
                token_name=name,
                isolated=False,
                conflicts_production=True,
                reason="staging 令牌命中 Production 令牌引用集合，拒绝复用。",
            )
        return TokenIsolationVerdict(
            token_name=name,
            isolated=True,
            conflicts_production=False,
            reason="staging 令牌未命中 production 引用，隔离成立。",
        )

    def assert_isolated(self, name: str, value: str | None) -> None:
        verdict = self.check_token(name, value)
        if not verdict.isolated:
            raise StagingTokenIsolationError(
                f"令牌 {name!r} 与 Production 令牌冲突：{verdict.reason}"
            )

    def audit(self, tokens: Mapping[str, str | None]) -> tuple[TokenIsolationVerdict, ...]:
        """批量校验一组 staging 令牌的隔离性。"""

        return tuple(self.check_token(n, v) for n, v in tokens.items())


__all__ = [
    "StagingTokenIsolationError",
    "TokenIsolationVerdict",
    "StagingTokenIsolation",
]
