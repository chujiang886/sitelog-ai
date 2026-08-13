"""Phase 3.9.2 企业生产发布闸门与证据包层（包入口）。

本包是**纯闸门 / 证据包 / 候选 / 清单 / 回滚引用 / RC 冻结**层，对外只暴露：

- 模型：``ProductionReleaseEvidence``（T1）/ ``ProductionReleaseCandidate``（T2）/
  ``ProductionReleaseGateResult``（T3）/ ``ReleaseSignoff``（T4）/
  ``ReleaseDecisionDraft``（T5）/ ``ReleasePackageManifest``（T6）/
  ``ReleaseRollbackReference``（T7）；
- RC 冻结模型：``ReleaseCandidate``（T11）/ ``RCFreezeComponent`` / ``RCFreezeStatus`` /
  ``RCFreezeManifest`` / ``FreezeCheckResult``；
- 服务：``ProductionReleaseEvidenceService``（T1/T8）/ ``ProductionReleaseGate``（T3）/
  ``ReleasePackageBuilder``（T6/T7）/ ``ProductionReleaseService``（T1–T7/T11 编排）/
  ``ReleaseFreezeChecker``（T11）；
- 结构级禁名集：``_PRODUCTION_RELEASE_FORBIDDEN``（供测试与审计取证）。

本包**不导出**任何真实部署 / 真实激活 / 真实数据覆盖 / 真实密钥写入 / 真实授权 /
代生产负责人签署 / 宣布生产 GO 的能力——因为它们根本不存在（红线①~⑦/⑧/⑨/⑩）。

Phase 3.9.6 增量分两层，**职责正交、不得互相顶替**：

- **Layer A（仓库派生的就绪档案，``activation_readiness``）**：从仓库/阶段产物出发，
  汇总 3.9.0–3.9.5 已有证据、四角色签署要求、SoD、阻断器、pending 登记、证据时效、
  工程激活契约与预激活质量门禁。数据来源是**代码仓库自身**，回答的是
  「本仓库当前客观上处于什么就绪前置态」。
- **Layer B（人工提交的证据接收链，``activation_intake`` → ``human_signoff`` →
  ``intake_service`` → ``review_package`` → ``final_decision``）**：从**真实人工提交**
  出发，接收证据、登记签署、生成供人裁决的材料包、承载真实人工最终裁决。数据来源是
  **真实 USER 的行为**，回答的是「人到底交了什么、签了什么、拍了什么板」。

两层都**只**产出事实与就绪前置态，任何一层都不得产出 ``APPROVED`` / ``GO`` /
``PRODUCTION_READY`` / ``engineering_approved``；Layer A 不能替 Layer B「视为已签署」，
Layer B 也不能用人工提交去覆盖 Layer A 的客观仓库事实。
"""

