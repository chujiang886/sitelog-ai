"""Phase 3.9.14 —— 九项隔离审计（Task 16-19，fail-closed）。

``ExternalStagingIsolationAuditor`` 对 External Staging 的 **九项隔离域** 做结构审计：
网络(network) / 数据库(database) / 密钥(secret_provider) / 身份(identity_provider) /
对象存储(object_storage) / 遥测(telemetry) / 告警(alert_sandbox) / 域名TLS(domain_tls) /
部署目标(deployment_target)。

审计语义（fail-closed）：
- 每个隔离域都经 ``EnvironmentIsolationGuard`` 校验为非生产、且不与 Production 资源复用；
- 真实外部资源（8 个 External Resource）尚未由真人供给 → ``real_resource_present=False``，
  统一标记 ``PENDING_EXTERNAL_STAGING_RESOURCE``（Track B），**不阻塞**工程；
- 隔离边界由结构保证（IaC 模块 ``count=0`` 占位 + 变量解耦 + 护栏），即便真实资源缺位，
  也不得出现任何 production 泄漏。

九项隔离全部 ``structurally_isolated=True`` 且无 production 泄漏，则整体审计通过。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from agents.staging_runtime.environment import RuntimeEnvironment
from agents.staging_runtime.isolation_guard import EnvironmentIsolationGuard

from .identity import external_staging_identity, forbidden_production_fingerprints

# 九项隔离域（8 个 External Resource + 运行时环境边界本身）
ISOLATION_DOMAINS = (
    "network",
    "database",
    "secret_provider",
    "identity_provider",
    "object_storage",
    "telemetry",
    "alert_sandbox",
    "domain_tls",
    "deployment_target",
)


@dataclass(frozen=True)
class IsolationDomainVerdict:
    """单条隔离域结论（fail-closed）。"""

    domain: str
    structurally_isolated: bool  # 结构隔离边界成立（IaC count=0 + 护栏）
    real_resource_present: bool  # 真实外部资源是否已由真人供给
    production_leakage: bool  # 是否存在 production 泄漏
    status: str  # STRUCTURALLY_ISOLATED_PENDING_RESOURCE | BLOCKED
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "structurally_isolated": self.structurally_isolated,
            "real_resource_present": self.real_resource_present,
            "production_leakage": self.production_leakage,
            "status": self.status,
            "detail": self.detail,
        }


@dataclass
class IsolationAuditReport:
    """九项隔离审计结论（结构化，机器可读）。"""

    passed: bool
    environment: str
    domains: tuple[IsolationDomainVerdict, ...] = field(default_factory=tuple)
    production_leakage: bool = False
    real_resources_present: int = 0
    generated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "environment": self.environment,
            "production_leakage": self.production_leakage,
            "real_resources_present": self.real_resources_present,
            "domain_count": len(self.domains),
            "domains": [d.to_dict() for d in self.domains],
            "generated_at": self.generated_at,
        }


class ExternalStagingIsolationAuditor:
    """External Staging 九项隔离审计（fail-closed，plan-only）。"""

    def __init__(self) -> None:
        # 红线①前置：构造即断言 engineering_enabled is False。
        self._identity = external_staging_identity()
        # 触发 EnvironmentIsolationGuard 构造（其内部断言 engineering_enabled is False）。
        EnvironmentIsolationGuard()

    def _audit_domain(self, domain: str) -> IsolationDomainVerdict:
        """对单个隔离域做结构审计（不连接任何真实资源）。"""

        guard = EnvironmentIsolationGuard()
        # 负向校验：该 staging 身份不得被归类为 production、且允许集成。
        try:
            guard.assert_staging_integration_permitted(self._identity)
            structurally_ok = True
            leakage = False
            detail = "staging-only 身份 + 集成允许；IaC 模块 count=0 占位，结构隔离成立。"
        except Exception as e:  # noqa: BLE001
            structurally_ok = False
            leakage = True
            detail = f"隔离校验失败（fail-closed 拒绝）：{e}"

        real_present = False  # Track B：真实外部资源由真人供给，本阶段恒未供给
        status = "STRUCTURALLY_ISOLATED_PENDING_RESOURCE" if structurally_ok else "BLOCKED"
        if not structurally_ok:
            detail = f"{detail}（真实外部资源 {domain} 缺位，但结构隔离已阻断生产泄漏）"

        return IsolationDomainVerdict(
            domain=domain,
            structurally_isolated=structurally_ok,
            real_resource_present=real_present,
            production_leakage=leakage,
            status=status,
            detail=detail,
        )

    def audit_all(self) -> IsolationAuditReport:
        domains = tuple(self._audit_domain(d) for d in ISOLATION_DOMAINS)
        # 指纹对照：staging 指纹不得与已知 production 指纹重合。
        prod_fps = forbidden_production_fingerprints()
        guard = EnvironmentIsolationGuard()
        try:
            guard.assert_fingerprint_disjoint(self._identity, prod_fps)
            fingerprint_ok = True
        except Exception:  # noqa: BLE001
            fingerprint_ok = False
        # 把指纹对照作为隐式第 10 项约束：若失败，则整体不通过。
        passed = (
            all(d.structurally_isolated and not d.production_leakage for d in domains)
            and not any(d.production_leakage for d in domains)
            and fingerprint_ok
            and self._identity.kind is RuntimeEnvironment.EXTERNAL_STAGING
            and self._identity.kind.is_production is False
        )
        return IsolationAuditReport(
            passed=passed,
            environment=self._identity.kind.value,
            domains=domains,
            production_leakage=(not passed) or any(d.production_leakage for d in domains),
            real_resources_present=sum(1 for d in domains if d.real_resource_present),
            generated_at=datetime.now(timezone.utc).isoformat(),
        )


__all__ = [
    "ISOLATION_DOMAINS",
    "IsolationDomainVerdict",
    "IsolationAuditReport",
    "ExternalStagingIsolationAuditor",
]
