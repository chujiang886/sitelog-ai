"""Phase 3.9.10 —— External Staging Evidence Model & Chain（Tasks 19-20）。

- ``ExternalStagingQualificationEvidence``：单条证据（scope 固定 ``EXTERNAL_STAGING``，
  禁止 ``PRODUCTION``；``contains_secret`` 恒为 ``False``）。
- ``EvidenceChain``：Resource Registry → Configuration → Connectivity → Isolation →
  Deployment → Runtime Health → Telemetry → Alert → Failure/Recovery → Qualification
  Gate → Human Review。复用 SHA-256 / Chain of Custody，不造第二套审计系统。

fail-closed：任何证据不得携带真实 Secret；scope 不得为 production。
"""

from __future__ import annotations

import datetime as _dt
import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable

from agents.external_staging_qualification.models import ExternalStagingIdentityError


class EvidenceType(str, Enum):
    """证据类型（链节点）。"""

    RESOURCE_REGISTRY = "resource_registry"
    CONFIGURATION = "configuration"
    CONNECTIVITY = "connectivity"
    ISOLATION = "isolation"
    DEPLOYMENT = "deployment"
    RUNTIME_HEALTH = "runtime_health"
    TELEMETRY = "telemetry"
    ALERT = "alert"
    FAILURE_RECOVERY = "failure_recovery"
    QUALIFICATION_GATE = "qualification_gate"
    HUMAN_REVIEW = "human_review"


class EvidenceScope(str, Enum):
    """证据作用域（禁止 PRODUCTION）。"""

    EXTERNAL_STAGING = "external_staging"
    LOCAL_STAGING = "local_staging"
    DEVELOPMENT = "development"


_ALLOWED_SCOPES = frozenset(s.value for s in EvidenceScope)


@dataclass(frozen=True)
class ExternalStagingQualificationEvidence:
    """单条资格证据（不可变，scope 固定非 production，不含真实 Secret）。"""

    evidence_id: str
    resource_id: str
    evidence_type: EvidenceType
    environment: str
    source: str
    generated_at: str
    actor: str
    verification_status: str
    hash: str
    source_reference: str = ""
    contains_secret: bool = False

    def __post_init__(self) -> None:
        if self.environment not in _ALLOWED_SCOPES:
            raise ExternalStagingIdentityError(
                f"证据作用域 {self.environment!r} 非法（禁止 PRODUCTION）。"
            )
        if self.contains_secret:
            raise ExternalStagingIdentityError(
                "证据不得包含真实 Secret（contains_secret 必须为 False）。"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "resource_id": self.resource_id,
            "evidence_type": self.evidence_type.value,
            "environment": self.environment,
            "source": self.source,
            "generated_at": self.generated_at,
            "actor": self.actor,
            "verification_status": self.verification_status,
            "hash": self.hash,
            "source_reference": self.source_reference,
            "contains_secret": self.contains_secret,
        }


def make_evidence(
    *,
    evidence_id: str,
    resource_id: str,
    evidence_type: EvidenceType,
    source: str,
    actor: str,
    verification_status: str,
    source_reference: str = "",
    environment: str = EvidenceScope.EXTERNAL_STAGING.value,
    generated_at: str | None = None,
) -> ExternalStagingQualificationEvidence:
    """构造一条证据并自动计算 SHA-256（payload 不含明文凭据）。"""

    generated_at = generated_at or _dt.datetime.now(_dt.timezone.utc).isoformat()
    payload = (
        f"{evidence_id}|{resource_id}|{evidence_type.value}|{environment}|"
        f"{source}|{actor}|{verification_status}|{source_reference}"
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return ExternalStagingQualificationEvidence(
        evidence_id=evidence_id,
        resource_id=resource_id,
        evidence_type=evidence_type,
        environment=environment,
        source=source,
        generated_at=generated_at,
        actor=actor,
        verification_status=verification_status,
        hash=digest,
        source_reference=source_reference,
        contains_secret=False,
    )


@dataclass
class EvidenceChain:
    """证据链（Task 19）。"""

    items: tuple[ExternalStagingQualificationEvidence, ...] = field(
        default_factory=tuple
    )

    def append(self, evidence: ExternalStagingQualificationEvidence) -> "EvidenceChain":
        return EvidenceChain(items=self.items + (evidence,))

    def chain_hash(self) -> str:
        """整链 SHA-256（fail-closed 链式摘要）。"""

        joined = "|".join(e.hash for e in self.items)
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()

    def summary(self) -> dict[str, Any]:
        by_type: dict[str, int] = {}
        for e in self.items:
            by_type[e.evidence_type.value] = by_type.get(e.evidence_type.value, 0) + 1
        return {
            "count": len(self.items),
            "by_type": by_type,
            "chain_hash": self.chain_hash(),
            "all_scope_external_staging": all(
                e.environment == EvidenceScope.EXTERNAL_STAGING.value for e in self.items
            ),
            "none_contains_secret": all(not e.contains_secret for e in self.items),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [e.to_dict() for e in self.items],
            "summary": self.summary(),
        }


__all__ = [
    "EvidenceType",
    "EvidenceScope",
    "ExternalStagingQualificationEvidence",
    "make_evidence",
    "EvidenceChain",
]
