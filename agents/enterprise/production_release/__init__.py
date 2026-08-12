"""Phase 3.9.2 企业生产发布闸门与证据包层（包入口）。

本包是**纯闸门 / 证据包 / 候选 / 清单 / 回滚引用**层，对外只暴露：

- 模型：``ProductionReleaseEvidence``（T1）/ ``ProductionReleaseCandidate``（T2）/
  ``ProductionReleaseGateResult``（T3）/ ``ReleaseSignoff``（T4）/
  ``ReleaseDecisionDraft``（T5）/ ``ReleasePackageManifest``（T6）/
  ``ReleaseRollbackReference``（T7）；
- 服务：``ProductionReleaseEvidenceService``（T1/T8）/ ``ProductionReleaseGate``（T3）/
  ``ReleasePackageBuilder``（T6/T7）/ ``ProductionReleaseService``（T1–T7 编排）；
- 结构级禁名集：``_PRODUCTION_RELEASE_FORBIDDEN``（供测试与审计取证）。

本包**不导出**任何真实部署 / 真实激活 / 真实数据覆盖 / 真实密钥写入 / 真实授权 /
代生产负责人签署 / 宣布生产 GO 的能力——因为它们根本不存在（红线①~⑦/⑧/⑨/⑩）。
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
    SignoffDecision,
    SignoffRole,
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
