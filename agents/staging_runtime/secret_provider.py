"""Phase 3.9.9 Real Staging Runtime Integration & Validation Layer —— Staging Secret Provider（Task 5）。

``StagingSecretProvider`` 负责读取 Local Staging 所需的**非生产** Secret：

- 仅从环境变量解析（``STAGING_SECRET_<NAME>``），绝不内联真实密钥；
- 构造时经 ``EnvironmentIsolationGuard`` 校验 staging 身份（非 staging 拒绝）；
- 若某 secret 落入已知 Production Secret 引用集合，抛
  ``StagingSecretIsolationError``（红线：禁止复用 Production Secret）；
- 本类**没有任何写入/落盘方法**，不写真实 Secret，不修改配置。

缺真实外部 Staging Secret 时，解析返回 ``None``（即 pending），上层据此标记
``PENDING_EXTERNAL_STAGING_RESOURCE``，不阻塞工程。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable, Mapping

from agents.staging_runtime.environment import EnvironmentIdentity
from agents.staging_runtime.isolation_guard import EnvironmentIsolationGuard


class StagingSecretIsolationError(Exception):
    """Staging Secret 隔离违例：拒绝读取/复用 Production Secret。"""


@dataclass(frozen=True)
class StagingSecretResolution:
    """单条 Secret 解析结果（不含明文值泄露到日志的设计意图）。"""

    name: str
    env_var: str
    resolved: bool  # True=已从环境变量取得；False=未配置（pending）


class StagingSecretProvider:
    """读取 Local Staging 非生产 Secret（从环境变量，绝不内联真实值）。"""

    def __init__(
        self,
        identity: EnvironmentIdentity,
        *,
        production_secret_refs: Iterable[str] = (),
        env: Mapping[str, str] | None = None,
    ) -> None:
        # 红线前置：staging 身份必须经护栏校验（含 engineering_enabled 断言）。
        guard = EnvironmentIsolationGuard()
        guard.assert_staging_integration_permitted(identity)

        self._identity = identity
        self._production_secret_refs = frozenset(production_secret_refs)
        self._env = dict(env) if env is not None else dict(os.environ)

    @staticmethod
    def _default_env_var(name: str) -> str:
        """逻辑名 → 环境变量名（大写 + STAGING_SECRET_ 前缀）。"""

        return f"STAGING_SECRET_{name.upper()}"

    def resolve(self, name: str, *, env_var: str | None = None) -> str | None:
        """解析一条 Staging Secret（从环境变量）。未配置返回 ``None``（pending）。

        fail-closed：若解析值落入已知 Production Secret 引用集合，抛
        ``StagingSecretIsolationError``（红线：禁止复用 Production Secret）。
        """

        var = env_var or self._default_env_var(name)
        value = self._env.get(var)
        if value is not None and value in self._production_secret_refs:
            raise StagingSecretIsolationError(
                f"Staging Secret {name!r} 解析值命中 Production Secret 引用集合，"
                "拒绝复用（红线：禁止复用 Production Secret）。"
            )
        return value

    def resolve_required(self, name: str, *, env_var: str | None = None) -> str:
        """解析一条必需的 Staging Secret；未配置（pending）即抛。"""

        value = self.resolve(name, env_var=env_var)
        if value is None:
            raise StagingSecretIsolationError(
                f"Staging Secret {name!r} 未配置（环境变量 "
                f"{env_var or self._default_env_var(name)} 缺失）。"
            )
        return value

    def snapshot(self, names: Iterable[str]) -> tuple[StagingSecretResolution, ...]:
        """对一组逻辑名做解析快照（仅记录是否 resolved，不收集明文值）。"""

        return tuple(
            StagingSecretResolution(
                name=n,
                env_var=self._default_env_var(n),
                resolved=self.resolve(n) is not None,
            )
            for n in names
        )

    def missing(self, names: Iterable[str]) -> tuple[str, ...]:
        """返回未配置（pending）的 Secret 逻辑名列表。"""

        return tuple(n for n in names if self.resolve(n) is None)

    @classmethod
    def from_identity(
        cls,
        identity: EnvironmentIdentity,
        *,
        production_secret_refs: Iterable[str] = (),
        env: Mapping[str, str] | None = None,
    ) -> "StagingSecretProvider":
        """便捷构造（语义同 ``StagingSecretProvider(...)``）。"""

        return cls(identity, production_secret_refs=production_secret_refs, env=env)


__all__ = [
    "StagingSecretIsolationError",
    "StagingSecretResolution",
    "StagingSecretProvider",
]
