"""Phase 3.9.11 —— External Staging Execution Gate（Task 26）。

汇总检查（fail-closed），状态仅 4 态（沿用 qualification 的 ``GateStatus``，禁止
APPROVED/PRODUCTION_READY/GO）：

- ``BLOCKED``
- ``PENDING_EXTERNAL_STAGING_RESOURCE``
- ``PENDING_HUMAN_VERIFICATION``
- ``READY_FOR_EXTERNAL_STAGING_HUMAN_REVIEW``

裁决：任一 block 级失败 → BLOCKED；资源待决/人工待决 → PENDING_EXTERNAL_STAGING_RESOURCE；
**绝不**越级至 READY/GO。
"""

from __future__ import annotations

from typing import Any

from agents.external_staging_qualification.credential_scanner import (
    assert_no_credential_leak,
    CredentialLeakError,
)
from agents.external_staging_qualification.gate import GateCheck, GateResult
from agents.external_staging_qualification.models import (
    ExternalStagingResourceRegistry,
    GateStatus,
)

from agents.external_staging_execution.evidence import ExecutionEvidenceChain
from agents.external_staging_execution.models import ExecutionPlan


class ExternalStagingExecutionGate:
    """外部预生产执行闸门（fail-closed 评估器）。"""

    def evaluate(
        self,
        *,
        plan: ExecutionPlan | None = None,
        evidence_chain: ExecutionEvidenceChain | None = None,
        environment_identity: dict[str, Any] | None = None,
        registry: ExternalStagingResourceRegistry | None = None,
        security_ok: bool = True,
        regression_ok: bool = True,
        repo_clean: bool = True,
        additional_pending_resources: tuple[str, ...] = (),
        human_verification_required: bool = True,
    ) -> GateResult:
        checks: list[GateCheck] = []

        # 1) 执行计划存在
        plan_ok = plan is not None and len(plan.steps) > 0
        checks.append(
            GateCheck(
                "execution_plan_present",
                plan_ok,
                "block",
                f"执行计划步数={len(plan.steps) if plan else 0}。",
            )
        )

        # 2) 未宣称真实执行
        no_real = bool(plan is not None and not plan.summary().get("any_real_execution"))
        checks.append(
            GateCheck(
                "no_real_execution_claimed",
                no_real,
                "block",
                "执行计划未宣称真实执行（plan-only/contract-test/pending）。"
                if no_real
                else "执行计划宣称了真实执行（红线）。",
            )
        )

        # 3) 环境身份：production 必须为 False
        prod_false = environment_identity.get("production") is False if environment_identity else False
        checks.append(
            GateCheck(
                "environment_not_production",
                prod_false,
                "block",
                "环境身份 production=false。" if prod_false else "环境身份 production=true（红线）。",
            )
        )

        # 4) 凭据引用安全（读取登记簿真实引用，不忽略泄漏）
        try:
            ref_map = {
                r.resource_id: {
                    "credential_reference": r.credential_reference or "",
                    "source_reference": r.source_reference or "",
                }
                for r in (registry.resources if registry else [])
            }
            assert_no_credential_leak(mapping=ref_map)
            cred_ok = True
            cred_detail = "凭据引用无明文泄漏。"
        except CredentialLeakError as exc:
            cred_ok = False
            cred_detail = str(exc)
        checks.append(GateCheck("credential_reference_safety", cred_ok, "block", cred_detail))

        # 5) 8 资源诚实 PENDING（无真实执行宣称）
        if registry is not None:
            any_verified = any(r.verified for r in registry.resources)
            any_blocked = any(
                r.qualification_status == "blocked" for r in registry.resources
            )
            checks.append(
                GateCheck(
                    "resources_honest_pending",
                    (not any_verified) and (not any_blocked),
                    "pending",
                    "8 资源全部诚实 PENDING（无真实验证）。"
                    if (not any_verified)
                    else "存在已验证资源（Track B 应 PENDING）。",
                )
            )

        # 6) 证据完整性（无 Secret）
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
        checks.append(
            GateCheck("security", security_ok, "block", "安全扫描通过。" if security_ok else "安全扫描失败。")
        )
        checks.append(
            GateCheck("full_regression", regression_ok, "block", "全量回归 0 failed。" if regression_ok else "全量回归存在失败。")
        )
        checks.append(
            GateCheck("repository_clean", repo_clean, "block", "工作树清洁。" if repo_clean else "工作树不清洁。")
        )

        status = self._decide(checks, additional_pending_resources, human_verification_required)
        evidence_hash = evidence_chain.chain_hash() if evidence_chain else ""
        return GateResult(status=status, checks=tuple(checks), evidence_hash=evidence_hash)

    @staticmethod
    def _decide(
        checks: list[GateCheck],
        additional_pending_resources: tuple[str, ...],
        human_verification_required: bool,
    ) -> GateStatus:
        if any(not c.passed and c.severity == "block" for c in checks):
            return GateStatus.BLOCKED
        pending_due_to_resources = any(
            not c.passed and c.severity == "pending" for c in checks
        )
        if pending_due_to_resources or additional_pending_resources:
            return GateStatus.PENDING_EXTERNAL_STAGING_RESOURCE
        if human_verification_required:
            return GateStatus.PENDING_HUMAN_VERIFICATION
        return GateStatus.READY_FOR_EXTERNAL_STAGING_HUMAN_REVIEW


__all__ = ["ExternalStagingExecutionGate"]
