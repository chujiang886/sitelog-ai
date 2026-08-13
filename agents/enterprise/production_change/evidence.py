"""Phase 3.9.7 变更证据域（T9）。可关联 phase / artifact / test_result / security_scan /
staging_validation / rollback_drill / recovery_validation / audit_reference / commit /
timestamp，并携带 integrity_status + verification_status。AI 不得把 PENDING_VERIFICATION
自动提升为 VERIFIED（红线⑩）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from agents.enterprise.production_change.models import ChangeEvidence


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_change_evidence(
    *,
    evidence_id: str,
    evidence_type: str,
    source: str,
    source_reference: str,
    change_id: Optional[str] = None,
    integrity_status: str = "pending",
    verification_status: str = "pending_verification",
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
    created_at: Optional[str] = None,
) -> ChangeEvidence:
    """构造一条变更证据（verification_status 初始 PENDING_VERIFICATION；AI 不提升）。"""

    return ChangeEvidence(
        evidence_id=evidence_id,
        evidence_type=evidence_type,
        source=source,
        source_reference=source_reference,
        created_at=created_at or _now(),
        integrity_status=integrity_status,
        verification_status=verification_status,
        change_id=change_id,
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


def build_change_evidence_chain(evidence: List[ChangeEvidence]) -> Dict[str, object]:
    """把多条变更证据聚合成可被 AI 廉价核验的证据链（只读）。"""

    return {
        "count": len(evidence),
        "items": [e.to_dict() for e in evidence],
        "pending_verification": [
            e.evidence_id
            for e in evidence
            if e.verification_status == "pending_verification"
        ],
    }


__all__ = ["build_change_evidence", "build_change_evidence_chain"]
