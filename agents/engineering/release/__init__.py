"""Engineering Gray Release Execution Infrastructure（Phase 3.2 Sprint 3.2.5-F）。

首次工程灰度发布的执行基础设施：
- ``approval``：``EngineeringReleaseApproval`` 授权记录（G6 证据，append-only）；
- ``audit``：``release_audit.jsonl`` 发布审计日志（append-only，仅引用）；
- ``gate``：``release_precheck()`` 发布前 G1-G6 门禁；
- ``controller``：``enable`` / ``disable`` / ``rollback`` / ``restore`` 执行核心。

红线总约束：本包任何操作都**不**翻转 ``engineering_enabled``、**不**改
``verified.json``、**不**输出 ``engineering_approved``；真实放量仍须主理人
单独书面授权 + G1-G6 全过。所有写盘均为 append-only 或仅翻转灰度开关。
"""

from __future__ import annotations

from agents.engineering.release.approval import (
    DEFAULT_RELEASE_APPROVAL_PATH,
    EngineeringReleaseApproval,
    append_approval_record,
    find_approval_record,
    is_approval_effective,
    load_approval_records,
)
from agents.engineering.release.audit import (
    DEFAULT_RELEASE_AUDIT_PATH,
    ReleaseAuditRecord,
    append_audit_record,
    load_audit_records,
)
from agents.engineering.release.controller import (
    DEFAULT_OPERATOR,
    ReleaseAction,
    ReleaseOutcome,
    ReleaseResult,
    disable_release,
    enable_release,
    restore_release,
    rollback_release,
)
from agents.engineering.release.gate import release_precheck
from agents.engineering.release.production_checker import (
    ProductionReadinessChecker,
    ProductionReadinessReport,
)
from agents.engineering.release.evidence_bundle import (
    ReleaseEvidenceBundle,
    collect_release_evidence_bundle,
    REQUIRED_INTAKE_EVENTS,
)
from agents.engineering.release.candidate import (
    ReleaseCandidateRecord,
    collect_release_candidate,
    RUNBOOK_VERSION,
)
from agents.engineering.release.readiness import (
    check_e_th_realization,
    check_review_log_chain,
    check_verified_integrity,
    manual_modified_thresholds,
    production_readiness,
    production_readiness_checker,
    validate_release_approval,
)
from agents.engineering.gate.enable_gate import required_audit_events


__all__ = [
    "DEFAULT_RELEASE_APPROVAL_PATH",
    "EngineeringReleaseApproval",
    "append_approval_record",
    "find_approval_record",
    "is_approval_effective",
    "load_approval_records",
    "DEFAULT_RELEASE_AUDIT_PATH",
    "ReleaseAuditRecord",
    "append_audit_record",
    "load_audit_records",
    "DEFAULT_OPERATOR",
    "ReleaseAction",
    "ReleaseOutcome",
    "ReleaseResult",
    "disable_release",
    "enable_release",
    "restore_release",
    "rollback_release",
    "release_precheck",
    "ProductionReadinessChecker",
    "ProductionReadinessReport",
    "check_e_th_realization",
    "check_review_log_chain",
    "validate_release_approval",
    "manual_modified_thresholds",
    "check_verified_integrity",
    "production_readiness",
    "production_readiness_checker",
    "required_audit_events",
    "ReleaseEvidenceBundle",
    "collect_release_evidence_bundle",
    "REQUIRED_INTAKE_EVENTS",
    "ReleaseCandidateRecord",
    "collect_release_candidate",
    "RUNBOOK_VERSION",
]
