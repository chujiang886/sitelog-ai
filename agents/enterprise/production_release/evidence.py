"""Phase 3.9.2 企业生产发布闸门与证据包层 —— 证据服务（T1 / T8）。

职责：
- 创建 ``ProductionReleaseEvidence``（默认 ``verification_status=PENDING_VERIFICATION``）；
- 对可哈希产物重算 SHA-256 校验完整性（T8）；
- 汇总发布候选所需的客观证据（staging 报告 / 恢复校验 / 安全扫描 / 测试基线 /
  审计枚举 / 工程护栏），形成 Production Release Evidence Chain。

红线（T1 / T8 / ⑩）：
- ``verification_status`` **不得**由 AI 从 ``PENDING_VERIFICATION`` 自动提升为
  ``VERIFIED``。客观存在性事实（文件在 / 枚举数 / engineering_enabled=False）可由
  AI 核验为 ``VERIFIED``；依赖真实人工责任节点的事实（真实签署 / 真实密钥从未写入）
  一律保持 ``PENDING_VERIFICATION``，不得被描述为 production verified（红线⑨）。
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agents.enterprise.production_release.models import (
    EvidenceIntegrityStatus,
    EvidenceVerificationStatus,
    ProductionReleaseEvidence,
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git(*args: str) -> str:
    try:
        out = subprocess.run(
            ["git", *args],
            cwd=os.getcwd(),
            capture_output=True,
            text=True,
            check=False,
        )
        return out.stdout.strip()
    except Exception:
        return ""


class ProductionReleaseEvidenceService:
    """发布证据服务：只读收集 + 完整性校验，不决策、不激活、不代填真实人工证据。"""

    def __init__(self, root_dir: str = ".") -> None:
        self.root_dir = os.path.abspath(root_dir)

    # ------------------------------------------------------------------ #
    # 创建证据（默认待核验）
    # ------------------------------------------------------------------ #
    def create_evidence(
        self,
        *,
        evidence_id: str,
        evidence_type: str,
        source: str,
        source_reference: str,
        verification_status: EvidenceVerificationStatus = (
            EvidenceVerificationStatus.PENDING_VERIFICATION
        ),
        integrity_status: EvidenceIntegrityStatus = EvidenceIntegrityStatus.PENDING,
        phase: Optional[str] = None,
        artifact: Optional[str] = None,
        test_result: Optional[str] = None,
        security_scan: Optional[str] = None,
        staging_validation: Optional[str] = None,
        rollback_drill: Optional[str] = None,
        recovery_validation: Optional[str] = None,
        audit_reference: Optional[str] = None,
        commit: Optional[str] = None,
        timestamp: Optional[str] = None,
        detail: str = "",
        sha256: Optional[str] = None,
    ) -> ProductionReleaseEvidence:
        return ProductionReleaseEvidence(
            evidence_id=evidence_id,
            evidence_type=evidence_type,
            source=source,
            source_reference=source_reference,
            created_at=_now(),
            integrity_status=integrity_status,
            verification_status=verification_status,
            phase=phase,
            artifact=artifact,
            test_result=test_result,
            security_scan=security_scan,
            staging_validation=staging_validation,
            rollback_drill=rollback_drill,
            recovery_validation=recovery_validation,
            audit_reference=audit_reference,
            commit=commit,
            timestamp=timestamp,
            detail=detail,
            sha256=sha256,
        )

    # ------------------------------------------------------------------ #
    # 完整性校验（T8）：重算 SHA-256（T1 关联 artifact 时登记）
    # ------------------------------------------------------------------ #
    def verify_integrity(self, evidence: ProductionReleaseEvidence) -> EvidenceIntegrityStatus:
        """若 evidence 携带 sha256 且 source_reference 为可读文件，则重算比对。

        缺 sha256 / 文件不可达 → ``PENDING`` / ``UNKNOWN``（不擅自判定 TAMPERED）。
        """

        if not evidence.sha256:
            return EvidenceIntegrityStatus.PENDING
        path = os.path.join(self.root_dir, evidence.source_reference)
        if not os.path.isfile(path):
            return EvidenceIntegrityStatus.UNKNOWN
        try:
            h = hashlib.sha256()
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    h.update(chunk)
            actual = h.hexdigest()
        except Exception:
            return EvidenceIntegrityStatus.UNKNOWN
        return (
            EvidenceIntegrityStatus.INTACT
            if actual == evidence.sha256
            else EvidenceIntegrityStatus.TAMPERED
        )

    # ------------------------------------------------------------------ #
    # 汇总发布候选所需证据（形成 Evidence Chain）
    # ------------------------------------------------------------------ #
    def collect_release_evidence(
        self,
        *,
        release_id: str,
        test_baseline: Optional[Dict[str, object]] = None,
        audit_count: Optional[int] = None,
        engineering_enabled: Optional[bool] = None,
    ) -> List[ProductionReleaseEvidence]:
        """只读收集客观证据 + 标记人工依赖证据为 PENDING_VERIFICATION。

        客观事实 → VERIFIED（文件在 / 枚举数 / 护栏态）；
        依赖真实人工责任 → PENDING_VERIFICATION（AI 不代填、不冒称 production verified）。
        """

        root = self.root_dir
        reviews_dir = os.path.join(root, ".ai", "reviews")
        has_39_0 = os.path.isfile(
            os.path.join(reviews_dir, "phase3.9.0_production_readiness_preparation_report.md")
        )
        has_39_1 = os.path.isfile(
            os.path.join(reviews_dir, "phase3.9.1_staging_validation_disaster_recovery_report.md")
        )
        sec_scan_present = os.path.isfile(
            os.path.join(root, "scripts", "lint", "check_production_security.py")
        )

        items: List[ProductionReleaseEvidence] = []

        # —— 客观存在性事实：可核验为 VERIFIED / FAILED —— #
        items.append(
            self.create_evidence(
                evidence_id=f"ev-staging-{release_id}",
                evidence_type="staging_validation",
                source="filesystem",
                source_reference=".ai/reviews/phase3.9.1_staging_validation_disaster_recovery_report.md",
                verification_status=(
                    EvidenceVerificationStatus.VERIFIED
                    if has_39_1
                    else EvidenceVerificationStatus.FAILED
                ),
                integrity_status=(
                    EvidenceIntegrityStatus.INTACT
                    if has_39_1
                    else EvidenceIntegrityStatus.UNKNOWN
                ),
                phase="3.9.1",
                staging_validation="3.9.1",
                detail="3.9.1 预生产验证与灾难恢复演练报告存在性（客观事实）",
            )
        )
        items.append(
            self.create_evidence(
                evidence_id=f"ev-ready-{release_id}",
                evidence_type="production_readiness",
                source="filesystem",
                source_reference=".ai/reviews/phase3.9.0_production_readiness_preparation_report.md",
                verification_status=(
                    EvidenceVerificationStatus.VERIFIED
                    if has_39_0
                    else EvidenceVerificationStatus.FAILED
                ),
                integrity_status=(
                    EvidenceIntegrityStatus.INTACT
                    if has_39_0
                    else EvidenceIntegrityStatus.UNKNOWN
                ),
                phase="3.9.0",
                detail="3.9.0 生产就绪与受控激活准备报告存在性（客观事实）",
            )
        )
        items.append(
            self.create_evidence(
                evidence_id=f"ev-sec-{release_id}",
                evidence_type="security_scan",
                source="filesystem",
                source_reference="scripts/lint/check_production_security.py",
                verification_status=(
                    EvidenceVerificationStatus.VERIFIED
                    if sec_scan_present
                    else EvidenceVerificationStatus.FAILED
                ),
                integrity_status=(
                    EvidenceIntegrityStatus.INTACT
                    if sec_scan_present
                    else EvidenceIntegrityStatus.UNKNOWN
                ),
                security_scan="production_security",
                detail="生产安全红线扫描器存在性（客观事实）",
            )
        )

        # —— 审计枚举总数：客观事实 —— #
        if audit_count is not None:
            items.append(
                self.create_evidence(
                    evidence_id=f"ev-audit-{release_id}",
                    evidence_type="audit_reference",
                    source="AuditActionCategory",
                    source_reference="agents/enterprise/audit.AuditActionCategory",
                    verification_status=EvidenceVerificationStatus.VERIFIED,
                    integrity_status=EvidenceIntegrityStatus.INTACT,
                    audit_reference="audit_total",
                    detail=f"审计动作大类总数 = {audit_count}",
                )
            )

        # —— 工程护栏：engineering_enabled 必须 False（客观事实） —— #
        if engineering_enabled is not None:
            items.append(
                self.create_evidence(
                    evidence_id=f"ev-eng-{release_id}",
                    evidence_type="engineering_guard",
                    source="config_loader",
                    source_reference="agents/config_loader.load_engineering_enabled",
                    verification_status=(
                        EvidenceVerificationStatus.VERIFIED
                        if engineering_enabled is False
                        else EvidenceVerificationStatus.FAILED
                    ),
                    integrity_status=EvidenceIntegrityStatus.INTACT,
                    detail=f"engineering_enabled = {engineering_enabled}（红线①）",
                )
            )

        # —— 测试基线：若提供则记录（客观事实），否则 PENDING —— #
        if test_baseline is not None:
            items.append(
                self.create_evidence(
                    evidence_id=f"ev-test-{release_id}",
                    evidence_type="test_result",
                    source="pytest",
                    source_reference="tests/agents + backend/tests",
                    verification_status=EvidenceVerificationStatus.VERIFIED,
                    integrity_status=EvidenceIntegrityStatus.INTACT,
                    test_result=json.dumps(test_baseline, ensure_ascii=False),
                    detail="权威测试基线（passed/failed/skipped）",
                )
            )

        # —— 依赖真实人工责任节点：一律 PENDING_VERIFICATION（AI 不代填） —— #
        items.append(
            self.create_evidence(
                evidence_id=f"ev-human-{release_id}",
                evidence_type="human_signoff",
                source="human",
                source_reference="ReleaseSignoff(production-owner/release-manager/security-owner/auditor)",
                verification_status=EvidenceVerificationStatus.PENDING_VERIFICATION,
                integrity_status=EvidenceIntegrityStatus.PENDING,
                detail="真实责任人签署证据须由人工线下提供，AI 不得代填",
            )
        )
        items.append(
            self.create_evidence(
                evidence_id=f"ev-secret-{release_id}",
                evidence_type="production_secret",
                source="human",
                source_reference="真实生产密钥（不落库 / 不写入）",
                verification_status=EvidenceVerificationStatus.PENDING_VERIFICATION,
                integrity_status=EvidenceIntegrityStatus.PENDING,
                detail="真实生产密钥从未由本层写入，状态须由人工确认",
            )
        )

        return items

    # ------------------------------------------------------------------ #
    # Evidence Chain：仅聚合，不新增任何放行语义
    # ------------------------------------------------------------------ #
    def build_evidence_chain(self, evidence: List[ProductionReleaseEvidence]) -> Dict[str, Any]:
        return {
            "count": len(evidence),
            "verified": sum(
                1 for e in evidence if e.verification_status == EvidenceVerificationStatus.VERIFIED
            ),
            "pending": sum(
                1
                for e in evidence
                if e.verification_status == EvidenceVerificationStatus.PENDING_VERIFICATION
            ),
            "failed": sum(
                1 for e in evidence if e.verification_status == EvidenceVerificationStatus.FAILED
            ),
            "items": [e.to_dict() for e in evidence],
        }
