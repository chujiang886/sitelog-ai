"""Phase 3.9.14 —— External Staging 环境身份辅助（fail-closed）。

提供一致的 ``EXTERNAL_STAGING`` 身份构造与 ``PRODUCTION`` 参照身份构造，
供本包所有 harness（隔离/资格/健康/E2E/恢复/变更/证据）复用，避免各处
手抄不一致的身份，导致「把 Staging 说成 Production」的红线漂移。

所有身份构造均经 ``EnvironmentIsolationGuard`` 的前置断言：
- ``engineering_enabled is False``（红线①前置）；
- 构造即断言非 production、且允许真实 staging 集成。
"""

from __future__ import annotations

from agents.staging_runtime.environment import (
    EnvironmentIdentity,
    EnvironmentResources,
    RuntimeEnvironment,
)
from agents.staging_runtime.fingerprint import EnvironmentFingerprint
from agents.staging_runtime.isolation_guard import EnvironmentIsolationGuard


def external_staging_identity() -> EnvironmentIdentity:
    """构造 Phase 3.9.14 的 EXTERNAL_STAGING 身份（非生产、已验证非生产）。"""

    guard = EnvironmentIsolationGuard()
    identity = EnvironmentIdentity(
        kind=RuntimeEnvironment.EXTERNAL_STAGING,
        name="phase3.9.14-external-staging",
        purpose="External Staging Runtime Deployment & End-to-End Qualification (Phase 3.9.14)",
        resources=EnvironmentResources(),
    )
    guard.assert_staging_integration_permitted(identity)
    return identity.with_fingerprint()


def production_reference_identity() -> EnvironmentIdentity:
    """构造一个参照用的 PRODUCTION 身份（仅用于负向隔离校验，永不接入 staging）。

    该身份**不被** assert_staging_integration_permitted 接受（构造即触发护栏），
    调用方应直接用其做指纹/资源对照，而非传入 staging 集成路径。
    """

    return EnvironmentIdentity(
        kind=RuntimeEnvironment.PRODUCTION,
        name="reference-production",
        purpose="Reference production identity for negative isolation checks only",
        resources=EnvironmentResources(
            database="prod-db",
            secret="prod-secret",
            identity_provider="prod-idp",
            storage="prod-bucket",
            alert="prod-alert",
        ),
    ).with_fingerprint()


def forbidden_production_fingerprints() -> tuple[EnvironmentFingerprint, ...]:
    """返回已知 Production 指纹黑名单（当前为空；真实指纹由治理收口时注入）。"""

    return (production_reference_identity().fingerprint,)  # type: ignore[return-value]


__all__ = [
    "external_staging_identity",
    "production_reference_identity",
    "forbidden_production_fingerprints",
]
