"""Phase 3.9.9 Real Staging Runtime Integration & Validation Layer —— 环境模型（Task 1）。

定义运行环境分类（Environment Model）与环境身份（Environment Identity），
作为「代码级证明 Staging != Production」的第一层结构基础。

设计红线（fail-closed，本阶段 22 条最高红线映射）：
- 本文件**不**打开 `engineering_enabled`、**不**输出 `engineering_approved`、
  **不**复用 Production 的 database / secret / identity_provider / storage / alert 资源。
- ``PRODUCTION`` 永远不得被分类/标记为 staging；未知环境默认回落到 ``DEVELOPMENT``
  （guard 随后拒绝其实接真实 staging 集成），绝不默认信任。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

# Production 禁止被 staging 复用的资源种类（对应最高红线：
# 禁止复用 Production DB·Secret·IdP·Storage·Alert）。
PRODUCTION_FORBIDDEN_RESOURCE_KINDS = frozenset(
    {
        "database",
        "secret",
        "identity_provider",
        "storage",
        "alert",
    }
)


class RuntimeEnvironment(str, Enum):
    """运行环境分类。

    五类环境，语义互斥：
    - ``DEVELOPMENT`` / ``TESTING``：纯本地开发/测试，无真实外部 staging 集成。
    - ``LOCAL_STAGING``：本机/容器内预生产（非生产），允许真实 staging 接入。
    - ``EXTERNAL_STAGING``：已验证为非生产的外部预生产环境，允许真实 staging 接入。
    - ``PRODUCTION``：真实生产，**禁止**任何 staging 接入/验证动作。
    """

    DEVELOPMENT = "development"
    TESTING = "testing"
    LOCAL_STAGING = "local_staging"
    EXTERNAL_STAGING = "external_staging"
    PRODUCTION = "production"

    @property
    def is_production(self) -> bool:
        """是否为真实生产环境。"""

        return self is RuntimeEnvironment.PRODUCTION

    @property
    def is_staging(self) -> bool:
        """是否为任意 staging（local / external）。"""

        return self in (RuntimeEnvironment.LOCAL_STAGING, RuntimeEnvironment.EXTERNAL_STAGING)

    @property
    def is_external(self) -> bool:
        """是否为外部（非本机）环境。"""

        return self is RuntimeEnvironment.EXTERNAL_STAGING

    @property
    def is_local_only(self) -> bool:
        """是否仅限本机（dev/test/local-staging）。"""

        return self in (
            RuntimeEnvironment.DEVELOPMENT,
            RuntimeEnvironment.TESTING,
            RuntimeEnvironment.LOCAL_STAGING,
        )

    @property
    def permits_real_staging_integration(self) -> bool:
        """是否允许接入/验证真实 staging。

        fail-closed 语义：仅显式分类为 LOCAL_STAGING 或已验证非生产的
        EXTERNAL_STAGING 才允许；PRODUCTION 禁止，DEV/TESTING 仅本地、无真实外部集成。
        """

        return self in (RuntimeEnvironment.LOCAL_STAGING, RuntimeEnvironment.EXTERNAL_STAGING)


@dataclass(frozen=True)
class EnvironmentResources:
    """环境持有的资源标识（用于隔离校验）。

    每个字段为一个资源种类的标识字符串（如 DB DSN 摘要、secret 后端 id、
    IdP realm、storage bucket、alert channel）。``None`` 表示该种类未声明。
    字段名必须与 ``PRODUCTION_FORBIDDEN_RESOURCE_KINDS`` 完全一致。
    """

    database: str | None = None
    secret: str | None = None
    identity_provider: str | None = None
    storage: str | None = None
    alert: str | None = None

    def declared(self) -> dict[str, str]:
        """返回非 None 的资源种类 → 标识映射。"""

        return {
            kind: value
            for kind in PRODUCTION_FORBIDDEN_RESOURCE_KINDS
            if (value := getattr(self, kind)) is not None
        }


@dataclass(frozen=True)
class EnvironmentIdentity:
    """一个运行环境的不可变身份。

    由环境分类、名称、用途、资源声明与结构指纹共同界定；指纹使身份
    不可被标签伪造（guard 比对指纹而非信任 ``kind`` 字符串）。
    """

    kind: RuntimeEnvironment
    name: str
    purpose: str
    resources: EnvironmentResources = field(default_factory=EnvironmentResources)
    fingerprint: EnvironmentFingerprint | None = None

    def with_fingerprint(self) -> "EnvironmentIdentity":
        """补齐结构指纹（若缺失）。返回新实例，不修改原实例。"""

        if self.fingerprint is not None:
            return self
        # 延迟导入，避免与 fingerprint 模块形成循环依赖。
        from agents.staging_runtime.fingerprint import compute_environment_fingerprint

        fp = compute_environment_fingerprint(
            kind=self.kind,
            name=self.name,
            purpose=self.purpose,
            resources=self.resources,
        )
        return EnvironmentIdentity(
            kind=self.kind,
            name=self.name,
            purpose=self.purpose,
            resources=self.resources,
            fingerprint=fp,
        )


# 用于 classify_environment 的别名归一（小写键 → RuntimeEnvironment）。
_ENV_ALIASES: dict[str, RuntimeEnvironment] = {
    "dev": RuntimeEnvironment.DEVELOPMENT,
    "development": RuntimeEnvironment.DEVELOPMENT,
    "develop": RuntimeEnvironment.DEVELOPMENT,
    "test": RuntimeEnvironment.TESTING,
    "testing": RuntimeEnvironment.TESTING,
    "local_staging": RuntimeEnvironment.LOCAL_STAGING,
    "local-staging": RuntimeEnvironment.LOCAL_STAGING,
    "localstaging": RuntimeEnvironment.LOCAL_STAGING,
    "staging": RuntimeEnvironment.LOCAL_STAGING,  # 未指明 external 时默认 local（fail-closed 偏向非生产）
    "external_staging": RuntimeEnvironment.EXTERNAL_STAGING,
    "external-staging": RuntimeEnvironment.EXTERNAL_STAGING,
    "externalstaging": RuntimeEnvironment.EXTERNAL_STAGING,
    "prod": RuntimeEnvironment.PRODUCTION,
    "production": RuntimeEnvironment.PRODUCTION,
    "prd": RuntimeEnvironment.PRODUCTION,
}


class EnvironmentClassificationError(ValueError):
    """环境分类失败（strict 模式下未知信号抛出）。"""


def _read_signal(signals: Mapping[str, Any], *keys: str) -> Any | None:
    """从 signals 按候选键（大小写不敏感）读取首个存在且非空的取值。"""

    lowered = {str(k).lower(): v for k, v in signals.items()}
    for key in keys:
        v = lowered.get(key.lower())
        if v not in (None, "", "none", "null"):
            return v
    return None


def classify_environment(
    signals: Mapping[str, Any],
    *,
    strict: bool = False,
) -> RuntimeEnvironment:
    """从配置信号推导运行环境分类。

    fail-closed 规则：
    - 显式 ``is_production`` / ``production`` 为真 → ``PRODUCTION``。
    - 显式 staging 信号：``external_staging`` → EXTERNAL_STAGING；``local_staging`` /
      ``staging`` → LOCAL_STAGING。
    - 显式 dev/test → 对应值。
    - 未识别（且非 production）→ 非 strict 默认 ``DEVELOPMENT``（guard 随后拒绝真实
      staging 集成）；strict 模式抛 ``EnvironmentClassificationError``。

    本函数**绝不**把 PRODUCTION 推导为 staging；未知信号只可能回落到非生产默认。
    """

    if _read_signal(signals, "is_production", "production_flag") in (True, "true", "True", "1"):
        return RuntimeEnvironment.PRODUCTION

    raw = _read_signal(signals, "runtime_environment", "app_env", "env", "environment")
    if raw is not None:
        key = str(raw).strip().lower()
        if key in _ENV_ALIASES:
            return _ENV_ALIASES[key]
        # 未知显式值：若其字面含 "prod" 则视为生产（fail-closed 偏严）；否则回落。
        if "prod" in key:
            return RuntimeEnvironment.PRODUCTION

    if strict:
        raise EnvironmentClassificationError(
            f"无法从信号 {dict(signals)} 分类运行环境（strict 模式拒绝猜测）。"
        )
    return RuntimeEnvironment.DEVELOPMENT


__all__ = [
    "PRODUCTION_FORBIDDEN_RESOURCE_KINDS",
    "RuntimeEnvironment",
    "EnvironmentResources",
    "EnvironmentIdentity",
    "EnvironmentClassificationError",
    "classify_environment",
]
