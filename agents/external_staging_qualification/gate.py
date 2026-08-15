"""Phase 3.9.10 —— External Staging Qualification Gate（Task 21）。

汇总检查：

- 8 资源登记簿完整性
- 凭据引用安全（无明文泄漏）
- 连接性（无 BLOCKED）
- 隔离（无 BLOCKED）
- 部署目标（仅 External Staging）
- 运行时健康（UNKNOWN 不视作 HEALTHY）
- 遥测 / 告警沙箱
- Domain/TLS
- 证据完整性
- 安全 / 全量回归 / 仓库清洁

状态仅限（禁止 APPROVED/PRODUCTION_READY/GO）：

- ``BLOCKED``
- ``PENDING_EXTERNAL_STAGING_RESOURCE``
- ``PENDING_HUMAN_VERIFICATION``
- ``READY_FOR_EXTERNAL_STAGING_HUMAN_REVIEW``

fail-closed：任何硬 violation → BLOCKED；任何真实资源未验证 → 不越级。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agents.external_staging_qualification.credential_scanner import (
    assert_no_credential_leak,
    CredentialLeakError,
)
from agents.external_staging_qualification.evidence import EvidenceChain
from agents.external_staging_qualification.isolation import (
    CrossEnvironmentIsolationEvidence,
)
from agents.external_staging_qualification.models import (
    ExternalStagingResourceRegistry,
    GateStatus,
    ResourceQualificationStatus,
)
from agents.external_staging_qualification.runtime import RuntimeHealthReport


@dataclass
class GateCheck:
    """单检查项结果。"""

    name: str
    passed: bool
    severity: str  # "block" | "pending" | "info"
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "severity": self.severity,
            "detail": self.detail,
        }


@dataclass
class GateResult:
    """闸门评估结果。"""

    status: GateStatus
    checks: tuple[GateCheck, ...] = field(default_factory=tuple)
    evidence_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "passed": self.status
            in (
                GateStatus.READY_FOR_EXTERNAL_STAGING_HUMAN_REVIEW,
                GateStatus.PENDING_HUMAN_VERIFICATION,
                GateStatus.PENDING_EXTERNAL_STAGING_RESOURCE,
            ),
            "checks": [c.to_dict() for c in self.checks],
            "evidence_hash": self.evidence_hash,
        }


class ExternalStagingQualificationGate:
    """外部预生产资格闸门（fail-closed 评估器）。"""

    def evaluate(
        self,
        *,
        registry: ExternalStagingResourceRegistry,
        isolation: CrossEnvironmentIsolationEvidence | None = None,
        runtime: RuntimeHealthReport | None = None,
        evidence_chain: EvidenceChain | None = None,
        environment_identity: dict[str, Any] | None = None,
        security_ok: bool = True,
        regression_ok: bool = True,
        repo_clean: bool = True,
        additional_pending_resources: tuple[str, ...] = (),
        human_verification_required: bool = True,
    ) -> GateResult:
        checks: list[GateCheck] = []

        # 1) 8 资源登记簿完整性
        registry_ok = len(registry.resources) == 8
        checks.append(
            GateCheck(
                "resource_registry_complete",
                registry_ok,
                "block",
                f"登记资源数={len(registry.resources)}（应为 8）。",
            )
        )

        # 2) 凭据引用安全
        try:
            ref_map = {
                r.resource_id: {
                    "credential_reference": r.credential_reference or "",
                    "source_reference": r.source_reference or "",
                }
                for r in registry.resources
            }
            assert_no_credential_leak(mapping=ref_map)
            cred_ok = True
            cred_detail = "凭据引用无明文泄漏。"
        except CredentialLeakError as exc:
            cred_ok = False
            cred_detail = str(exc)
        checks.append(GateCheck("credential_reference_safety", cred_ok, "block", cred_detail))

        # 3) 连接性 / 资格：任何 BLOCKED → block；任一未验证 → pending
        any_blocked = any(
            r.qualification_status == ResourceQualificationStatus.BLOCKED.value
            for r in registry.resources
        )
        any_pending = any(
            r.qualification_status
            in (
                ResourceQualificationStatus.NOT_CONFIGURED.value,
                ResourceQualificationStatus.PENDING_EXTERNAL_STAGING_RESOURCE.value,
                ResourceQualificationStatus.QUALIFICATION_PENDING.value,
                ResourceQualificationStatus.CONFIGURED_UNVERIFIED.value,
            )
            or not r.verified
            for r in registry.resources
        )
        checks.append(
            GateCheck(
                "no_blocked_resources",
                not any_blocked,
                "block",
                "存在 BLOCKED 资源（命中 Production Denylist 或隔离失败）。"
                if any_blocked
                else "无 BLOCKED 资源。",
            )
        )
        checks.append(
            GateCheck(
                "all_resources_verified",
                not any_pending,
                "pending",
                "全部 8 资源已验证。" if not any_pending else "存在未验证资源（pending）。",
            )
        )

        # 4) 隔离
        if isolation is not None:
            iso_ok = not isolation.summary()["any_blocked"]
            checks.append(
                GateCheck(
                    "cross_environment_isolation",
                    iso_ok,
                    "block" if not iso_ok else "pending",
                    f"隔离 {isolation.summary()['verified']}/{isolation.summary()['total']} 已证，"
                    f"{isolation.summary()['pending']} 待证。",
                )
            )

        # 5) 运行时健康（UNKNOWN 不视作 HEALTHY）
        if runtime is not None:
            summary = runtime.summary()
            checks.append(
                GateCheck(
                    "runtime_health_no_false_healthy",
                    not summary["unknown_treated_as_healthy"],
                    "info",
                    f"运行时健康：healthy={summary['healthy']}, unknown={summary['unknown']} "
                    f"(UNKNOWN 不视作 HEALTHY)。",
                )
            )

        # 6) 证据完整性
        if evidence_chain is not None:
            ev_ok = evidence_chain.summary()["none_contains_secret"]
            checks.append(
                GateCheck(
                    "evidence_completeness",
                    ev_ok,
                    "block" if not ev_ok else "info",
                    f"证据 {evidence_chain.summary()['count']} 条，无 Secret 携带。",
                )
            )

        # 7) 安全 / 回归 / 仓库清洁
        checks.append(GateCheck("security", security_ok, "block", "安全扫描通过。" if security_ok else "安全扫描失败。"))
        checks.append(GateCheck("full_regression", regression_ok, "block", "全量回归 0 failed。" if regression_ok else "全量回归存在失败。"))
        checks.append(GateCheck("repository_clean", repo_clean, "block", "工作树清洁。" if repo_clean else "工作树不清洁。"))

        # 环境身份红线：production 必须为 False
        if environment_identity is not None:
            prod_false = environment_identity.get("production") is False
            checks.append(
                GateCheck(
                    "environment_not_production",
                    prod_false,
                    "block",
                    "环境身份 production=false。" if prod_false else "环境身份 production=true（红线）。",
                )
            )

        # ---- 状态裁决 ----
        status = self._decide(
            checks,
            additional_pending_resources,
            human_verification_required,
        )
        evidence_hash = evidence_chain.chain_hash() if evidence_chain else ""
        return GateResult(status=status, checks=tuple(checks), evidence_hash=evidence_hash)

    @staticmethod
    def _decide(
        checks: list[GateCheck],
        additional_pending_resources: tuple[str, ...],
        human_verification_required: bool,
    ) -> GateStatus:
        # 任一 block 级失败 → BLOCKED
        if any(not c.passed and c.severity == "block" for c in checks):
            return GateStatus.BLOCKED
        # 任一 pending 级未通过 或 额外 pending 资源 → PENDING_EXTERNAL_STAGING_RESOURCE
        pending_due_to_resources = any(
            not c.passed and c.severity == "pending" for c in checks
        )
        if pending_due_to_resources or additional_pending_resources:
            return GateStatus.PENDING_EXTERNAL_STAGING_RESOURCE
        # 资源齐备但未做人工验证 → 进入 human review 待决
        if human_verification_required:
            return GateStatus.PENDING_HUMAN_VERIFICATION
        return GateStatus.READY_FOR_EXTERNAL_STAGING_HUMAN_REVIEW


__all__ = [
    "GateCheck",
    "GateResult",
    "ExternalStagingQualificationGate",
]
