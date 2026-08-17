"""Phase 3.9.14 —— 13 项 Runtime Qualification 资格 harness（Task 20-28，fail-closed）。

``RuntimeQualificationHarness`` **真实驱动** ``agents/staging_runtime/`` 各安全提供方，
对 13 个能力域做**结构性安全证明**：每个域的运行不是「空框架 Pending」，而是确实执行了
提供方代码并断言其 fail-closed 安全行为（例如：StagingDatabaseProvider 拒绝复用 Production
DSN、StagingDataPolicy 拒绝 real_pii、StagingExecutionScope 拒绝所有生产动作令牌……）。

关键语义：
- ``code_verified=True``：该域的安全行为已真实运行并通过；
- ``runtime_executed=False``：未连接任何真实外部资源（8 个 External Resource 仍 Pending，
  真实端到端运行时资格属于 Track B，须真人供给资源 + 双钥匙授权后执行）；
- ``status=STRUCTURALLY_QUALIFIED_PENDING_RUNTIME``：结构性资格已证明，待真实运行时；
- 任一域失败 → 整体 ``all_structurally_qualified=False``（fail-closed，不掩盖）。
所有断言失败都会被捕获为 ``FAILED``，绝不 skip / xfail 吞掉。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from agents.staging_runtime.config import load_staging_identity
from agents.staging_runtime.environment import (
    EnvironmentIdentity,
    EnvironmentResources,
    RuntimeEnvironment,
    classify_environment,
)
from agents.staging_runtime.fingerprint import compute_environment_fingerprint, fingerprints_disjoint
from agents.staging_runtime.isolation_guard import EnvironmentIsolationGuard
from agents.staging_runtime.secret_provider import StagingSecretProvider, StagingSecretIsolationError
from agents.staging_runtime.local_profile import LocalStagingProfile
from agents.staging_runtime.execution_scope import (
    StagingExecutionScope,
    FORBIDDEN_PRODUCTION_ACTIONS,
    ALLOWED_STAGING_ACTIONS,
)
from agents.staging_runtime.db import StagingDatabaseProvider, StagingDatabaseError
from agents.staging_runtime.data_policy import StagingDataPolicy
from agents.staging_runtime.identity_provider import (
    StagingIdentityProvider,
    StagingIdentityProviderError,
)
from agents.staging_runtime.token_isolation import StagingTokenIsolation
from agents.staging_runtime.observability import StagingTelemetry, StagingRuntimeHealth

from .change_control import StagingRuntimeValidationGate, TERMINAL_STATE
from .identity import external_staging_identity, production_reference_identity

# 13 项 Runtime Qualification 检查名（与 runtime_manifest.RUNTIME_QUALIFICATION_CHECKS 一致）
QUALIFICATION_CHECKS = [
    "environment_classification",
    "fingerprint_isolation",
    "isolation_guard",
    "config_readiness",
    "secret_isolation",
    "local_profile",
    "execution_scope",
    "db_safety",
    "data_policy",
    "identity_isolation",
    "token_isolation",
    "observability_health",
    "gate_validation",
]

_RUNTIME_PENDING_STATUS = "STRUCTURALLY_QUALIFIED_PENDING_RUNTIME"


@dataclass(frozen=True)
class QualificationCheckResult:
    """单条资格检查结果（fail-closed）。"""

    name: str
    code_verified: bool       # 安全提供方行为已真实运行并通过
    runtime_executed: bool    # 是否连接真实外部资源（恒 False）
    status: str               # STRUCTURALLY_QUALIFIED_PENDING_RUNTIME | FAILED
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "code_verified": self.code_verified,
            "runtime_executed": self.runtime_executed,
            "status": self.status,
            "detail": self.detail,
        }


@dataclass
class RuntimeQualificationReport:
    """13 项资格汇总（结构化，机器可读）。"""

    passed: bool
    code_verified_count: int
    runtime_executed_count: int
    total: int
    is_production: bool
    real_apply_allowed: bool
    checks: tuple[QualificationCheckResult, ...] = field(default_factory=tuple)
    generated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "code_verified_count": self.code_verified_count,
            "runtime_executed_count": self.runtime_executed_count,
            "total": self.total,
            "is_production": self.is_production,
            "real_apply_allowed": self.real_apply_allowed,
            "checks": [c.to_dict() for c in self.checks],
            "generated_at": self.generated_at,
        }


def _run_check(name: str, fn: Callable[[], None]) -> QualificationCheckResult:
    """运行单条资格检查；捕获一切异常为 FAILED（fail-closed，不掩盖）。"""

    try:
        fn()
        return QualificationCheckResult(
            name=name,
            code_verified=True,
            runtime_executed=False,
            status=_RUNTIME_PENDING_STATUS,
            detail="安全提供方行为已真实运行并通过结构性 fail-closed 断言。",
        )
    except Exception as e:  # noqa: BLE001
        return QualificationCheckResult(
            name=name,
            code_verified=False,
            runtime_executed=False,
            status="FAILED",
            detail=f"资格检查失败：{type(e).__name__}: {e}",
        )


class RuntimeQualificationHarness:
    """13 项 Runtime Qualification harness（真实驱动安全提供方，plan-only）。"""

    def __init__(self, identity: EnvironmentIdentity | None = None) -> None:
        self._identity = identity or external_staging_identity()

    # ---- 13 项检查实现（每项均为真实代码执行 + 结构性 fail-closed 断言）----

    def _check_environment_classification(self) -> None:
        assert classify_environment({"environment": "external_staging"}) is RuntimeEnvironment.EXTERNAL_STAGING
        # 负向：production 信号不得被归类为 staging
        assert classify_environment({"is_production": True}) is RuntimeEnvironment.PRODUCTION
        assert classify_environment({"environment": "prod"}) is RuntimeEnvironment.PRODUCTION

    def _check_fingerprint_isolation(self) -> None:
        fp = compute_environment_fingerprint(
            kind=RuntimeEnvironment.EXTERNAL_STAGING,
            name="phase3.9.14-external-staging",
            purpose="external staging runtime e2e qualification",
            resources=EnvironmentResources(),
        )
        prod_fp = production_reference_identity().fingerprint
        assert fingerprints_disjoint([prod_fp], fp)  # type: ignore[arg-type]

    def _check_isolation_guard(self) -> None:
        guard = EnvironmentIsolationGuard()
        v = guard.validate(self._identity)
        assert v.passed, "staging 隔离校验应整体通过"
        # 负向：production 身份应触发违例
        pv = guard.validate(production_reference_identity())
        assert not pv.passed, "production 身份隔离校验应失败"

    def _check_config_readiness(self) -> None:
        # 真实加载 config.yaml::staging，断言非生产且指纹就绪。
        ident = load_staging_identity()
        assert not ident.kind.is_production
        assert ident.fingerprint is not None

    def _check_secret_isolation(self) -> None:
        p = StagingSecretProvider(self._identity)
        snap = p.snapshot(["db_dsn", "idp_secret"])
        assert all(not r.resolved for r in snap), "缺真实外部 Secret，应全 pending"
        # 负向：production secret 复用拒绝
        p2 = StagingSecretProvider(
            self._identity,
            production_secret_refs={"leaked-prod-secret"},
            env={"STAGING_SECRET_X": "leaked-prod-secret"},
        )
        raised = False
        try:
            p2.resolve("x", env_var="STAGING_SECRET_X")
        except StagingSecretIsolationError:
            raised = True
        assert raised, "staging Secret 命中 production 引用应被拒绝"

    def _check_local_profile(self) -> None:
        m = LocalStagingProfile().build_manifest()
        assert m["is_production"] is False
        assert m["non_production_bound"] is True

    def _check_execution_scope(self) -> None:
        scope = StagingExecutionScope(self._identity)
        assert all(not scope.is_permitted(a) for a in FORBIDDEN_PRODUCTION_ACTIONS)
        assert all(scope.is_permitted(a) for a in ALLOWED_STAGING_ACTIONS)

    def _check_db_safety(self) -> None:
        d = StagingDatabaseProvider(self._identity, staging_dsn="staging-dsn").describe()
        assert d.dsn_present and d.non_production
        # 负向：production DSN 复用拒绝
        raised = False
        try:
            StagingDatabaseProvider(
                self._identity, production_dsn_refs={"prod-dsn"}, staging_dsn="prod-dsn"
            ).describe()
        except StagingDatabaseError:
            raised = True
        assert raised, "staging DSN 命中 production DSN 应被拒绝"

    def _check_data_policy(self) -> None:
        pol = StagingDataPolicy(self._identity)
        assert not pol.classify("real_pii").permitted
        assert not pol.classify("production_snapshot").permitted
        assert pol.classify("synthetic").permitted
        assert not pol.classify("unknown_class").permitted

    def _check_identity_isolation(self) -> None:
        i = StagingIdentityProvider(self._identity, staging_issuer="staging-idp").describe()
        assert i.issuer_present and i.non_production
        raised = False
        try:
            StagingIdentityProvider(
                self._identity, production_issuer_refs={"prod-idp"}, staging_issuer="prod-idp"
            ).describe()
        except StagingIdentityProviderError:
            raised = True
        assert raised, "staging issuer 命中 production issuer 应被拒绝"

    def _check_token_isolation(self) -> None:
        t = StagingTokenIsolation(self._identity)
        assert t.check_token("t", "staging-token").isolated
        t2 = StagingTokenIsolation(self._identity, production_token_refs={"prod-token"})
        assert not t2.check_token("t", "prod-token").isolated

    def _check_observability_health(self) -> None:
        m = StagingTelemetry(self._identity).to_manifest()
        assert m["collects_real_data"] is False
        assert m["is_production"] is False
        checks = StagingRuntimeHealth(self._identity).describe_checks()
        assert len(checks) == 4
        assert all(c.non_production for c in checks)

    def _check_gate_validation(self) -> None:
        v = StagingRuntimeValidationGate(self._identity).run()
        assert v.passed
        assert v.terminal_state == TERMINAL_STATE
        assert v.is_production is False
        assert v.external_pending is True

    def qualify_all(self) -> RuntimeQualificationReport:
        handlers = {
            "environment_classification": self._check_environment_classification,
            "fingerprint_isolation": self._check_fingerprint_isolation,
            "isolation_guard": self._check_isolation_guard,
            "config_readiness": self._check_config_readiness,
            "secret_isolation": self._check_secret_isolation,
            "local_profile": self._check_local_profile,
            "execution_scope": self._check_execution_scope,
            "db_safety": self._check_db_safety,
            "data_policy": self._check_data_policy,
            "identity_isolation": self._check_identity_isolation,
            "token_isolation": self._check_token_isolation,
            "observability_health": self._check_observability_health,
            "gate_validation": self._check_gate_validation,
        }
        results = tuple(
            _run_check(name, handlers[name]) for name in QUALIFICATION_CHECKS
        )
        code_ok = sum(1 for r in results if r.code_verified)
        passed = all(r.code_verified for r in results) and self._identity.kind.is_production is False
        return RuntimeQualificationReport(
            passed=passed,
            code_verified_count=code_ok,
            runtime_executed_count=0,
            total=len(results),
            is_production=self._identity.kind.is_production,
            real_apply_allowed=False,
            checks=results,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )


__all__ = [
    "QUALIFICATION_CHECKS",
    "QualificationCheckResult",
    "RuntimeQualificationReport",
    "RuntimeQualificationHarness",
]
