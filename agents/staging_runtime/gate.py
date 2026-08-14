"""Phase 3.9.9 Real Staging Runtime Integration & Validation Layer —— Validation Gate（Task 33-34）。

``StagingValidationGate`` 运行一组**结构性**校验（不连接、不执行任何真实动作），
产出 ``StagingGateVerdict``。

终端态恒为 ``PHASE_3_9_9_REAL_STAGING_RUNTIME_VALIDATION_BUILT_NO_GO``：
- 绝不输出 ``PRODUCTION_READY`` / ``APPROVED`` / ``GO``；
- ``is_production`` 永远 False；
- ``external_pending=True``（缺真实外部 Staging 资源）；
- ``human_verification_required=True``（四角色线下验证/签署后才可授权真实部署）。

fail-closed：任意校验失败或检测到 production 泄漏即整体不通过。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from agents.staging_runtime.config import load_staging_identity
from agents.staging_runtime.environment import EnvironmentIdentity, RuntimeEnvironment
from agents.staging_runtime.isolation_guard import (
    EnvironmentIsolationGuard,
    StagingIsolationViolationError,
)
from agents.staging_runtime.execution_scope import FORBIDDEN_PRODUCTION_ACTIONS
from agents.staging_runtime.deployment import StagingDeploymentProvider, StagingDeploymentForbiddenError
from agents.staging_runtime.db import (
    StagingDatabaseProvider,
    StagingMigrationSafety,
    StagingMigrationForbiddenError,
    MigrationPlan,
)
from agents.staging_runtime.data_policy import StagingDataPolicy
from agents.staging_runtime.token_isolation import StagingTokenIsolation
from agents.staging_runtime.evidence import build_staging_evidence

# 本阶段终端态（禁 PRODUCTION_READY / APPROVED / GO）。
TERMINAL_STATE = "PHASE_3_9_9_REAL_STAGING_RUNTIME_VALIDATION_BUILT_NO_GO"

# 本阶段允许的「非 production」环境集合。
_ALLOWED_ENVIRONMENTS = frozenset(
    {RuntimeEnvironment.LOCAL_STAGING, RuntimeEnvironment.EXTERNAL_STAGING}
)


@dataclass(frozen=True)
class StagingGateCheck:
    """单条 Gate 校验。"""

    name: str
    passed: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class StagingGateVerdict:
    """Gate 结论（结构化，机器可读）。"""

    passed: bool
    terminal_state: str
    environment: str
    is_production: bool
    checks: tuple[StagingGateCheck, ...]
    evidence_hash: str
    external_pending: bool
    human_verification_required: bool
    generated_at: str

    def require_passed(self) -> None:
        if not self.passed:  # pragma: no cover - defensive
            raise StagingGateError("Gate 未通过，禁止推进到任何 production 动作。")

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "terminal_state": self.terminal_state,
            "environment": self.environment,
            "is_production": self.is_production,
            "checks": [c.to_dict() for c in self.checks],
            "evidence_hash": self.evidence_hash,
            "external_pending": self.external_pending,
            "human_verification_required": self.human_verification_required,
            "generated_at": self.generated_at,
        }


class StagingGateError(Exception):
    """Gate 未通过（fail-closed）。"""


class StagingValidationGate:
    """本地预生产验证 Gate（结构性校验电池，不执行真实动作）。"""

    def __init__(self, identity: EnvironmentIdentity | None = None) -> None:
        self._identity = identity or load_staging_identity()
        guard = EnvironmentIsolationGuard()
        try:
            guard.assert_staging_integration_permitted(self._identity)
        except StagingIsolationViolationError as e:
            raise StagingGateError(str(e))
        if self._identity.kind not in _ALLOWED_ENVIRONMENTS:
            raise StagingGateError(
                f"环境 {self._identity.kind.value} 不在允许集合（local_staging/external_staging），"
                "Gate 拒绝运行。"
            )

    def run(
        self,
        *,
        secret_names: Iterable[str] = (),
        production_refs: dict[str, Iterable[str]] | None = None,
    ) -> StagingGateVerdict:
        checks: list[StagingGateCheck] = []
        ident = self._identity

        # 1. 环境分类非 production
        checks.append(
            StagingGateCheck(
                name="environment_non_production",
                passed=not ident.kind.is_production,
                detail=f"kind={ident.kind.value}",
            )
        )

        # 2. 隔离护栏通过
        try:
            EnvironmentIsolationGuard().assert_staging_integration_permitted(ident)
            checks.append(StagingGateCheck(name="isolation_guard", passed=True, detail="staging-only + 集成允许"))
        except StagingIsolationViolationError as e:
            checks.append(StagingGateCheck(name="isolation_guard", passed=False, detail=str(e)))

        # 3. 执行边界：禁止动作令牌全拒
        from agents.staging_runtime.execution_scope import StagingExecutionScope

        scope = StagingExecutionScope(ident)
        forbidden_rejected = all(not scope.is_permitted(a) for a in FORBIDDEN_PRODUCTION_ACTIONS)
        checks.append(
            StagingGateCheck(
                name="execution_scope_forbids_production",
                passed=forbidden_rejected,
                detail=f"forbidden_actions={len(FORBIDDEN_PRODUCTION_ACTIONS)}",
            )
        )

        # 4. 部署 apply 永远拒绝
        try:
            StagingDeploymentProvider(ident).apply()
            checks.append(StagingGateCheck(name="deployment_apply_forbidden", passed=False, detail="apply 未拒绝"))
        except StagingDeploymentForbiddenError:
            checks.append(StagingGateCheck(name="deployment_apply_forbidden", passed=True, detail="apply 正确拒绝"))

        # 5. 迁移 apply 永远拒绝
        try:
            StagingMigrationSafety(ident).apply(MigrationPlan(name="g", targets=("local_staging",)))
            checks.append(StagingGateCheck(name="migration_apply_forbidden", passed=False, detail="apply 未拒绝"))
        except StagingMigrationForbiddenError:
            checks.append(StagingGateCheck(name="migration_apply_forbidden", passed=True, detail="apply 正确拒绝"))

        # 6. DB Provider describe 非 production
        try:
            StagingDatabaseProvider(ident, staging_dsn="staging-dsn").describe()
            checks.append(StagingGateCheck(name="db_provider_non_production", passed=True, detail="describe OK"))
        except Exception as e:  # noqa: BLE001
            checks.append(StagingGateCheck(name="db_provider_non_production", passed=False, detail=str(e)))

        # 7. 数据策略拒绝真实 PII
        policy = StagingDataPolicy(ident)
        checks.append(
            StagingGateCheck(
                name="data_policy_rejects_real_pii",
                passed=not policy.classify("real_pii").permitted,
                detail="real_pii 被拒绝",
            )
        )

        # 8. 令牌隔离（staging 令牌 ≠ production 令牌）
        token = StagingTokenIsolation(ident, production_token_refs=set((production_refs or {}).get("secret", ())))
        checks.append(
            StagingGateCheck(
                name="token_isolation",
                passed=token.check_token("t", "staging-token").isolated,
                detail="staging 令牌未命中 production 引用",
            )
        )

        # 9. 证据模型无 production 泄漏
        evidence = build_staging_evidence(
            ident, secret_names=list(secret_names), production_refs=production_refs
        )
        checks.append(
            StagingGateCheck(
                name="evidence_no_production_leakage",
                passed=not evidence.has_production_leakage(),
                detail=f"violations={len(evidence.violations())}",
            )
        )

        passed = all(c.passed for c in checks) and not ident.kind.is_production

        return StagingGateVerdict(
            passed=passed,
            terminal_state=TERMINAL_STATE,
            environment=ident.kind.value,
            is_production=ident.kind.is_production,
            checks=tuple(checks),
            evidence_hash=evidence.integrity_hash(),
            external_pending=True,  # 缺真实外部 Staging 资源
            human_verification_required=True,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )


__all__ = [
    "TERMINAL_STATE",
    "StagingGateCheck",
    "StagingGateVerdict",
    "StagingGateError",
    "StagingValidationGate",
]