from agents.enterprise.production_release.forbidden import (
    _PRODUCTION_RELEASE_EXTRA_FORBIDDEN,
    _PRODUCTION_RELEASE_FORBIDDEN,
    PRODUCTION_RELEASE_FORBIDDEN_COUNT,
)
from agents.enterprise.production_release.gate import ProductionReleaseGate
from agents.enterprise.production_release.models import (
    EvidenceIntegrityStatus,
    EvidenceVerificationStatus,
    ProductionReleaseCandidate,
    ProductionReleaseEvidence,
    ProductionReleaseGateResult,
    ReleaseCandidateStatus,
    ReleaseDecisionDraft,
    ReleaseDecisionDraftStatus,
    ReleaseGateStatus,
    ReleasePackageManifest,
    ReleaseRollbackReference,
    ReleaseSignoff,
    SignoffRole,
    SignoffDecision,
)
from agents.enterprise.production_release.release_candidate import (
    RCFreezeComponent,
    RCFreezeStatus,
    ReleaseCandidate,
    create_release_candidate,
)
from agents.enterprise.production_release.freeze_manifest import (
    RCFreezeManifest,
    generate_rc_freeze_manifest,
)
from agents.enterprise.production_release.freeze_checker import (
    FreezeCheckResult,
    ReleaseFreezeChecker,
)
from agents.enterprise.production_release.activation_evidence import (
    ActivationEvidenceBundle,
    REQUIRED_SIGNOFF_ROLES,
    build_activation_evidence_bundle,
)
from agents.enterprise.production_release.activation_gate import (
    ControlledActivationGate,
    ControlledActivationGateResult,
    ControlledActivationGateStatus,
)
from agents.enterprise.production_release.human_approval import (
    HumanActivationApproval,
    HumanActivationApprovalService,
    HumanActivationApprovalStatus,
)
from agents.enterprise.production_release.freeze_forbidden import (
    FREEZE_ACTIVATION_FORBIDDEN_COUNT,
    _FREEZE_ACTIVATION_FORBIDDEN,
)
from agents.enterprise.production_release.activation_readiness import (  # Layer A
    ACTIVATION_READINESS_EXTRA_FORBIDDEN_COUNT,
    ACTIVATION_READINESS_FORBIDDEN_COUNT,
    ActivationBlocker,
    ActivationEvidenceBundleV2,
    ActivationEvidenceFreshness,
    ActivationEvidenceItem,
    ActivationReadinessStatus,
    EngineeringActivationContract,
    EvidenceFreshnessStatus,
    EvidenceScope,
    HumanReviewStatus,
    PreActivationQualityGate,
    ProductionActivationReadinessGate,
    ProductionActivationReadinessGateResult,
    ProductionActivationSignoffRequirement,
    ProductionHumanReviewPacket,
    ProductionPendingVerificationItem,
    SoDValidationResult,
    SoDValidator,
    assemble_activation_readiness_dossier,
    build_default_activation_blockers,
    build_default_activation_evidence_bundle_v2,
    build_default_pending_verification_registry,
    build_default_signoff_requirements,
)
from agents.enterprise.production_release.activation_intake import (  # Layer B
    AI_ALLOWED_SUBMISSION_STATUSES,
    HUMAN_ONLY_SUBMISSION_STATUSES,
    REQUIRED_ACTIVATION_EVIDENCE_TYPES,
    REQUIRED_SUBMITTER_KIND,
    ActivationEvidenceIntakeError,
    ActivationEvidenceSubmission,
    ActivationEvidenceSubmissionStatus,
    ChainOfCustodyEvent,
    CustodyEventKind,
    EvidenceProvenance,
    build_activation_evidence_submission,
    build_chain_of_custody,
    build_evidence_provenance,
)
from agents.enterprise.production_release.human_signoff import (  # Layer B
    REQUIRED_SIGNOFF_ACTOR_KIND,
    HumanSignoffError,
    HumanSignoffRecord,
    HumanSignoffRegistry,
    HumanSignoffRegistrySnapshot,
    build_human_signoff_record,
)
from agents.enterprise.production_release.intake_forbidden import (
    ACTIVATION_INTAKE_EXTRA_FORBIDDEN_COUNT,
    ACTIVATION_INTAKE_FORBIDDEN_COUNT,
    _ACTIVATION_INTAKE_EXTRA_FORBIDDEN,
    _ACTIVATION_INTAKE_FORBIDDEN,
)
from agents.enterprise.production_release.intake_service import (  # Layer B
    ActivationEvidenceIntakeService,
    ActivationIntakeServiceError,
    EvidenceIntakeSummary,
)
from agents.enterprise.production_release.review_package import (  # Layer B
    ALLOWED_REVIEW_READINESS,
    FORBIDDEN_CONCLUSION_TOKENS,
    ActivationReviewPackageError,
    FinalActivationReviewPackage,
    ReviewPackageReadiness,
    build_final_activation_review_package,
)
from agents.enterprise.production_release.final_decision import (  # Layer B
    REQUIRED_DECIDER_KIND,
    ActivationExecutionState,
    FinalDecisionLedgerSnapshot,
    FinalDecisionOutcome,
    FinalHumanActivationDecision,
    FinalHumanDecisionError,
    FinalHumanDecisionLedger,
    build_final_human_activation_decision,
    compute_review_package_digest,
)
from agents.enterprise.production_release.evidence import ProductionReleaseEvidenceService
from agents.enterprise.production_release.package import ReleasePackageBuilder
from agents.enterprise.production_release.service import (
    ProductionReleaseError,
    ProductionReleaseService,
)

