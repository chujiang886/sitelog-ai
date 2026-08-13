"""Phase 3.9.6 生产激活证据接收层 —— 提交模型与证据溯源（T3 / T4）。

本模块定义**真实人工提交激活证据**时的两个基础契约：

* ``ActivationEvidenceSubmission``（T3）—— 一条被接收的激活证据提交记录；
* ``EvidenceProvenance`` + ``ChainOfCustodyEvent``（T4）—— 该证据的来源与保管链。

与 Phase 3.9.2 的 ``ProductionReleaseEvidence`` 的区别
------------------------------------------------------
``ProductionReleaseEvidence`` 描述的是"系统内已知的发布证据"（由流水线/仓库自身产生）；
本模块描述的是"**外部真实人工提交进来的激活证据**"——它必须回答三个额外问题：

1. 谁提交的（必须是真实 USER，AI / SYSTEM 不得提交）；
2. 从哪来、经过谁的手（provenance + chain of custody，可审计）；
3. 内容有没有被改（declared vs computed SHA-256）。

红线（Phase 3.9.6 ③④⑨）
------------------------
* AI **不得构造**人工签署，也**不得**把任何提交标记为 ``APPROVED_BY_HUMAN`` /
  ``REJECTED_BY_HUMAN`` —— 这两个状态只能由真实人工经服务层推进，工厂函数会硬拒绝；
* AI 可产出的状态上限是 ``STRUCTURALLY_VALIDATED``，其语义被明确定义为
  "**结构完整，尚未获得任何人工批准**"，绝不等价于 approved；
* 结构校验失败、哈希不匹配、来源不可核验 → 一律 fail-closed 落到
  ``VALIDATION_FAILED`` / ``PENDING_HUMAN_EVIDENCE``，绝不放行。

本模块不持有生产状态、不翻转 ``engineering_enabled``、不宣布 GO。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

from agents.enterprise.production_release.models import (
    EvidenceIntegrityStatus,
    EvidenceVerificationStatus,
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ActivationEvidenceIntakeError(Exception):
    """激活证据接收契约被违反（fail-closed）。"""


# --------------------------------------------------------------------------- #
# 常量                                                                          #
# --------------------------------------------------------------------------- #

#: 提交者必须是真实自然人（USER）。审计层同口径（actor_kind）。
REQUIRED_SUBMITTER_KIND = "user"

#: 激活前必须收齐的证据类型（与 3.9.2 激活证据包口径对齐，可由调用方收窄）。
REQUIRED_ACTIVATION_EVIDENCE_TYPES: Tuple[str, ...] = (
    "rc_freeze_manifest",
    "governance_integrity_report",
    "security_review",
    "staging_validation",
    "rollback_drill",
    "recovery_validation",
)


# --------------------------------------------------------------------------- #
# T4：证据溯源 / 保管链                                                          #
# --------------------------------------------------------------------------- #
class CustodyEventKind(str, Enum):
    """保管链事件类型（append-only，仅记录真实发生过的交接）。"""

    PRODUCED = "produced"  # 证据originally产生（流水线 / 演练 / 扫描）
    EXPORTED = "exported"  # 从源系统导出
    TRANSFERRED = "transferred"  # 人工/系统间交接
    RECEIVED = "received"  # 被 BOIP 接收
    HASHED = "hashed"  # 计算/登记哈希
    REVIEWED = "reviewed"  # 真实人工查阅（不等于批准）


@dataclass(frozen=True)
class ChainOfCustodyEvent:
    """保管链单条事件（T4）。

    ``actor_kind`` 如实记录（user / system）；``PRODUCED`` / ``HASHED`` 等机器动作允许
    system，但 ``TRANSFERRED`` / ``REVIEWED`` 这类需要人负责的动作应为 user。
    本结构只**如实记录**，不做价值判断，也不提升任何状态。
    """

    event_kind: CustodyEventKind
    actor_id: str
    actor_kind: str
    occurred_at: str
    detail: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "event_kind": self.event_kind.value,
            "actor_id": self.actor_id,
            "actor_kind": self.actor_kind,
            "occurred_at": self.occurred_at,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class EvidenceProvenance:
    """证据溯源（T4）：这条证据从哪来、谁交的、经过谁的手、能否核验。

    ``verifiable`` 不是"可信"的同义词，只表示"具备可被人工独立复核的坐标"
    （来源系统 + 来源引用 + 提交者身份 + 至少一条保管链事件 + 声明哈希）。
    真实可信与否，由真实人工在复核阶段判断，AI 不代劳（红线⑨）。
    """

    origin_system: str
    origin_reference: str
    submitted_by: str
    submitted_by_kind: str
    submitted_at: str
    declared_sha256: Optional[str] = None
    captured_at: Optional[str] = None
    chain_of_custody: Tuple[ChainOfCustodyEvent, ...] = field(default_factory=tuple)
    note: str = "PROVENANCE_ONLY: 仅记录来源与保管链，不代表真实性判断"

    @property
    def submitted_by_real_user(self) -> bool:
        return self.submitted_by_kind.strip().lower() == REQUIRED_SUBMITTER_KIND

    @property
    def verifiable(self) -> bool:
        """是否具备可被人工独立复核的最小坐标集（fail-closed）。"""
        return bool(
            self.origin_system.strip()
            and self.origin_reference.strip()
            and self.submitted_by.strip()
            and self.submitted_by_real_user
            and self.declared_sha256
            and self.chain_of_custody
        )

    @property
    def missing_provenance_fields(self) -> List[str]:
        missing: List[str] = []
        if not self.origin_system.strip():
            missing.append("origin_system")
        if not self.origin_reference.strip():
            missing.append("origin_reference")
        if not self.submitted_by.strip():
            missing.append("submitted_by")
        if not self.submitted_by_real_user:
            missing.append("submitted_by_kind!=user")
        if not self.declared_sha256:
            missing.append("declared_sha256")
        if not self.chain_of_custody:
            missing.append("chain_of_custody")
        return missing

    def to_dict(self) -> Dict[str, object]:
        return {
            "origin_system": self.origin_system,
            "origin_reference": self.origin_reference,
            "submitted_by": self.submitted_by,
            "submitted_by_kind": self.submitted_by_kind,
            "submitted_at": self.submitted_at,
            "declared_sha256": self.declared_sha256,
            "captured_at": self.captured_at,
            "chain_of_custody": [e.to_dict() for e in self.chain_of_custody],
            "verifiable": self.verifiable,
            "missing_provenance_fields": self.missing_provenance_fields,
            "note": self.note,
        }


# --------------------------------------------------------------------------- #
# T3：激活证据提交                                                               #
# --------------------------------------------------------------------------- #
class ActivationEvidenceSubmissionStatus(str, Enum):
    """激活证据提交状态。

    AI **可**产出（上限）：
        ``SUBMITTED`` / ``STRUCTURALLY_VALIDATED`` / ``VALIDATION_FAILED`` /
        ``PENDING_HUMAN_EVIDENCE``
    AI **不可**产出（红线④/⑨，只能由真实人工经服务层推进）：
        ``APPROVED_BY_HUMAN`` / ``REJECTED_BY_HUMAN``

    特别注意：``STRUCTURALLY_VALIDATED`` 的含义严格限定为"结构完整、哈希一致、
    来源可核验"，它**不是** approved，也**不**解除任何闸门阻断。
    """

    SUBMITTED = "submitted"
    STRUCTURALLY_VALIDATED = "structurally_validated"
    VALIDATION_FAILED = "validation_failed"
    PENDING_HUMAN_EVIDENCE = "pending_human_evidence"
    APPROVED_BY_HUMAN = "approved_by_human"
    REJECTED_BY_HUMAN = "rejected_by_human"


#: AI 路径允许产出的状态集合（服务层与工厂共同强制）。
AI_ALLOWED_SUBMISSION_STATUSES = frozenset(
    {
        ActivationEvidenceSubmissionStatus.SUBMITTED,
        ActivationEvidenceSubmissionStatus.STRUCTURALLY_VALIDATED,
        ActivationEvidenceSubmissionStatus.VALIDATION_FAILED,
        ActivationEvidenceSubmissionStatus.PENDING_HUMAN_EVIDENCE,
    }
)

#: 只能由真实人工推进的状态集合（AI 触碰即抛错）。
HUMAN_ONLY_SUBMISSION_STATUSES = frozenset(
    {
        ActivationEvidenceSubmissionStatus.APPROVED_BY_HUMAN,
        ActivationEvidenceSubmissionStatus.REJECTED_BY_HUMAN,
    }
)


@dataclass(frozen=True)
class ActivationEvidenceSubmission:
    """一条真实人工提交的激活证据（T3，只读记录）。

    存储安全（T13 前置约束）：本结构**只存引用与哈希**（``content_reference`` /
    ``declared_sha256`` / ``computed_sha256``），**不存证据原文**，因此不会把
    密钥、令牌、生产数据带进仓库或审计流。
    """

    submission_id: str
    rc_id: str
    evidence_type: str
    title: str
    content_reference: str
    provenance: EvidenceProvenance
    status: ActivationEvidenceSubmissionStatus
    integrity_status: EvidenceIntegrityStatus = EvidenceIntegrityStatus.PENDING
    verification_status: EvidenceVerificationStatus = (
        EvidenceVerificationStatus.PENDING_VERIFICATION
    )
    computed_sha256: Optional[str] = None
    validation_findings: Tuple[str, ...] = field(default_factory=tuple)
    received_at: str = ""
    # 人工裁决字段：AI 恒不填充（保持 None），仅真实人工经服务层写入。
    human_decision_by: Optional[str] = None
    human_decision_at: Optional[str] = None
    human_decision_reason: Optional[str] = None
    note: str = (
        "SUBMISSION_ONLY: 仅接收与登记真实人工提交的激活证据；"
        "structurally_validated != approved；不激活、不宣布 GO"
    )

    # -- 派生事实（只读推导，绝不提升状态）-------------------------------- #

    @property
    def hash_declared(self) -> bool:
        return bool(self.provenance.declared_sha256)

    @property
    def hash_computed(self) -> bool:
        return bool(self.computed_sha256)

    @property
    def hash_match(self) -> Optional[bool]:
        """声明哈希与实算哈希是否一致；任一缺失返回 None（未知，不算通过）。"""
        if not self.hash_declared or not self.hash_computed:
            return None
        return (self.provenance.declared_sha256 or "").strip().lower() == (
            self.computed_sha256 or ""
        ).strip().lower()

    @property
    def structurally_valid(self) -> bool:
        """结构是否完整（必填齐备 + 溯源可核验 + 哈希不冲突）。

        注意：哈希"未知"（未实算）不视为结构失败——它只是尚未核验，仍需人工复核；
        但哈希"明确不一致"是硬失败（可能被篡改）。
        """
        if not (
            self.submission_id.strip()
            and self.rc_id.strip()
            and self.evidence_type.strip()
            and self.title.strip()
            and self.content_reference.strip()
        ):
            return False
        if not self.provenance.verifiable:
            return False
        if self.hash_match is False:
            return False
        if self.integrity_status is EvidenceIntegrityStatus.TAMPERED:
            return False
        return True

    @property
    def is_human_approved(self) -> bool:
        """是否已获真实人工批准 —— 仅当状态为 APPROVED_BY_HUMAN 且留有真实决策人。

        AI 无法令其为真：工厂拒绝构造该状态，服务层要求真实 USER 且经审计留痕。
        """
        return (
            self.status is ActivationEvidenceSubmissionStatus.APPROVED_BY_HUMAN
            and bool(self.human_decision_by)
        )

    @property
    def is_human_rejected(self) -> bool:
        return (
            self.status is ActivationEvidenceSubmissionStatus.REJECTED_BY_HUMAN
            and bool(self.human_decision_by)
        )

    @property
    def awaiting_human_review(self) -> bool:
        """结构已过、但尚无任何人工裁决 —— 这是 AI 能达到的最高状态。"""
        return self.structurally_valid and not (
            self.is_human_approved or self.is_human_rejected
        )

    def to_dict(self) -> Dict[str, object]:
        return {
            "submission_id": self.submission_id,
            "rc_id": self.rc_id,
            "evidence_type": self.evidence_type,
            "title": self.title,
            "content_reference": self.content_reference,
            "provenance": self.provenance.to_dict(),
            "status": self.status.value,
            "integrity_status": self.integrity_status.value,
            "verification_status": self.verification_status.value,
            "computed_sha256": self.computed_sha256,
            "hash_match": self.hash_match,
            "validation_findings": list(self.validation_findings),
            "received_at": self.received_at,
            "structurally_valid": self.structurally_valid,
            "is_human_approved": self.is_human_approved,
            "is_human_rejected": self.is_human_rejected,
            "awaiting_human_review": self.awaiting_human_review,
            "human_decision_by": self.human_decision_by,
            "human_decision_at": self.human_decision_at,
            "human_decision_reason": self.human_decision_reason,
            "note": self.note,
        }


# --------------------------------------------------------------------------- #
# 工厂                                                                          #
# --------------------------------------------------------------------------- #
def build_chain_of_custody(
    events: Sequence[Dict[str, object]],
) -> Tuple[ChainOfCustodyEvent, ...]:
    """把外部传入的保管链事件字典列表转为不可变事件元组（如实转换，不补造）。"""
    built: List[ChainOfCustodyEvent] = []
    for raw in events:
        kind_raw = str(raw.get("event_kind", "")).strip()
        try:
            kind = CustodyEventKind(kind_raw)
        except ValueError as exc:
            raise ActivationEvidenceIntakeError(
                f"unknown custody event kind: {kind_raw!r}"
            ) from exc
        actor_id = str(raw.get("actor_id", "")).strip()
        if not actor_id:
            raise ActivationEvidenceIntakeError(
                "chain-of-custody event requires a non-empty actor_id"
            )
        built.append(
            ChainOfCustodyEvent(
                event_kind=kind,
                actor_id=actor_id,
                actor_kind=str(raw.get("actor_kind", "")).strip() or "unknown",
                occurred_at=str(raw.get("occurred_at", "")).strip() or _now(),
                detail=str(raw.get("detail", "")),
            )
        )
    return tuple(built)


def build_evidence_provenance(
    *,
    origin_system: str,
    origin_reference: str,
    submitted_by: str,
    submitted_by_kind: str,
    declared_sha256: Optional[str] = None,
    captured_at: Optional[str] = None,
    chain_of_custody: Sequence[ChainOfCustodyEvent] = (),
    submitted_at: Optional[str] = None,
) -> EvidenceProvenance:
    """构建证据溯源。

    ``submitted_by_kind`` 必须为真实 ``user``；传入 ai / system 直接抛错（红线③/⑨）——
    激活证据只能由真实自然人提交，AI 不得代提交、不得代表人签字。
    """
    if submitted_by_kind.strip().lower() != REQUIRED_SUBMITTER_KIND:
        raise ActivationEvidenceIntakeError(
            "activation evidence must be submitted by a real human user "
            f"(actor_kind='user'), got {submitted_by_kind!r}"
        )
    if not submitted_by.strip():
        raise ActivationEvidenceIntakeError("submitted_by must be a real actor id")

    return EvidenceProvenance(
        origin_system=origin_system,
        origin_reference=origin_reference,
        submitted_by=submitted_by,
        submitted_by_kind=REQUIRED_SUBMITTER_KIND,
        submitted_at=submitted_at or _now(),
        declared_sha256=(declared_sha256 or None),
        captured_at=captured_at,
        chain_of_custody=tuple(chain_of_custody),
    )


def build_activation_evidence_submission(
    *,
    submission_id: str,
    rc_id: str,
    evidence_type: str,
    title: str,
    content_reference: str,
    provenance: EvidenceProvenance,
    computed_sha256: Optional[str] = None,
    integrity_status: EvidenceIntegrityStatus = EvidenceIntegrityStatus.PENDING,
    verification_status: EvidenceVerificationStatus = (
        EvidenceVerificationStatus.PENDING_VERIFICATION
    ),
    status: Optional[ActivationEvidenceSubmissionStatus] = None,
    validation_findings: Sequence[str] = (),
) -> ActivationEvidenceSubmission:
    """构建一条激活证据提交记录（AI 路径 fail-closed）。

    * ``status`` 若未指定，按事实推导：结构完整 → ``STRUCTURALLY_VALIDATED``，
      否则 ``VALIDATION_FAILED``（而非乐观放行）；
    * 显式传入 ``APPROVED_BY_HUMAN`` / ``REJECTED_BY_HUMAN`` 一律抛错 —— 人工裁决
      只能经 ``ActivationEvidenceIntakeService`` 由真实 USER 记录（红线④/⑨）；
    * 本函数**不**填充 ``human_decision_*`` 任何字段。
    """
    if status is not None and status in HUMAN_ONLY_SUBMISSION_STATUSES:
        raise ActivationEvidenceIntakeError(
            "AI must not construct a human decision status "
            f"({status.value}); human approval is recorded only by a real USER"
        )

    findings = list(validation_findings)
    provisional = ActivationEvidenceSubmission(
        submission_id=submission_id,
        rc_id=rc_id,
        evidence_type=evidence_type,
        title=title,
        content_reference=content_reference,
        provenance=provenance,
        status=ActivationEvidenceSubmissionStatus.SUBMITTED,
        integrity_status=integrity_status,
        verification_status=verification_status,
        computed_sha256=computed_sha256,
        validation_findings=tuple(findings),
        received_at=_now(),
    )

    # 结构性发现（如实追加，供人工复核；不影响红线判定之外的任何放行）
    if not provisional.provenance.verifiable:
        missing = ", ".join(provisional.provenance.missing_provenance_fields)
        findings.append(f"provenance_not_verifiable: {missing}")
    if provisional.hash_match is False:
        findings.append("sha256_mismatch: declared != computed (possible tampering)")
    if provisional.hash_match is None:
        findings.append("sha256_not_recomputed: awaiting independent hash verification")
    if integrity_status is EvidenceIntegrityStatus.TAMPERED:
        findings.append("integrity_status=tampered")

    resolved_status = status
    if resolved_status is None:
        resolved_status = (
            ActivationEvidenceSubmissionStatus.STRUCTURALLY_VALIDATED
            if provisional.structurally_valid
            else ActivationEvidenceSubmissionStatus.VALIDATION_FAILED
        )
    if resolved_status not in AI_ALLOWED_SUBMISSION_STATUSES:
        raise ActivationEvidenceIntakeError(
            f"status {resolved_status.value!r} is not permitted on the AI path"
        )

    return ActivationEvidenceSubmission(
        submission_id=submission_id,
        rc_id=rc_id,
        evidence_type=evidence_type,
        title=title,
        content_reference=content_reference,
        provenance=provenance,
        status=resolved_status,
        integrity_status=integrity_status,
        verification_status=verification_status,
        computed_sha256=computed_sha256,
        validation_findings=tuple(findings),
        received_at=provisional.received_at,
    )


__all__ = [
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
]
