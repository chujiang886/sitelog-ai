"""Phase 3.9.9 Real Staging Runtime Integration & Validation Layer —— Staging 配置（Task 4）。

从 ``agents/config.yaml::staging`` 段加载本地预生产配置，构建结构身份
``EnvironmentIdentity`` 并经 ``EnvironmentIsolationGuard`` 校验，确保：

- staging 环境分类**绝不**是 PRODUCTION（``config.staging.environment`` 只能解析为
  ``local_staging`` / ``external_staging``，否则抛 ``StagingConfigError``）；
- 资源声明（database/secret/identity_provider/storage/alert）经隔离校验，结构上
  不得等于 production（fail-closed，靠指纹与护栏而非文档约定）；
- 缺真实外部 Staging 资源时标记 ``PENDING_EXTERNAL_STAGING_RESOURCE``，工程不阻塞，
  继续完成可独立验证的 Local Staging 项。

设计红线：本模块**不**打开 ``engineering_enabled``、**不**输出 ``engineering_approved``、
**不**写真实 Secret；所有资源值经 ``${VAR:pending_verification}`` 占位或环境变量注入。
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Iterable, Mapping

from agents.config_loader import load_staging_config
from agents.staging_runtime.environment import (
    EnvironmentIdentity,
    EnvironmentResources,
    RuntimeEnvironment,
    classify_environment,
)
from agents.staging_runtime.fingerprint import EnvironmentFingerprint
from agents.staging_runtime.isolation_guard import EnvironmentIsolationGuard


class StagingResourceReadiness(str, Enum):
    """Staging 资源就绪状态（用于标记 PENDING，不阻塞工程）。

    - ``READY``：资源已配置（本地或外部 staging，非生产）。
    - ``PENDING_EXTERNAL_STAGING_RESOURCE``：缺真实外部 Staging 资源（全部或未决为
      ``pending_verification``）。
    - ``PENDING_HUMAN_STAGING_VERIFICATION``：资源已声明但需人工设备/核对项。
    """

    READY = "ready"
    PENDING_EXTERNAL_STAGING_RESOURCE = "pending_external_staging_resource"
    PENDING_HUMAN_STAGING_VERIFICATION = "pending_human_staging_verification"


class StagingConfigError(ValueError):
    """Staging 配置加载/校验失败（fail-closed）。"""


def _build_resources(raw: Mapping[str, Any]) -> EnvironmentResources:
    """从 ``staging.resources`` 段构造 ``EnvironmentResources``（None 表示未声明）。"""

    resources = raw.get("resources", {}) or {}
    return EnvironmentResources(
        database=resources.get("database"),
        secret=resources.get("secret"),
        identity_provider=resources.get("identity_provider"),
        storage=resources.get("storage"),
        alert=resources.get("alert"),
    )


def load_staging_identity(
    config_path: str | None = None,
    *,
    strict: bool = False,
) -> EnvironmentIdentity:
    """从 ``config.yaml::staging`` 加载并校验 Local Staging 身份。

    fail-closed 行为：
    - 环境分类来自 ``staging.environment`` 信号；解析为 PRODUCTION 直接抛
      ``StagingConfigError``（绝不把 production 当 staging）。
    - 构造 ``EnvironmentIsolationGuard``（其前置断言 ``engineering_enabled is False``），
      经 ``assert_staging_integration_permitted`` 校验允许真实 staging 集成。
    - 缺真实外部资源时，资源值回落 ``pending_verification``；这**不**影响结构校验，
      仅表示接入待补全（上层据此标记 ``PENDING_EXTERNAL_STAGING_RESOURCE``）。
    """

    section: Mapping[str, Any] = (
        load_staging_config(config_path) if config_path is not None else load_staging_config()
    ) or {}
    env_signal = section.get("environment", "local_staging")
    kind = classify_environment({"environment": env_signal}, strict=strict)
    if kind.is_production:
        raise StagingConfigError(
            f"config.yaml::staging.environment 被解析为 PRODUCTION（信号 {env_signal!r}），"
            "违反红线：staging 环境不得是生产环境。"
        )

    name = section.get("name", "phase3.9.9-local-staging")
    purpose = section.get(
        "purpose",
        "Real non-production pre-prod runtime integration & validation (Phase 3.9.9)",
    )
    resources = _build_resources(section)
    identity = EnvironmentIdentity(kind=kind, name=name, purpose=purpose, resources=resources)

    # 结构校验：engineering_enabled 前置 + staging-only + 集成允许（fail-closed）。
    guard = EnvironmentIsolationGuard()
    guard.assert_staging_integration_permitted(identity)

    return identity.with_fingerprint()


def load_forbidden_production_fingerprints(
    config_path: str | None = None,
) -> tuple[EnvironmentFingerprint, ...]:
    """读取 ``staging.forbidden_production_fingerprints`` 黑名单（占位空，不内联真实生产值）。

    收口时由治理注入真实生产指纹；此处仅原样返回配置列表（当前为空），不参与伪造。
    """

    section: Mapping[str, Any] = (
        load_staging_config(config_path) if config_path is not None else load_staging_config()
    ) or {}
    raw = section.get("forbidden_production_fingerprints", []) or []
    return tuple(
        EnvironmentFingerprint(value=str(v))
        for v in raw
        if isinstance(v, (str, bytes)) and v
    )


def staging_resource_readiness(identity: EnvironmentIdentity) -> StagingResourceReadiness:
    """根据资源声明判断就绪状态：未声明或全为 pending_verification → 缺外部资源。"""

    declared = identity.resources.declared()
    if not declared:
        return StagingResourceReadiness.PENDING_EXTERNAL_STAGING_RESOURCE
    if all(str(v) == "pending_verification" for v in declared.values()):
        return StagingResourceReadiness.PENDING_EXTERNAL_STAGING_RESOURCE
    return StagingResourceReadiness.READY


__all__ = [
    "StagingResourceReadiness",
    "StagingConfigError",
    "load_staging_identity",
    "load_forbidden_production_fingerprints",
    "staging_resource_readiness",
]


# 引用防剔除：RuntimeEnvironment 在 classify_environment 间接使用，显式保留符号。
_ = RuntimeEnvironment