__all__ = [
    # 模型
    "EvidenceVerificationStatus",
    "EvidenceIntegrityStatus",
    "ProductionReleaseEvidence",
    "ProductionReleaseCandidate",
    "ReleaseCandidateStatus",
    "ProductionReleaseGateResult",
    "ReleaseGateStatus",
    "ReleaseSignoff",
    "SignoffRole",
    "SignoffDecision",
    "ReleaseDecisionDraft",
    "ReleaseDecisionDraftStatus",
    "ReleasePackageManifest",
    "ReleaseRollbackReference",
    # RC 冻结模型
    "RCFreezeStatus",
    "RCFreezeComponent",
    "ReleaseCandidate",
    "create_release_candidate",
    "RCFreezeManifest",
    "generate_rc_freeze_manifest",
    "FreezeCheckResult",
    "ReleaseFreezeChecker",
    # 受控激活证据包 / 闸门 / 人工批准契约
    "ActivationEvidenceBundle",
    "REQUIRED_SIGNOFF_ROLES",
    "build_activation_evidence_bundle",
    "ControlledActivationGate",
    "ControlledActivationGateResult",
    "ControlledActivationGateStatus",
    "HumanActivationApproval",
    "HumanActivationApprovalService",
    "HumanActivationApprovalStatus",
    # Phase 3.9.6 Layer A：仓库派生的激活就绪档案
    "EvidenceScope",
    "ActivationReadinessStatus",
    "HumanReviewStatus",
    "EvidenceFreshnessStatus",
    "ActivationEvidenceItem",
    "ActivationEvidenceBundleV2",
    "build_default_activation_evidence_bundle_v2",
    "ProductionActivationSignoffRequirement",
    "build_default_signoff_requirements",
    "SoDValidator",
    "SoDValidationResult",
    "ActivationBlocker",
    "build_default_activation_blockers",
    "ProductionPendingVerificationItem",
    "build_default_pending_verification_registry",
    "ActivationEvidenceFreshness",
    "EngineeringActivationContract",
    "ProductionActivationReadinessGate",
    "ProductionActivationReadinessGateResult",
    "ProductionHumanReviewPacket",
    "PreActivationQualityGate",
    "assemble_activation_readiness_dossier",
    "ACTIVATION_READINESS_EXTRA_FORBIDDEN_COUNT",
    "ACTIVATION_READINESS_FORBIDDEN_COUNT",
    # Phase 3.9.6 Layer B：人工提交的证据接收 → 签署 → 材料包 → 人工裁决
    "ActivationEvidenceIntakeError",
    "REQUIRED_SUBMITTER_KIND",
    "REQUIRED_ACTIVATION_EVIDENCE_TYPES",
    "CustodyEventKind",
    "ChainOfCustodyEvent",
    "EvidenceProvenance",
    "ActivationEvidenceSubmissionStatus",
    "AI_ALLOWED_SUBMISSION_STATUSES",
    "HUMAN_ONLY_SUBMISSION_STATUSES",
    "ActivationEvidenceSubmission",
    "build_chain_of_custody",
    "build_evidence_provenance",
    "build_activation_evidence_submission",
    "HumanSignoffError",
    "REQUIRED_SIGNOFF_ACTOR_KIND",
    "HumanSignoffRecord",
    "build_human_signoff_record",
    "HumanSignoffRegistry",
    "HumanSignoffRegistrySnapshot",
    "ActivationIntakeServiceError",
    "EvidenceIntakeSummary",
    "ActivationEvidenceIntakeService",
    "ActivationReviewPackageError",
    "ReviewPackageReadiness",
    "ALLOWED_REVIEW_READINESS",
    "FORBIDDEN_CONCLUSION_TOKENS",
    "FinalActivationReviewPackage",
    "build_final_activation_review_package",
    "FinalHumanDecisionError",
    "REQUIRED_DECIDER_KIND",
    "FinalDecisionOutcome",
    "ActivationExecutionState",
    "compute_review_package_digest",
    "FinalHumanActivationDecision",
    "build_final_human_activation_decision",
    "FinalDecisionLedgerSnapshot",
    "FinalHumanDecisionLedger",
    # 红线取证
    "_ACTIVATION_INTAKE_EXTRA_FORBIDDEN",
    "_ACTIVATION_INTAKE_FORBIDDEN",
    "ACTIVATION_INTAKE_EXTRA_FORBIDDEN_COUNT",
    "ACTIVATION_INTAKE_FORBIDDEN_COUNT",
    "_FREEZE_ACTIVATION_FORBIDDEN",
    "FREEZE_ACTIVATION_FORBIDDEN_COUNT",
    # 服务
    "ProductionReleaseEvidenceService",
    "ProductionReleaseGate",
    "ReleasePackageBuilder",
    "ProductionReleaseService",
    "ProductionReleaseError",
    # 红线取证
    "_PRODUCTION_RELEASE_EXTRA_FORBIDDEN",
    "_PRODUCTION_RELEASE_FORBIDDEN",
    "PRODUCTION_RELEASE_FORBIDDEN_COUNT",
]
