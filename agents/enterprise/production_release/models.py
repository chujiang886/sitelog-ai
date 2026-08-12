"""Phase 3.9.2 企业生产发布闸门与证据包层 —— 数据模型（T1–T7）。

全部为**只读闸门 / 证据包 / 候选 / 清单 / 回滚引用结构**：本模块不持有任何生产状态，
不写入任何密钥，不执行任何真实激活 / 真实授权 / 真实数据覆盖。所有 ``approved`` /
``released`` / ``activated`` 类放行字段恒为 ``False`` 或处于 ``*_FOR_HUMAN_REVIEW`` /
``READY_FOR_HUMAN_REVIEW`` 状态，最终放行只能源于真实人工（production-owner /
release-manager / security-owner / auditor）线下签署 ``ReleaseSignoff``。

本层**新增 4 个审计动作大类**（release_candidate_created / release_gate_evaluated /
release_signoff_recorded / release_manifest_generated），审计总数由 79 → 83；其余
可审计动作复用既有 ``record_user_action``（actor_kind 恒 USER）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


# --------------------------------------------------------------------------- #
# 枚举                                                                          #
# --------------------------------------------------------------------------- #
class EvidenceVerificationStatus(str, Enum):
    """证据核验状态（T1）。

    注意：AI **不得**把 ``PENDING_VERIFICATION`` 自动提升为 ``VERIFIED``
    （红线⑩ / 收口条件红线）。缺失真实人工核验的证据一律保持 ``PENDING_VERIFICATION``。
    """

    VERIFIED = "verified"
    PENDING_VERIFICATION = "pending_verification"
    FAILED = "failed"


class EvidenceIntegrityStatus(str, Enum):
    """证据完整性状态（T1 / T8）。

    ``INTACT``：完整性校验通过（SHA-256 / append-only / 追踪关联齐备）；
    ``PENDING``：完整性尚未核验（缺真实来源）；
    ``TAMPERED``：完整性校验失败（哈希不匹配 / 记录被改）；
    ``UNKNOWN``：来源不可达，无法核验。
    """

    INTACT = "intact"
    PENDING = "pending"
    TAMPERED = "tampered"
    UNKNOWN = "unknown"


class ReleaseCandidateStatus(str, Enum):
    """发布候选状态（T2）。

    AI 只能构造 ``DRAFT`` / ``GATHERED`` / ``AWAITING_HUMAN_REVIEW`` 三种；
    ``REJECTED_BY_HUMAN`` 与 ``APPROVED_FOR_RELEASE_BY_HUMAN`` 只能由真实人工
    （主理人线下决策 / 签署 ReleaseSignoff）产生，AI 不可进入。
    """

    DRAFT = "draft"
    GATHERED = "gathered"
    AWAITING_HUMAN_REVIEW = "awaiting_human_review"
    REJECTED_BY_HUMAN = "rejected_by_human"
    APPROVED_FOR_RELEASE_BY_HUMAN = "approved_for_release_by_human"


class ReleaseGateStatus(str, Enum):
    """发布闸门状态（T3）。

    AI 只可产出 ``READY_FOR_HUMAN_REVIEW`` / ``BLOCKED`` / ``PENDING_VERIFICATION``；
    ``APPROVED`` / ``AUTO_APPROVED`` / ``ENGINEERING_APPROVED`` **禁止**作为 AI 终态
    （红线②/③/⑩）。
    """

    READY_FOR_HUMAN_REVIEW = "ready_for_human_review"
    BLOCKED = "blocked"
    PENDING_VERIFICATION = "pending_verification"


class SignoffRole(str, Enum):
    """人工签署角色（T4）。"""

    PRODUCTION_OWNER = "production-owner"
    RELEASE_MANAGER = "release-manager"
    SECURITY_OWNER = "security-owner"
    AUDITOR = "auditor"


class SignoffDecision(str, Enum):
    """人工签署决策（T4）。"""

    GO = "go"
    NO_GO = "no_go"
    NEED_MORE_EVIDENCE = "need_more_evidence"


class ReleaseDecisionDraftStatus(str, Enum):
    """Go/No-Go 草稿状态（T5）。

    AI 只可产出 ``READY_FOR_HUMAN_GO_NO_GO`` / ``BLOCKED`` / ``NEEDS_MORE_EVIDENCE``；
    ``GO_LIVE_APPROVED`` **禁止**作为 AI 生成状态（红线②/⑧/⑩）。
    """

    READY_FOR_HUMAN_GO_NO_GO = "ready_for_human_go_no_go"
    BLOCKED = "blocked"
    NEEDS_MORE_EVIDENCE = "needs_more_evidence"


# --------------------------------------------------------------------------- #
# T1：发布证据                                                                   #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ProductionReleaseEvidence:
    """T1 发布证据：可关联 phase / artifact / test_result / security_scan /
    staging_validation / rollback_drill / recovery_validation / audit_reference /
    commit / timestamp，并携带 integrity_status + verification_status。

    ``verification_status`` 初始由真实来源决定；AI 不得把 ``PENDING_VERIFICATION``
    自动提升为 ``VERIFIED``（红线⑩）。
    """

    evidence_id: str
    evidence_type: str
    source: str
    source_reference: str
    created_at: str
    integrity_status: EvidenceIntegrityStatus = EvidenceIntegrityStatus.PENDING
    verification_status: EvidenceVerificationStatus = (
        EvidenceVerificationStatus.PENDING_VERIFICATION
    )
    # 关联维度（全部可选；用于形成 Production Release Evidence Chain）
    phase: Optional[str] = None
    artifact: Optional[str] = None
    test_result: Optional[str] = None
    security_scan: Optional[str] = None
    staging_validation: Optional[str] = None
    rollback_drill: Optional[str] = None
    recovery_validation: Optional[str] = None
    audit_reference: Optional[str] = None
    commit: Optional[str] = None
    timestamp: Optional[str] = None
    detail: str = ""
    sha256: Optional[str] = None  # 可哈希产物时登记 SHA-256

    def to_dict(self) -> Dict[str, object]:
        return {
            "evidence_id": self.evidence_id,
            "evidence_type": self.evidence_type,
            "source": self.source,
            "source_reference": self.source_reference,
            "created_at": self.created_at,
            "integrity_status": self.integrity_status.value,
            "verification_status": self.verification_status.value,
            "phase": self.phase,
            "artifact": self.artifact,
            "test_result": self.test_result,
            "security_scan": self.security_scan,
            "staging_validation": self.staging_validation,
            "rollback_drill": self.rollback_drill,
            "recovery_validation": self.recovery_validation,
            "audit_reference": self.audit_reference,
            "commit": self.commit,
            "timestamp": self.timestamp,
            "detail": self.detail,
            "sha256": self.sha256,
        }


# --------------------------------------------------------------------------- #
# T2：发布候选                                                                   #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ProductionReleaseCandidate:
    """T2 发布候选：仅描述候选对象，不决策、不激活。

    ``release_approved`` 恒为 ``False``（fail-closed）；``status`` 取值只能由真实人工
    推进到 ``REJECTED_BY_HUMAN`` / ``APPROVED_FOR_RELEASE_BY_HUMAN``，AI 只可造
    ``DRAFT`` / ``GATHERED`` / ``AWAITING_HUMAN_REVIEW``。本模型**不提供**
    ``auto_approve_release`` 能力。
    """

    release_id: str
    version: str
    commit_sha: str
    branch: str
    build_artifacts: List[str] = field(default_factory=list)
    migration_version: Optional[str] = None
    config_baseline: Optional[str] = None
    security_baseline: Optional[str] = None
    test_baseline: Dict[str, object] = field(default_factory=dict)
    rollback_reference: Optional[str] = None
    evidence_ids: List[str] = field(default_factory=list)
    status: ReleaseCandidateStatus = ReleaseCandidateStatus.DRAFT
    release_approved: bool = False  # fail-closed：AI 路径恒 False
    created_at: str = ""
    note: str = (
        "RC_ONLY: 发布候选仅描述放行对象，不激活；最终放行须主理人线下签署 "
        "ReleaseSignoff"
    )

    def to_dict(self) -> Dict[str, object]:
        return {
            "release_id": self.release_id,
            "version": self.version,
            "commit_sha": self.commit_sha,
            "branch": self.branch,
            "build_artifacts": list(self.build_artifacts),
            "migration_version": self.migration_version,
            "config_baseline": self.config_baseline,
            "security_baseline": self.security_baseline,
            "test_baseline": dict(self.test_baseline),
            "rollback_reference": self.rollback_reference,
            "evidence_ids": list(self.evidence_ids),
            "status": self.status.value,
            "release_approved": self.release_approved,
            "created_at": self.created_at,
            "note": self.note,
        }


# --------------------------------------------------------------------------- #
# T3：发布闸门结果                                                               #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ProductionReleaseGateResult:
    """T3 发布闸门评估结果：AI 只产出 READY_FOR_HUMAN_REVIEW / BLOCKED /
    PENDING_VERIFICATION；绝不产出 APPROVED / AUTO_APPROVED / ENGINEERING_APPROVED。
    """

    status: ReleaseGateStatus
    checks: Dict[str, bool] = field(default_factory=dict)
    missing: List[str] = field(default_factory=list)
    note: str = (
        "GATE_ONLY: AI 不直接返回 APPROVED；最终放行须真实 ReleaseSignoff 组合决定"
    )

    def to_dict(self) -> Dict[str, object]:
        return {
            "status": self.status.value,
            "checks": dict(self.checks),
            "missing": list(self.missing),
            "note": self.note,
        }


# --------------------------------------------------------------------------- #
# T4：人工签署                                                                   #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ReleaseSignoff:
    """T4 人工签署契约：只能由真实 USER（production-owner / release-manager /
    security-owner / auditor）创建。

    ``actor_kind`` 必须 ``USER``；AI / SYSTEM 不得构造本实例（服务层 forbidden 名
    ``create_human_signoff`` 已结构拦截）。本阶段（Phase 3.9.2）不得伪造任何实例。
    """

    signoff_id: str
    release_id: str
    actor_id: str
    actor_kind: str  # 必须 "user"
    role: SignoffRole
    decision: SignoffDecision
    reason: str
    timestamp: str
    evidence_snapshot: Dict[str, object] = field(default_factory=dict)
    note: str = "CONTRACT_ONLY: 仅真实责任人可创建；AI 不得代签"

    def to_dict(self) -> Dict[str, object]:
        return {
            "signoff_id": self.signoff_id,
            "release_id": self.release_id,
            "actor_id": self.actor_id,
            "actor_kind": self.actor_kind,
            "role": self.role.value,
            "decision": self.decision.value,
            "reason": self.reason,
            "timestamp": self.timestamp,
            "evidence_snapshot": dict(self.evidence_snapshot),
            "note": self.note,
        }


# --------------------------------------------------------------------------- #
# T5：Go/No-Go 决策草稿                                                          #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ReleaseDecisionDraft:
    """T5 Go/No-Go 决策草稿：只能是草稿。

    AI 可汇总证据摘要 / 通过项 / 阻断项 / pending_verification / 风险项 / 回滚准备情况；
    最终状态必须由真实 ``ReleaseSignoff`` 组合决定。``status`` 只能源于
    ``READY_FOR_HUMAN_GO_NO_GO`` / ``BLOCKED`` / ``NEEDS_MORE_EVIDENCE``；
    ``GO_LIVE_APPROVED`` 禁止作为 AI 生成状态。
    """

    draft_id: str
    release_id: str
    evidence_summary: Dict[str, object] = field(default_factory=dict)
    passed_items: List[str] = field(default_factory=list)
    blocked_items: List[str] = field(default_factory=list)
    pending_verification: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    rollback_readiness: str = "pending_verification"
    status: ReleaseDecisionDraftStatus = ReleaseDecisionDraftStatus.READY_FOR_HUMAN_GO_NO_GO
    generated_at: str = ""
    note: str = (
        "DRAFT_ONLY: AI 生成草稿；最终 GO / NO-GO 只能由真实 ReleaseSignoff 组合决定"
    )

    def to_dict(self) -> Dict[str, object]:
        return {
            "draft_id": self.draft_id,
            "release_id": self.release_id,
            "evidence_summary": dict(self.evidence_summary),
            "passed_items": list(self.passed_items),
            "blocked_items": list(self.blocked_items),
            "pending_verification": list(self.pending_verification),
            "risks": list(self.risks),
            "rollback_readiness": self.rollback_readiness,
            "status": self.status.value,
            "generated_at": self.generated_at,
            "note": self.note,
        }


# --------------------------------------------------------------------------- #
# T6：发布清单清单（Manifest）                                                   #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ReleasePackageManifest:
    """T6 发布包清单：描述产物哈希 / 迁移版本 / 配置基线 / 依赖基线 / 扫描与报告引用。

    可哈希产物使用 SHA-256（``artifact_hashes``）。本清单**只描述**，不执行部署。
    """

    release_version: str
    commit_sha: str
    artifact_hashes: Dict[str, str] = field(default_factory=dict)
    migration_revision: Optional[str] = None
    config_baseline: Optional[str] = None
    dependency_baseline: Optional[str] = None
    security_scan_ref: Optional[str] = None
    test_report_ref: Optional[str] = None
    rollback_version: Optional[str] = None
    documentation_version: Optional[str] = None
    generated_at: str = ""
    note: str = "MANIFEST_ONLY: 描述产物与引用，不执行部署"

    def to_dict(self) -> Dict[str, object]:
        return {
            "release_version": self.release_version,
            "commit_sha": self.commit_sha,
            "artifact_hashes": dict(self.artifact_hashes),
            "migration_revision": self.migration_revision,
            "config_baseline": self.config_baseline,
            "dependency_baseline": self.dependency_baseline,
            "security_scan_ref": self.security_scan_ref,
            "test_report_ref": self.test_report_ref,
            "rollback_version": self.rollback_version,
            "documentation_version": self.documentation_version,
            "generated_at": self.generated_at,
            "note": self.note,
        }


# --------------------------------------------------------------------------- #
# T7：回滚引用                                                                   #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ReleaseRollbackReference:
    """T7 回滚引用：记录 last_known_good 版本 / commit / 数据库修订 / 配置基线 /
    回滚步骤与恢复校验引用。

    本阶段**不真正执行** production rollback；只验证回滚引用是否完整。
    """

    last_known_good_version: str
    last_known_good_commit: str
    database_revision: Optional[str] = None
    config_baseline: Optional[str] = None
    rollback_steps_reference: Optional[str] = None
    recovery_validation_reference: Optional[str] = None
    note: str = "ROLLBACK_REF_ONLY: 仅记录引用，不执行真实回滚"
    verified: bool = False  # 仅验证引用完整性，不执行回滚

    def to_dict(self) -> Dict[str, object]:
        return {
            "last_known_good_version": self.last_known_good_version,
            "last_known_good_commit": self.last_known_good_commit,
            "database_revision": self.database_revision,
            "config_baseline": self.config_baseline,
            "rollback_steps_reference": self.rollback_steps_reference,
            "recovery_validation_reference": self.recovery_validation_reference,
            "verified": self.verified,
            "note": self.note,
        }
