"""Phase 3.9.6 激活证据接收服务（T5）—— 接收 / 校验 / 登记 / 汇总，永不批准。

本服务是 Phase 3.9.6 的执行中枢：把 T3/T4 的提交与溯源模型、T6/T7 的人工签署记录
与登记簿接进一条**可审计、fail-closed** 的治理流水线：

    真实人工提交证据 → 结构校验（≠批准）→ 真实人工签署登记 → 只读汇总
                                                     ↓
                                        供 T8 评审包 / T10 闸门消费

四条不可让渡的服务级契约
------------------------
1. **提交者必须是真实自然人**：所有写入口均 ``require_human_actor(actor_kind)``，
   AI / SYSTEM 调用直接抛 ``EnterpriseRedLineViolationError``（红线③/⑨）。
2. **校验不等于批准**：AI 路径最高只能把提交推进到 ``STRUCTURALLY_VALIDATED``；
   ``APPROVED_BY_HUMAN`` 只能经 ``record_human_evidence_decision`` 由真实 USER 写入，
   且必须留下决策人与理由（红线④）。
3. **只存引用与哈希，不存原文**：``_compute_sha256`` 以流式分块读取文件求哈希后即
   丢弃内容，服务内**永不**保留证据正文，因此不会把生产密钥 / 生产数据带进仓库或
   审计流（红线⑦，T13 存储安全的运行时保障）。
4. **不放行**：本服务不翻转 ``engineering_enabled``、不产出 ``engineering_approved``、
   不宣布 ``PRODUCTION_GO``、不绕过 ``ControlledActivationGate``（红线①②⑤⑩）。

``_FORBIDDEN = _ACTIVATION_INTAKE_FORBIDDEN`` 在方法名层面结构性拦截一切越权动词。
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import uuid4

from agents.enterprise.audit import (
    AuditActorKind,
    AuditService,
    require_human_actor,
)
from agents.enterprise.production_release.activation_intake import (
    ActivationEvidenceIntakeError,
    ActivationEvidenceSubmission,
    ActivationEvidenceSubmissionStatus,
    EvidenceProvenance,
    REQUIRED_ACTIVATION_EVIDENCE_TYPES,
    build_activation_evidence_submission,
)
from agents.enterprise.production_release.human_signoff import (
    HumanSignoffRecord,
    HumanSignoffRegistry,
    HumanSignoffRegistrySnapshot,
)
from agents.enterprise.production_release.intake_forbidden import (
    _ACTIVATION_INTAKE_FORBIDDEN,
)
from agents.enterprise.production_release.models import EvidenceIntegrityStatus
from agents.enterprise.production_release.review_package import (
    FinalActivationReviewPackage,
    build_final_activation_review_package,
)
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)

#: 计算哈希时的分块大小（流式读取，绝不整块驻留内存 / 绝不保存内容）。
_HASH_CHUNK_BYTES = 1024 * 1024


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ActivationIntakeServiceError(EnterpriseRedLineViolationError):
    """接收服务业务违例（继承红线异常，保证调用方 fail-closed 处理）。"""


# --------------------------------------------------------------------------- #
# 只读汇总                                                                      #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class EvidenceIntakeSummary:
    """接收状态只读汇总（供 T8 评审包 / T10 闸门 / API 消费）。

    ``intake_complete`` 的语义被严格限定为：**必需证据类型全部被真实人工提交、
    且全部通过结构校验、且全部获得真实人工批准**。它依旧不等于放行 —— 放行还需
    四角色签署齐备（T7）与主理人终端裁决。
    """

    rc_id: str
    required_types: Tuple[str, ...]
    submitted_types: Tuple[str, ...]
    missing_types: Tuple[str, ...]
    structurally_validated_ids: Tuple[str, ...]
    validation_failed_ids: Tuple[str, ...]
    human_approved_ids: Tuple[str, ...]
    human_rejected_ids: Tuple[str, ...]
    awaiting_human_ids: Tuple[str, ...]
    total_submissions: int
    intake_complete: bool
    generated_at: str
    note: str = (
        "EVIDENCE_INTAKE_SUMMARY: 只读汇总；structurally_validated != approved；"
        "intake_complete 亦不等于 Production GO；激活由主理人在人类终端执行"
    )

    def to_dict(self) -> Dict[str, object]:
        return {
            "rc_id": self.rc_id,
            "required_types": list(self.required_types),
            "submitted_types": list(self.submitted_types),
            "missing_types": list(self.missing_types),
            "structurally_validated_ids": list(self.structurally_validated_ids),
            "validation_failed_ids": list(self.validation_failed_ids),
            "human_approved_ids": list(self.human_approved_ids),
            "human_rejected_ids": list(self.human_rejected_ids),
            "awaiting_human_ids": list(self.awaiting_human_ids),
            "total_submissions": self.total_submissions,
            "intake_complete": self.intake_complete,
            "generated_at": self.generated_at,
            "note": self.note,
        }


# --------------------------------------------------------------------------- #
# 服务                                                                          #
# --------------------------------------------------------------------------- #
class ActivationEvidenceIntakeService(_RedLineForbiddenMixin):
    """激活证据接收与人工签署治理服务（T5，fail-closed）。

    持有两个 append-only 集合：
    * ``_submissions``：按 submission_id 索引的证据提交（人工裁决以 supersede 语义更新，
      历史保留在 ``_decision_log``）；
    * ``_registry``：``HumanSignoffRegistry``（T7），只追加真实人工签署。

    服务**不持有证据原文**、不持有任何生产状态。
    """

    _FORBIDDEN = _ACTIVATION_INTAKE_FORBIDDEN

    def __init__(
        self,
        *,
        rc_id: str,
        audit: AuditService,
        required_evidence_types: Sequence[str] = REQUIRED_ACTIVATION_EVIDENCE_TYPES,
        root_dir: str = ".",
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构建证据接收层（红线①）"
            )
        if not str(rc_id).strip():
            raise ActivationIntakeServiceError("intake service requires a real rc_id")
        self._rc_id = str(rc_id).strip()
        self._audit = audit
        self._root_dir = root_dir
        self._required_types: Tuple[str, ...] = tuple(required_evidence_types)
        self._submissions: Dict[str, ActivationEvidenceSubmission] = {}
        self._decision_log: List[Dict[str, object]] = []
        self._registry = HumanSignoffRegistry(rc_id=self._rc_id)

    # ------------------------------------------------------------------ #
    # 内部工具
    # ------------------------------------------------------------------ #
    @property
    def rc_id(self) -> str:
        return self._rc_id

    @property
    def required_types(self) -> Tuple[str, ...]:
        return self._required_types

    @property
    def registry(self) -> HumanSignoffRegistry:
        """签署登记簿（只读使用；写入须经 ``register_human_signoff``）。"""
        return self._registry

    @property
    def decision_log(self) -> Tuple[Dict[str, object], ...]:
        """人工裁决历史（append-only，含被取代的早期裁决）。"""
        return tuple(dict(d) for d in self._decision_log)

    def _compute_sha256(self, content_reference: str) -> Optional[str]:
        """对**本地可读**的证据引用流式计算 SHA-256；内容读完即弃（红线⑦）。

        ``content_reference`` 若不是本地存在的文件（如工单号 / 外部 URL / 线下件编号），
        返回 ``None`` —— 服务不会为了"凑一个哈希"去抓取外部内容，也不会伪造。
        """
        ref = (content_reference or "").strip()
        if not ref:
            return None
        path = ref if os.path.isabs(ref) else os.path.join(self._root_dir, ref)
        if not os.path.isfile(path):
            return None
        digest = hashlib.sha256()
        try:
            with open(path, "rb") as fh:
                while True:
                    chunk = fh.read(_HASH_CHUNK_BYTES)
                    if not chunk:
                        break
                    digest.update(chunk)
        except OSError:
            return None
        # 注意：chunk 为局部变量，函数返回后即释放；服务不保存任何证据正文。
        return digest.hexdigest()

    # ------------------------------------------------------------------ #
    # 1) 真实人工提交证据（AI 不得代提交）
    # ------------------------------------------------------------------ #
    def submit_evidence(
        self,
        *,
        actor_kind: AuditActorKind,
        actor_id: str,
        evidence_type: str,
        title: str,
        content_reference: str,
        provenance: EvidenceProvenance,
        submission_id: Optional[str] = None,
        integrity_status: EvidenceIntegrityStatus = EvidenceIntegrityStatus.PENDING,
        recompute_hash: bool = True,
    ) -> ActivationEvidenceSubmission:
        """接收一条真实人工提交的激活证据。

        流程：human-gating → 独立重算哈希（若引用为本地文件）→ 构造提交记录
        （状态最高 ``STRUCTURALLY_VALIDATED``）→ 审计留痕。

        **绝不**因为"结构通过"就视为采信：``STRUCTURALLY_VALIDATED`` 与 approved
        在本系统中是两个正交概念（红线④）。
        """

        require_human_actor(actor_kind)
        if not str(actor_id).strip():
            raise ActivationIntakeServiceError(
                "evidence submission requires a real actor_id（红线③/⑨）"
            )
        if provenance.submitted_by.strip() != str(actor_id).strip():
            raise ActivationIntakeServiceError(
                "provenance.submitted_by must match the submitting actor_id "
                f"({provenance.submitted_by!r} != {actor_id!r})"
            )

        sid = submission_id or f"aes-{uuid4().hex[:12]}"
        if sid in self._submissions:
            raise ActivationIntakeServiceError(
                f"submission_id already exists (append-only): {sid!r}"
            )

        computed = self._compute_sha256(content_reference) if recompute_hash else None

        submission = build_activation_evidence_submission(
            submission_id=sid,
            rc_id=self._rc_id,
            evidence_type=evidence_type,
            title=title,
            content_reference=content_reference,
            provenance=provenance,
            computed_sha256=computed,
            integrity_status=integrity_status,
        )
        self._submissions[sid] = submission

        self._audit.record_activation_evidence_submitted(
            record_id=f"aes-{uuid4().hex[:12]}",
            actor_id=str(actor_id),
            action="submit_activation_evidence",
            target=f"{self._rc_id}:{sid}",
            detail=(
                f"type={evidence_type};status={submission.status.value};"
                f"hash_match={submission.hash_match};"
                f"findings={len(submission.validation_findings)}"
            ),
            ts=_now(),
        )
        # 结构校验是一个独立的、可被单独审计的事实（validated ≠ approved）。
        if submission.status is ActivationEvidenceSubmissionStatus.STRUCTURALLY_VALIDATED:
            self._audit.record_activation_evidence_validated(
                record_id=f"aev-{uuid4().hex[:12]}",
                actor_id=str(actor_id),
                action="validate_activation_evidence",
                target=f"{self._rc_id}:{sid}",
                detail="structurally_validated=true;approved=false",
                ts=_now(),
            )
        return submission

    # ------------------------------------------------------------------ #
    # 2) 重新校验（只重算事实，不提升状态）
    # ------------------------------------------------------------------ #
    def revalidate_submission(
        self,
        *,
        actor_kind: AuditActorKind,
        actor_id: str,
        submission_id: str,
    ) -> ActivationEvidenceSubmission:
        """重新独立计算哈希并刷新结构校验结论（不触碰任何人工裁决字段）。

        若该提交已有真实人工裁决（approved / rejected），本方法**保留**其裁决状态，
        只更新客观事实（computed_sha256 / findings）——AI 绝不覆盖人工决策（红线⑨）。
        """

        require_human_actor(actor_kind)
        current = self._get(submission_id)
        computed = self._compute_sha256(current.content_reference)

        refreshed = build_activation_evidence_submission(
            submission_id=current.submission_id,
            rc_id=current.rc_id,
            evidence_type=current.evidence_type,
            title=current.title,
            content_reference=current.content_reference,
            provenance=current.provenance,
            computed_sha256=computed,
            integrity_status=current.integrity_status,
        )
        # 已有人工裁决 → 只更新客观字段，裁决状态与决策人原样保留（红线⑨）。
        if current.human_decision_by:
            refreshed = replace(
                refreshed,
                status=current.status,
                human_decision_by=current.human_decision_by,
                human_decision_at=current.human_decision_at,
                human_decision_reason=current.human_decision_reason,
            )
        self._submissions[submission_id] = refreshed

        self._audit.record_activation_evidence_validated(
            record_id=f"aev-{uuid4().hex[:12]}",
            actor_id=str(actor_id),
            action="revalidate_activation_evidence",
            target=f"{self._rc_id}:{submission_id}",
            detail=(
                f"structurally_valid={refreshed.structurally_valid};"
                f"hash_match={refreshed.hash_match};approved=false"
            ),
            ts=_now(),
        )
        return refreshed

    # ------------------------------------------------------------------ #
    # 3) 真实人工对单条证据的裁决（唯一能产出 APPROVED_BY_HUMAN 的路径）
    # ------------------------------------------------------------------ #
    def record_human_evidence_decision(
        self,
        *,
        actor_kind: AuditActorKind,
        actor_id: str,
        submission_id: str,
        approved: bool,
        reason: str,
    ) -> ActivationEvidenceSubmission:
        """登记一次**已经发生**的真实人工证据裁决。

        约束（fail-closed）：
        * ``actor_kind`` 必须为真实 USER（``require_human_actor``）；
        * ``reason`` 必须非空 —— 无理由的批准不可采信；
        * 结构校验失败的证据**不得**被标记为 approved（可以被 reject）——
          这是防止"人被诱导批准一份哈希对不上的证据"的最后一道机器护栏；
        * 覆盖既有裁决时保留历史（append-only ``_decision_log``），如实暴露改判。

        本方法不因批准而解除任何闸门 —— 闸门由 T10 依据完整事实独立判定。
        """

        require_human_actor(actor_kind)
        if not str(actor_id).strip():
            raise ActivationIntakeServiceError(
                "human evidence decision requires a real actor_id（红线③/⑨）"
            )
        if not str(reason).strip():
            raise ActivationIntakeServiceError(
                "human evidence decision requires a non-empty reason "
                "（无理由的批准不可采信）"
            )

        current = self._get(submission_id)
        if approved and not current.structurally_valid:
            raise ActivationIntakeServiceError(
                "cannot approve a structurally invalid submission "
                f"({submission_id!r}); findings={list(current.validation_findings)}"
            )

        if current.human_decision_by:
            # 如实登记"改判"这一事实，历史不删除。
            self._decision_log.append(
                {
                    "submission_id": submission_id,
                    "superseded_status": current.status.value,
                    "superseded_by_actor": current.human_decision_by,
                    "superseded_at": current.human_decision_at,
                    "superseded_reason": current.human_decision_reason,
                    "logged_at": _now(),
                }
            )

        decided_at = _now()
        new_status = (
            ActivationEvidenceSubmissionStatus.APPROVED_BY_HUMAN
            if approved
            else ActivationEvidenceSubmissionStatus.REJECTED_BY_HUMAN
        )
        updated = replace(
            current,
            status=new_status,
            human_decision_by=str(actor_id),
            human_decision_at=decided_at,
            human_decision_reason=str(reason),
        )
        self._submissions[submission_id] = updated
        self._decision_log.append(
            {
                "submission_id": submission_id,
                "decision": new_status.value,
                "actor_id": str(actor_id),
                "decided_at": decided_at,
                "reason": str(reason)[:500],
            }
        )

        self._audit.record_activation_evidence_validated(
            record_id=f"aeh-{uuid4().hex[:12]}",
            actor_id=str(actor_id),
            action="record_human_evidence_decision",
            target=f"{self._rc_id}:{submission_id}",
            detail=(
                f"decision={new_status.value};"
                f"human_decided=true;reason={str(reason)[:200]}"
            ),
            ts=decided_at,
        )
        return updated

    # ------------------------------------------------------------------ #
    # 4) 真实人工签署登记（T7 登记簿写入口）
    # ------------------------------------------------------------------ #
    def register_human_signoff(
        self,
        *,
        actor_kind: AuditActorKind,
        record: HumanSignoffRecord,
    ) -> HumanSignoffRecord:
        """把一条**已经发生**的真实人工签署登记进登记簿（append-only）。

        服务不构造 ``HumanSignoffRecord``（构造须经 ``build_human_signoff_record``，
        且强制 ``actor_kind='user'`` + 真实 ``signature_reference``）；这里只做
        human-gating、归属校验、登记与审计留痕（红线③/⑨）。
        """

        require_human_actor(actor_kind)
        if record.actor_id.strip() == "":
            raise ActivationIntakeServiceError("signoff record requires a real actor_id")
        registered = self._registry.register(record)

        self._audit.record_human_signoff_registered(
            record_id=f"hsr-{uuid4().hex[:12]}",
            actor_id=record.actor_id,
            action="register_human_signoff",
            target=f"{self._rc_id}:{record.role.value}",
            detail=(
                f"decision={record.decision.value};"
                f"signature_reference={record.signature_reference[:120]};"
                f"scope={len(record.evidence_scope_reviewed)}"
            ),
            ts=record.signed_at or _now(),
        )
        return registered

    # ------------------------------------------------------------------ #
    # 5) 只读查询与汇总
    # ------------------------------------------------------------------ #
    def _get(self, submission_id: str) -> ActivationEvidenceSubmission:
        try:
            return self._submissions[submission_id]
        except KeyError as exc:
            raise ActivationIntakeServiceError(
                f"unknown submission_id: {submission_id!r}"
            ) from exc

    def get_submission(self, submission_id: str) -> ActivationEvidenceSubmission:
        return self._get(submission_id)

    def submissions(self) -> Tuple[ActivationEvidenceSubmission, ...]:
        return tuple(self._submissions.values())

    def submissions_by_type(self) -> Dict[str, Tuple[ActivationEvidenceSubmission, ...]]:
        grouped: Dict[str, List[ActivationEvidenceSubmission]] = {}
        for sub in self._submissions.values():
            grouped.setdefault(sub.evidence_type, []).append(sub)
        return {k: tuple(v) for k, v in grouped.items()}

    def signoff_snapshot(self) -> HumanSignoffRegistrySnapshot:
        return self._registry.snapshot()

    def summarize(self) -> EvidenceIntakeSummary:
        """产出只读接收汇总（fail-closed：任何未知一律不计入完成）。"""

        subs = list(self._submissions.values())
        # 一个类型只要**存在一条获真实人工批准**的提交，才算该类型已满足。
        approved_types = {s.evidence_type for s in subs if s.is_human_approved}
        submitted_types = {s.evidence_type for s in subs}
        missing = tuple(t for t in self._required_types if t not in approved_types)

        intake_complete = not missing and bool(self._required_types)

        return EvidenceIntakeSummary(
            rc_id=self._rc_id,
            required_types=self._required_types,
            submitted_types=tuple(sorted(submitted_types)),
            missing_types=missing,
            structurally_validated_ids=tuple(
                sorted(s.submission_id for s in subs if s.structurally_valid)
            ),
            validation_failed_ids=tuple(
                sorted(s.submission_id for s in subs if not s.structurally_valid)
            ),
            human_approved_ids=tuple(
                sorted(s.submission_id for s in subs if s.is_human_approved)
            ),
            human_rejected_ids=tuple(
                sorted(s.submission_id for s in subs if s.is_human_rejected)
            ),
            awaiting_human_ids=tuple(
                sorted(s.submission_id for s in subs if s.awaiting_human_review)
            ),
            total_submissions=len(subs),
            intake_complete=intake_complete,
            generated_at=_now(),
        )


    # ------------------------------------------------------------------ #
    # 6) 生成最终人工评审包（T8）—— 材料，不是裁决
    # ------------------------------------------------------------------ #
    def build_review_package(
        self,
        *,
        actor_kind: AuditActorKind,
        actor_id: str,
        gate_snapshot: Optional[Dict[str, Any]] = None,
        package_id: Optional[str] = None,
    ) -> "FinalActivationReviewPackage":
        """应真实人工请求，汇总当前全部事实生成只读评审材料包。

        必须由真实自然人发起（``require_human_actor``）—— 审计记录里的
        ``actor_kind`` 固定为 USER，若允许 AI 自行生成，审计就会撒谎。

        评审包**不含**任何放行结论：其就绪度上限为
        ``READY_FOR_HUMAN_FINAL_REVIEW``，且构建期会对序列化产物做放行词元扫描
        （红线②⑤⑩）。本方法也不改变任何提交 / 签署状态。
        """

        require_human_actor(actor_kind)
        if not str(actor_id).strip():
            raise ActivationIntakeServiceError(
                "review package generation requires a real actor_id（红线⑤）"
            )

        summary = self.summarize()
        snapshot = self.signoff_snapshot()
        pid = package_id or f"farp-{uuid4().hex[:12]}"

        package = build_final_activation_review_package(
            package_id=pid,
            rc_id=self._rc_id,
            generated_for_actor=str(actor_id),
            evidence_summary=summary.to_dict(),
            signoff_snapshot=snapshot,
            submissions=self.submissions(),
            gate_snapshot=gate_snapshot,
            decision_log_size=len(self._decision_log),
            required_submission_ids=summary.human_approved_ids,
        )

        self._audit.record_activation_review_package_generated(
            record_id=f"arp-{uuid4().hex[:12]}",
            actor_id=str(actor_id),
            action="generate_activation_review_package",
            target=f"{self._rc_id}:{pid}",
            detail=(
                f"readiness={package.readiness.value};"
                f"outstanding={len(package.outstanding_items)};"
                f"evidence={summary.total_submissions};"
                f"signed_roles={len(snapshot.signed_roles)};"
                "carries_decision=false"
            ),
            ts=package.generated_at,
        )
        return package


__all__ = [
    "ActivationIntakeServiceError",
    "EvidenceIntakeSummary",
    "ActivationEvidenceIntakeService",
]
