"""Phase 3.9.2 企业生产发布闸门与证据包层 —— 发布闸门（T3）。

``ProductionReleaseGate.evaluate`` 评估 13 项闸门条件，产出
``READY_FOR_HUMAN_REVIEW`` / ``BLOCKED`` / ``PENDING_VERIFICATION`` 三态之一。

红线（T3 / ② / ③ / ⑩）：
- **禁止** ``APPROVED`` / ``AUTO_APPROVED`` / ``ENGINEERING_APPROVED`` 作为 AI 终态。
- 即便全部客观检查通过，只要真实人工签署（human_signoff）仍 PENDING，闸门也只能
  返回 ``READY_FOR_HUMAN_REVIEW``；最终 GO 只能由真实 ``ReleaseSignoff`` 组合决定。
"""

from __future__ import annotations

from typing import Any, Dict, List

from agents.enterprise.production_release.models import (
    EvidenceVerificationStatus,
    ProductionReleaseCandidate,
    ProductionReleaseGateResult,
    ReleaseGateStatus,
)


class ProductionReleaseGate:
    """发布闸门：诚实评估 13 项条件，但只产出三类人工前置终态。"""

    # 13 项闸门键（与收口报告 / 测试一一对应）
    CHECK_KEYS = (
        "git_workspace_integrity",
        "commit_sha_exists",
        "full_test_results_green",
        "production_security_scanner",
        "identity_security_scanner",
        "governance_quality_gate",
        "staging_validation",
        "rollback_drill",
        "recovery_validation",
        "database_migration_status",
        "configuration_baseline",
        "deployment_documentation",
        "evidence_completeness",
    )

    def evaluate(
        self,
        *,
        candidate: ProductionReleaseCandidate,
        evidence_chain: Dict[str, Any],
        scan: Dict[str, bool],
    ) -> ProductionReleaseGateResult:
        """``scan`` 携带各外部检查布尔值；``evidence_chain`` 由 EvidenceService 产出。

        返回状态：
        - 任一检查为 False → ``BLOCKED``；
        - 全部通过但 human_signoff 仍 PENDING → ``PENDING_VERIFICATION``；
        - 全部通过且 human_signoff 已 VERIFIED 由调用方另判（本 AI 路径恒不返回 APPROVED）。
        """

        checks: Dict[str, bool] = {}

        # —— 1-2：Git 工作区完整性 / Commit SHA 存在（由 scan 提供） —— #
        checks["git_workspace_integrity"] = bool(scan.get("git_workspace_integrity", False))
        checks["commit_sha_exists"] = bool(scan.get("commit_sha_exists", False))

        # —— 3-6：全量测试 / 生产安全 / 身份安全 / 治理质量门 —— #
        checks["full_test_results_green"] = bool(scan.get("full_test_results_green", False))
        checks["production_security_scanner"] = bool(scan.get("production_security_scanner", False))
        checks["identity_security_scanner"] = bool(scan.get("identity_security_scanner", False))
        checks["governance_quality_gate"] = bool(scan.get("governance_quality_gate", False))

        # —— 7-9：预生产验证 / 回滚演练 / 恢复校验（证据链客观事实） —— #
        items = evidence_chain.get("items", [])
        by_type = {e["evidence_type"]: e for e in items}

        def _ok(ev_type: str) -> bool:
            ev = by_type.get(ev_type)
            if ev is None:
                return False
            return ev["verification_status"] in ("verified", "pending_verification")

        checks["staging_validation"] = _ok("staging_validation")
        checks["rollback_drill"] = _ok("rollback_drill") or bool(
            scan.get("rollback_drill", False)
        )
        checks["recovery_validation"] = _ok("recovery_validation") or bool(
            scan.get("recovery_validation", False)
        )

        # —— 10-12：数据库迁移 / 配置基线 / 部署文档（由 scan 提供） —— #
        checks["database_migration_status"] = bool(scan.get("database_migration_status", False))
        checks["configuration_baseline"] = bool(scan.get("configuration_baseline", False))
        checks["deployment_documentation"] = bool(scan.get("deployment_documentation", False))

        # —— 13：证据完整性（无 FAILED 证据，且至少有待核验清单） —— #
        failed = evidence_chain.get("failed", 0)
        pending = evidence_chain.get("pending", 0)
        checks["evidence_completeness"] = (failed == 0) and (evidence_chain.get("count", 0) > 0)

        missing: List[str] = [k for k, v in checks.items() if not v]

        # —— 状态判定（fail-closed，永不 APPROVED） —— #
        if missing:
            status = ReleaseGateStatus.BLOCKED
        elif pending > 0:
            # 客观检查全过，但仍有待人工核验项（含 human_signoff）→ 待核验
            status = ReleaseGateStatus.PENDING_VERIFICATION
        else:
            # 全过且无 PENDING：仍只给人工前置态，不直接放行
            status = ReleaseGateStatus.READY_FOR_HUMAN_REVIEW

        return ProductionReleaseGateResult(
            status=status,
            checks=checks,
            missing=missing,
        )
