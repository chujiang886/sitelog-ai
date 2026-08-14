"""Phase 3.9.9 Real Staging Runtime Integration & Validation Layer —— 环境隔离护栏（Task 2）。

``EnvironmentIsolationGuard`` 是「代码级证明 Staging != Production」的执行层：
- 构造即断言 ``engineering_enabled is False``（红线①前置）。
- ``assert_staging_only``：PRODUCTION 永远不得被当作 staging 接入（红线：把 Staging 说成 Production）。
- ``assert_resource_isolation``：staging 不得复用 Production 的 database / secret /
  identity_provider / storage / alert（红线：复用 Production 资源）。
- ``assert_staging_integration_permitted``：仅 LOCAL_STAGING / 已验证非生产 EXTERNAL_STAGING
  可接入真实 staging；其余一律 refuse（fail-closed）。

所有违例为 **fail-closed**：无法验证即拒绝，不靠文档约定兜底。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    safety_invariants_ok,
)
from agents.staging_runtime.environment import (
    PRODUCTION_FORBIDDEN_RESOURCE_KINDS,
    EnvironmentIdentity,
    RuntimeEnvironment,
)
from agents.staging_runtime.fingerprint import EnvironmentFingerprint, fingerprints_disjoint


class StagingIsolationViolationError(Exception):
    """Staging 隔离违例：结构上拒绝 staging 触碰 production。"""


@dataclass(frozen=True)
class IsolationViolation:
    """单条隔离违例记录。"""

    kind: str  # "production_classified_as_staging" | "resource_reuse" | "integration_not_permitted" | "unknown_production"
    detail: str


@dataclass(frozen=True)
class IsolationVerdict:
    """隔离校验结论（非抛出异常式的结构化结果）。"""

    passed: bool
    environment: RuntimeEnvironment
    violations: tuple[IsolationViolation, ...]
    checked_at: str

    def require_ok(self) -> None:
        """不通过则抛出 ``StagingIsolationViolationError``。"""

        if not self.passed:
            raise StagingIsolationViolationError(
                "环境隔离校验未通过：" + "; ".join(v.detail for v in self.violations)
            )


class EnvironmentIsolationGuard:
    """Staging/Production 环境隔离护栏（fail-closed）。"""

    def __init__(self) -> None:
        # 红线①前置：构造即断言 engineering_enabled is False。
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "EnvironmentIsolationGuard 构造失败：engineering_enabled 必须为 False（红线①）。"
            )

    # ---- 单点断言 ----

    def assert_staging_only(self, env: EnvironmentIdentity) -> None:
        """环境不得是 PRODUCTION（红线：把 Staging 说成 Production）。"""

        if env.kind.is_production:
            raise StagingIsolationViolationError(
                f"环境 {env.name!r} 被分类为 PRODUCTION，不得作为 staging 接入。"
            )

    def assert_staging_integration_permitted(self, env: EnvironmentIdentity) -> None:
        """仅 LOCAL_STAGING / 已验证非生产 EXTERNAL_STAGING 可接入真实 staging。"""

        if not env.kind.permits_real_staging_integration:
            raise StagingIsolationViolationError(
                f"环境 {env.name!r}（{env.kind.value}）不允许接入真实 staging 集成；"
                "仅 local_staging / 已验证非生产的 external_staging 允许。"
            )
        self.assert_staging_only(env)

    def assert_resource_isolation(
        self,
        staging: EnvironmentIdentity,
        production: EnvironmentIdentity,
    ) -> None:
        """staging 不得复用 production 的受禁资源（DB/Secret/IdP/Storage/Alert）。"""

        if not production.kind.is_production:
            raise StagingIsolationViolationError(
                "无法验证 production 身份：传入的生产环境标识其 kind 非 PRODUCTION，"
                "隔离校验中止（fail-closed）。"
            )
        self.assert_staging_only(staging)

        shared: list[str] = []
        for kind in sorted(PRODUCTION_FORBIDDEN_RESOURCE_KINDS):
            s_val = getattr(staging.resources, kind)
            p_val = getattr(production.resources, kind)
            if s_val is not None and p_val is not None and s_val == p_val:
                shared.append(kind)
        if shared:
            raise StagingIsolationViolationError(
                f"Staging 环境 {staging.name!r} 复用了 Production 资源：{', '.join(shared)}。"
                "红线：禁止复用 Production DB/Secret/IdP/Storage/Alert。"
            )

    def assert_fingerprint_disjoint(
        self,
        staging: EnvironmentIdentity,
        production_fingerprints: Iterable[EnvironmentFingerprint],
    ) -> None:
        """staging 指纹必须与所有已知 production 指纹不同（防改名伪装）。"""

        staging_fp = (staging.fingerprint or staging.with_fingerprint().fingerprint)
        if not fingerprints_disjoint(production_fingerprints, staging_fp):  # type: ignore[arg-type]
            raise StagingIsolationViolationError(
                f"Staging 环境 {staging.name!r} 的指纹与某个 Production 指纹重合，"
                "疑似伪装（红线：把 Staging 说成 Production）。"
            )

    # ---- 结构化校验（返回 verdict，不强制抛异常）----

    def validate(
        self,
        staging: EnvironmentIdentity,
        *,
        production: EnvironmentIdentity | None = None,
        production_fingerprints: Iterable[EnvironmentFingerprint] = (),
    ) -> IsolationVerdict:
        """对 staging 环境做完整隔离校验，返回结构化结论。"""

        violations: list[IsolationViolation] = []
        if staging.kind.is_production:
            violations.append(
                IsolationViolation(
                    kind="production_classified_as_staging",
                    detail=f"环境 {staging.name!r} 是 PRODUCTION，不得作为 staging。",
                )
            )
        if not staging.kind.permits_real_staging_integration:
            violations.append(
                IsolationViolation(
                    kind="integration_not_permitted",
                    detail=f"环境 {staging.name!r}（{staging.kind.value}）不允许真实 staging 集成。",
                )
            )
        if production is not None:
            if not production.kind.is_production:
                violations.append(
                    IsolationViolation(
                        kind="unknown_production",
                        detail="传入的 production 环境标识其 kind 非 PRODUCTION，无法校验资源隔离。",
                    )
                )
            else:
                for kind in sorted(PRODUCTION_FORBIDDEN_RESOURCE_KINDS):
                    s_val = getattr(staging.resources, kind)
                    p_val = getattr(production.resources, kind)
                    if s_val is not None and p_val is not None and s_val == p_val:
                        violations.append(
                            IsolationViolation(
                                kind="resource_reuse",
                                detail=f"staging {staging.name!r} 复用 production 资源：{kind}。",
                            )
                        )
        checked_at = datetime.now(timezone.utc).isoformat()
        return IsolationVerdict(
            passed=len(violations) == 0,
            environment=staging.kind,
            violations=tuple(violations),
            checked_at=checked_at,
        )


__all__ = [
    "StagingIsolationViolationError",
    "IsolationViolation",
    "IsolationVerdict",
    "EnvironmentIsolationGuard",
]
