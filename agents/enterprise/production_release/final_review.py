"""Phase 3.9.7 生产激活最终人工评审与 Go/No-Go 就绪层（T1–T11）。

本模块位于 BOIP 治理层最末端：**在四角色真实签署 + 真实人工 GO/NO-GO 裁决之前**，
把"材料是否齐备、签署是否齐备、是否存在冲突或漂移、是否可供人来判"这四类事实
收敛成一组**只读、可审计、fail-closed** 的领域结构。

核心立场（红线①②⑤⑨⑩）
------------------------
* **AI 仅是只读事实 custodian**：本模块汇总、比对、标记，但**不构造**任何人工签署、
  不构造任何 GO 裁决、不翻转 ``engineering_enabled``、不宣布 Production GO。
* **就绪度不含放行终态**：``FinalReviewReadiness``（T7）的取值集合里**根本不存在**
  ``go`` / ``approved`` / ``activated`` / ``engineering_approved``；能表达的最高就绪度
  是 ``READY_FOR_HUMAN_GO_NO_GO_REVIEW``（"材料齐了，请人来判"）。
* **冲突与漂移只标记不解决**：``HumanSignoffConflictDetector``（T4）与
  ``ActivationEvidenceDriftDetector``（T5）仅输出候选 / 发现，绝不自动修复、绝不自动
  重生成评审包 —— 修复是主理人与四角色的责任。
* **T8 复用而非重造**：最终裁决逻辑直接复用 Phase 3.9.6 ``final_decision.py`` 的
  ``FinalHumanActivationDecision``，本模块不另立一套裁决模型。

与 Phase 3.9.6 的正交关系
--------------------------
Phase 3.9.6 产出 ``FinalActivationReviewPackage``（供人裁决的材料包）与
``FinalHumanActivationDecision``（人的裁决登记）。本模块在其之上叠加：
``FinalReviewEvidenceSnapshot``（T1 事实引用快照）→
``ActivationEvidenceCompletenessMatrix``（T2 完整性矩阵）→
``FourRoleSignoffMatrix``（T3 签署矩阵）→
``HumanSignoffConflictDetector``（T4 冲突）→
``ActivationEvidenceDriftDetector``（T5 漂移）→
``FinalActivationReviewPacket``（T6 评审包 + SourceTrace）→
``FinalReviewReadinessEvaluator``（T7 就绪度）→
``FinalProductionDecision``（T8 复用裁决）→
``HumanFinalDecisionVerifier``（T9 裁决校验）→
``ProductionActivationHandoffPackage``（T10 交接包）→
``ActivationAbortConditionCatalog``（T11 中止条件目录）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from agents.config_loader import load_engineering_enabled
from agents.enterprise.production_release.activation_evidence import (
    REQUIRED_SIGNOFF_ROLES,
)
from agents.enterprise.production_release.final_decision import (
    FinalDecisionOutcome,
    FinalHumanActivationDecision,
    FinalHumanDecisionError,
    build_final_human_activation_decision,
)
from agents.enterprise.production_release.human_signoff import (
    HumanSignoffRegistrySnapshot,
)
from agents.enterprise.production_release.models import SignoffRole, SignoffDecision
from agents.enterprise.production_release.review_package import (
    FinalActivationReviewPackage,
    ReviewPackageReadiness,
    build_final_activation_review_package,
)
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    safety_invariants_ok,
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class FinalReviewError(EnterpriseRedLineViolationError):
    """Phase 3.9.7 最终评审层契约被违反（继承红线异常，调用方 fail-closed）。"""


# --------------------------------------------------------------------------- #
# 放行类词元（本模块输出禁止出现）                                                  #
# --------------------------------------------------------------------------- #
#: 一旦出现在本模块任何非注释字段中即判定越权的放行类词元（小写匹配）。
_FINAL_REVIEW_FORBIDDEN_TOKENS: Tuple[str, ...] = (
    "engineering_approved",
    "production_go",
    "go_live_approved",
    "activated_by_human",
    "auto_approved",
    "auto_activated",
    "approved_for_production",
    "activation_granted",
    "ai_go",
    "ai_approved",
)

#: 扫描时跳过的说明性字段（这些字段的正文本身要**讲**红线，必然含关键词）。
_FINAL_REVIEW_NOTE_KEYS = ("note", "notes", "disclaimer", "human_action_required", "detail")


def _scan_forbidden_tokens(payload: Any, path: str = "$") -> List[str]:
    """递归扫描序列化产物，返回命中放行类词元的字段路径（跳过说明性字段）。"""
    hits: List[str] = []
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            key_s = str(key)
            if key_s in _FINAL_REVIEW_NOTE_KEYS or key_s.endswith("_note"):
                continue
            hits.extend(_scan_forbidden_tokens(value, f"{path}.{key_s}"))
    elif isinstance(payload, (list, tuple)):
        for idx, item in enumerate(payload):
            hits.extend(_scan_forbidden_tokens(item, f"{path}[{idx}]"))
    elif isinstance(payload, str):
        low = payload.lower()
        for token in _FINAL_REVIEW_FORBIDDEN_TOKENS:
            if token in low:
                hits.append(f"{path}:{token}")
    return hits


# --------------------------------------------------------------------------- #
# T1：最终评审证据事实快照（只读引用 + 哈希，绝不复制 secret）                        #
# --------------------------------------------------------------------------- #
#: Phase 3.9.7 最终评审需要核对的 11 类事实（仅引用与哈希，不含原文 / secret）。
FINAL_REVIEW_EVIDENCE_FACT_KINDS: Tuple[str, ...] = (
    "rc_freeze_manifest",
    "governance_integrity_report",
    "security_review",
    "staging_validation",
    "rollback_drill",
    "recovery_validation",
    "human_signoff_registry",
    "final_review_package",
    "final_decision_ledger",
    "readiness_evaluation",
    "handoff_package",
)


@dataclass(frozen=True)
class FinalReviewEvidenceFact:
    """单条证据事实引用（T1，只读）。

    **绝不复制 secret / 原文**：``source_ref`` 是引用坐标（路径 / ledger id /
    artifact id），``sha256`` 是所引用产物的哈希。敏感内容只以哈希形式留存。
    """

    fact_id: str
    fact_kind: str
    source_ref: str  # 引用坐标，非原文
    sha256: Optional[str]  # 所引用产物的哈希；敏感内容绝不入库
    present: bool
    captured_at: str
    note: str = (
        "EVIDENCE_FACT_REF_ONLY: 仅存引用与哈希，绝不复制 secret / 原文"
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fact_id": self.fact_id,
            "fact_kind": self.fact_kind,
            "source_ref": self.source_ref,
            "sha256": self.sha256,
            "present": self.present,
            "captured_at": self.captured_at,
            "note": self.note,
        }


@dataclass(frozen=True)
class FinalReviewEvidenceSnapshot:
    """最终评审证据事实快照（T1，只读汇总）。

    AI 仅**汇总统读**既有事实的引用与哈希，不构造、不补全、不存储任何 secret。
    """

    snapshot_id: str
    rc_id: str
    captured_at: str
    facts: Tuple[FinalReviewEvidenceFact, ...]
    generated_by: str = "ai_custodian_readonly"
    note: str = (
        "EVIDENCE_SNAPSHOT_READONLY: 事实引用汇总；AI 不编造、不补全、不存储 secret"
    )

    def fact_by_kind(self, fact_kind: str) -> Optional[FinalReviewEvidenceFact]:
        for fact in self.facts:
            if fact.fact_kind == fact_kind:
                return fact
        return None

    def missing_kinds(self, required: Sequence[str]) -> Tuple[str, ...]:
        present = {f.fact_kind for f in self.facts if f.present}
        return tuple(k for k in required if k not in present)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "rc_id": self.rc_id,
            "captured_at": self.captured_at,
            "facts": [f.to_dict() for f in self.facts],
            "generated_by": self.generated_by,
            "present_fact_kinds": sorted(f.fact_kind for f in self.facts if f.present),
            "note": self.note,
        }


def build_final_review_evidence_snapshot(
    *,
    snapshot_id: str,
    rc_id: str,
    facts: Sequence[FinalReviewEvidenceFact],
) -> FinalReviewEvidenceSnapshot:
    """构建最终评审证据事实快照（只读；不复制任何 secret）。"""
    facts_tuple = tuple(facts)
    if not facts_tuple:
        raise FinalReviewError("evidence snapshot requires at least one fact reference")
    return FinalReviewEvidenceSnapshot(
        snapshot_id=snapshot_id,
        rc_id=rc_id,
        captured_at=_now(),
        facts=facts_tuple,
    )


# --------------------------------------------------------------------------- #
# T2：激活证据完整性矩阵（8 项，状态不含 AI_APPROVED）                              #
# --------------------------------------------------------------------------- #
#: 完整性矩阵需要核对的 8 项（覆盖激活证据与最终评审链路）。
FINAL_REVIEW_COMPLETENESS_ITEMS: Tuple[str, ...] = (
    "rc_freeze_manifest",
    "governance_integrity_report",
    "security_review",
    "staging_validation",
    "rollback_drill",
    "recovery_validation",
    "four_role_signoffs",
    "final_decision_ledger",
)


class CompletenessStatus(str, Enum):
    """证据项完整性状态（**刻意不含 AI_APPROVED / approved**）。

    AI 只能把状态推到 ``HUMAN_REVIEWED``，且须由真实人工在 ``reviewed_by`` 留痕；
    任何 ``approved`` 语义都不在本枚举内（红线②⑤⑨）。
    """

    MISSING = "missing"
    SUBMITTED = "submitted"
    STRUCTURALLY_VALIDATED = "structurally_validated"
    HUMAN_REVIEWED = "human_reviewed"


ALLOWED_COMPLETENESS_STATUS = frozenset(CompletenessStatus)


@dataclass(frozen=True)
class CompletenessItem:
    """完整性矩阵中的单项（T2）。

    ``HUMAN_REVIEWED`` 必须由真实人工在 ``reviewed_by`` 留痕 —— AI 不得把状态
    标为已人工复核却无复核人（红线⑨）。
    """

    item_id: str
    item_kind: str
    status: CompletenessStatus
    reviewed_by: Optional[str] = None  # 真实人工 ID；AI 不得填
    reviewed_at: Optional[str] = None
    note: str = (
        "COMPLETENESS_ITEM: 状态不含 AI 审批；HUMAN_REVIEWED 须由真实人工留痕"
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "item_kind": self.item_kind,
            "status": self.status.value,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at,
            "note": self.note,
        }


@dataclass(frozen=True)
class ActivationEvidenceCompletenessMatrix:
    """激活证据完整性矩阵（T2，只读聚合）。

    ``is_evidence_complete`` 为真**仅**表示 8 项全部达到 ``HUMAN_REVIEWED``；
    它不等于放行，只是"材料可供人来判"的前提之一（红线⑤）。
    """

    matrix_id: str
    rc_id: str
    items: Tuple[CompletenessItem, ...]
    generated_at: str
    note: str = (
        "COMPLETENESS_MATRIX: 仅陈述证据完整性事实；不含 AI 审批；不翻转 engineering_enabled"
    )

    def by_kind(self, item_kind: str) -> Optional[CompletenessItem]:
        for item in self.items:
            if item.item_kind == item_kind:
                return item
        return None

    @property
    def is_evidence_complete(self) -> bool:
        return all(
            item.status is CompletenessStatus.HUMAN_REVIEWED for item in self.items
        )

    @property
    def missing_items(self) -> Tuple[str, ...]:
        return tuple(
            item.item_kind
            for item in self.items
            if item.status is CompletenessStatus.MISSING
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "matrix_id": self.matrix_id,
            "rc_id": self.rc_id,
            "items": [i.to_dict() for i in self.items],
            "is_evidence_complete": self.is_evidence_complete,
            "missing_items": list(self.missing_items),
            "generated_at": self.generated_at,
            "note": self.note,
        }


def build_activation_evidence_completeness_matrix(
    *,
    matrix_id: str,
    rc_id: str,
    items: Sequence[CompletenessItem],
) -> ActivationEvidenceCompletenessMatrix:
    """构建完整性矩阵（fail-closed）。

    * 每个条目状态必须落在 ``ALLOWED_COMPLETENESS_STATUS`` 内（刻意排除一切
      ``approved`` / ``ai_approved`` 语义，红线②）；
    * ``HUMAN_REVIEWED`` 必须有真实 ``reviewed_by`` 留痕（红线⑨）。
    """
    items_tuple = tuple(items)
    if not items_tuple:
        raise FinalReviewError("completeness matrix requires at least one item")
    for item in items_tuple:
        if item.status not in ALLOWED_COMPLETENESS_STATUS:
            raise FinalReviewError(
                f"completeness status {item.status!r} 不在允许集合内"
                f"（禁止 AI_APPROVED / approved，红线②）"
            )
        if item.status is CompletenessStatus.HUMAN_REVIEWED:
            if not str(item.reviewed_by or "").strip():
                raise FinalReviewError(
                    f"item {item.item_kind} 标记为 HUMAN_REVIEWED 但无 reviewed_by "
                    f"真实人工留痕（红线⑨）"
                )
    return ActivationEvidenceCompletenessMatrix(
        matrix_id=matrix_id,
        rc_id=rc_id,
        items=items_tuple,
        generated_at=_now(),
    )


# --------------------------------------------------------------------------- #
# T3：四角色签署矩阵（状态不含 AI 生成的 RECORDED）                                 #
# --------------------------------------------------------------------------- #
class SignoffMatrixStatus(str, Enum):
    """四角色签署矩阵状态（**RECORDED 必须由真实人工产生**）。

    ``RECORDED`` 的 ``recorded_by`` 必须非空（真实 USER）；AI 不得在无人留痕时
    把角色标为已签署（红线③⑨）。
    """

    MISSING = "missing"
    RECORDED = "recorded"
    CONFLICTING = "conflicting"


@dataclass(frozen=True)
class SignoffMatrixEntry:
    """四角色签署矩阵中的单角色条目（T3）。"""

    role: SignoffRole
    status: SignoffMatrixStatus
    recorded_by: Optional[str] = None  # 真实人工 ID；AI 不得填
    decision: Optional[str] = None  # 真实人工决策（go / no_go / need_more_evidence）
    conflict_note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role.value,
            "status": self.status.value,
            "recorded_by": self.recorded_by,
            "decision": self.decision,
            "conflict_note": self.conflict_note,
        }


@dataclass(frozen=True)
class FourRoleSignoffMatrix:
    """四角色签署矩阵（T3，只读聚合）。

    ``signoff_complete`` 为真**仅**当四角色全部 ``RECORDED`` 且决策为 ``go``；
    它仍**不**代表 Production GO，只是签署前置满足（红线⑤）。
    """

    matrix_id: str
    rc_id: str
    entries: Tuple[SignoffMatrixEntry, ...]
    generated_at: str
    note: str = (
        "SIGNOFF_MATRIX: 仅记录真实人工签署事实；AI 不构造 RECORDED；不宣布 GO"
    )

    def by_role(self, role: SignoffRole) -> Optional[SignoffMatrixEntry]:
        for entry in self.entries:
            if entry.role == role:
                return entry
        return None

    @property
    def missing_roles(self) -> Tuple[str, ...]:
        return tuple(
            e.role.value
            for e in self.entries
            if e.status is SignoffMatrixStatus.MISSING
        )

    @property
    def conflicting_roles(self) -> Tuple[str, ...]:
        return tuple(
            e.role.value
            for e in self.entries
            if e.status is SignoffMatrixStatus.CONFLICTING
        )

    @property
    def signoff_complete(self) -> bool:
        """四角色齐备且全部真实 GO（fail-closed）。"""
        effective = [e for e in self.entries if e.status is SignoffMatrixStatus.RECORDED]
        if len(effective) != len(REQUIRED_SIGNOFF_ROLES):
            return False
        return all(
            e.decision == SignoffDecision.GO.value and str(e.recorded_by or "").strip()
            for e in effective
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "matrix_id": self.matrix_id,
            "rc_id": self.rc_id,
            "entries": [e.to_dict() for e in self.entries],
            "missing_roles": list(self.missing_roles),
            "conflicting_roles": list(self.conflicting_roles),
            "signoff_complete": self.signoff_complete,
            "generated_at": self.generated_at,
            "note": self.note,
        }


def build_four_role_signoff_matrix(
    *,
    matrix_id: str,
    rc_id: str,
    entries: Sequence[SignoffMatrixEntry],
) -> FourRoleSignoffMatrix:
    """构建四角色签署矩阵（fail-closed）。

    * 角色集合必须等于 ``REQUIRED_SIGNOFF_ROLES``（四角色，不可缺）；
    * ``RECORDED`` 必须有真实 ``recorded_by`` 留痕（红线③⑨）。
    """
    entries_tuple = tuple(entries)
    if {e.role.value for e in entries_tuple} != set(REQUIRED_SIGNOFF_ROLES):
        raise FinalReviewError(
            f"signoff matrix 角色集合必须为 {REQUIRED_SIGNOFF_ROLES}，"
            f"实得 {sorted(e.role.value for e in entries_tuple)}"
        )
    for entry in entries_tuple:
        if entry.status is SignoffMatrixStatus.RECORDED:
            if not str(entry.recorded_by or "").strip():
                raise FinalReviewError(
                    f"role {entry.role.value} 标记为 RECORDED 但无 recorded_by "
                    f"真实人工留痕（红线③⑨）"
                )
    return FourRoleSignoffMatrix(
        matrix_id=matrix_id,
        rc_id=rc_id,
        entries=entries_tuple,
        generated_at=_now(),
    )


# --------------------------------------------------------------------------- #
# T4：人工签署冲突检测器（仅输出候选，不自动解决）                                  #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SignoffConflictCandidate:
    """一条签署冲突候选（T4，只读标记）。

    本结构**只标记**冲突，绝不自动解决、绝不代判（红线⑨⑩）。
    """

    candidate_id: str
    role: str
    kind: str  # 冲突种类：decision_conflict / scope_unreviewed / missing_evidence / data_integrity
    detail: str
    severity: str = "high"
    detected_at: str = field(default_factory=_now)
    note: str = "CONFLICT_CANDIDATE_ONLY: 仅标记，不自动解决、不代判"


class HumanSignoffConflictDetector:
    """人工签署冲突检测器（T4）：只输出 ``SignoffConflictCandidate``，不解决任何冲突。"""

    def detect(
        self,
        *,
        signoff_entries: Sequence[SignoffMatrixEntry],
        completeness_items: Sequence[CompletenessItem] = (),
        signoff_snapshot: Optional[HumanSignoffRegistrySnapshot] = None,
    ) -> Tuple[SignoffConflictCandidate, ...]:
        """根据签署矩阵 / 完整性矩阵 / 登记簿快照，输出冲突候选列表。

        **仅标记**：不修改任何人工记录、不自动重生成评审包、不下任何裁决。
        """
        candidates: List[SignoffConflictCandidate] = []

        for entry in signoff_entries:
            if entry.status is SignoffMatrixStatus.CONFLICTING:
                candidates.append(
                    SignoffConflictCandidate(
                        candidate_id=f"conflict-{entry.role.value}-conflicting",
                        role=entry.role.value,
                        kind="decision_conflict",
                        detail=entry.conflict_note
                        or f"角色 {entry.role.value} 存在未解决冲突",
                    )
                )
            if (
                entry.status is SignoffMatrixStatus.RECORDED
                and not str(entry.recorded_by or "").strip()
            ):
                candidates.append(
                    SignoffConflictCandidate(
                        candidate_id=f"conflict-{entry.role.value}-no-actor",
                        role=entry.role.value,
                        kind="data_integrity",
                        detail=f"角色 {entry.role.value} 标记为 RECORDED 却无 recorded_by 留痕",
                        severity="critical",
                    )
                )

        for item in completeness_items:
            if (
                item.status is CompletenessStatus.HUMAN_REVIEWED
                and not str(item.reviewed_by or "").strip()
            ):
                candidates.append(
                    SignoffConflictCandidate(
                        candidate_id=f"conflict-{item.item_kind}-no-reviewer",
                        role=item.item_kind,
                        kind="data_integrity",
                        detail=f"证据项 {item.item_kind} 标记为 HUMAN_REVIEWED 却无 reviewed_by 留痕",
                        severity="critical",
                    )
                )

        if signoff_snapshot is not None and signoff_snapshot.blocking_roles:
            candidates.append(
                SignoffConflictCandidate(
                    candidate_id="conflict-signoff-blocking-roles",
                    role=",".join(signoff_snapshot.blocking_roles),
                    kind="decision_conflict",
                    detail=(
                        "以下责任角色作出阻断性裁决（NO_GO / 需补证据）："
                        + ", ".join(signoff_snapshot.blocking_roles)
                    ),
                )
            )

        return tuple(candidates)


# --------------------------------------------------------------------------- #
# T5：激活证据漂移检测器（快照 vs 当前 repo，REVIEW_INVALIDATED_BY_DRIFT）          #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class EvidenceDriftFinding:
    """一条证据漂移发现（T5，只读标记）。

    ``invalidates_review`` 为真表示该项漂移使既有评审包失效（REVIEW_INVALIDATED_BY_DRIFT）。
    本结构**只报告**，不自动整改、不自动重生成评审包（红线⑨⑩）。
    """

    finding_id: str
    fact_kind: str
    expected_sha256: Optional[str]
    actual_sha256: Optional[str]
    drifted: bool
    invalidates_review: bool
    detail: str
    detected_at: str = field(default_factory=_now)
    note: str = "DRIFT_FINDING_ONLY: 仅报告；不自动整改、不自动重生成评审包"


class ActivationEvidenceDriftDetector:
    """激活证据漂移检测器（T5）：对比快照哈希与当前事实哈希，仅输出发现。"""

    def detect(
        self,
        *,
        snapshot: FinalReviewEvidenceSnapshot,
        current_facts: Mapping[str, Mapping[str, Any]],
    ) -> Tuple[EvidenceDriftFinding, ...]:
        """逐事实比对其在快照中的哈希与当前哈希。

        * 快照中 ``present`` 的事实，若当前缺失或哈希不一致 → 漂移；
        * 漂移且该项属于必需事实（在 ``current_facts`` 标记为 ``required``）时，
          ``invalidates_review`` 为真 → 触发 ``REVIEW_INVALIDATED_BY_DRIFT``。
        **仅报告**，不做任何修复动作。
        """
        findings: List[EvidenceDriftFinding] = []
        for fact in snapshot.facts:
            if not fact.present:
                continue
            current = current_facts.get(fact.fact_kind)
            if current is None:
                findings.append(
                    EvidenceDriftFinding(
                        finding_id=f"drift-{fact.fact_kind}-missing",
                        fact_kind=fact.fact_kind,
                        expected_sha256=fact.sha256,
                        actual_sha256=None,
                        drifted=True,
                        invalidates_review=bool(current_facts.get("__required__", ()))
                        and fact.fact_kind
                        in current_facts.get("__required__", ()),
                        detail=f"快照存在事实 {fact.fact_kind}，但当前仓库已无该事实",
                    )
                )
                continue
            actual_sha = current.get("sha256")
            drifted = bool(actual_sha) and bool(fact.sha256) and actual_sha != fact.sha256
            if drifted:
                required = current.get("required", False)
                findings.append(
                    EvidenceDriftFinding(
                        finding_id=f"drift-{fact.fact_kind}-hash",
                        fact_kind=fact.fact_kind,
                        expected_sha256=fact.sha256,
                        actual_sha256=actual_sha,
                        drifted=True,
                        invalidates_review=bool(required),
                        detail=(
                            f"事实 {fact.fact_kind} 哈希漂移："
                            f"期望 {fact.sha256}, 实得 {actual_sha}"
                        ),
                    )
                )
        return tuple(findings)


# --------------------------------------------------------------------------- #
# T6：最终激活评审包（含 SourceTrace，复用 FinalActivationReviewPackage 模式）       #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class FinalReviewSourceTrace:
    """本评审包的来源 lineage（T6，只读）。

    记录评审包由哪些输入（快照 / 矩阵 / 评审包 / git head）派生，**不含原文**。
    """

    review_package_id: str
    snapshot_id: Optional[str]
    completeness_matrix_id: Optional[str]
    signoff_matrix_id: Optional[str]
    generated_by_module: str
    git_head: str
    engineering_enabled_at_generation: bool
    derived_from: Tuple[str, ...] = field(default_factory=tuple)
    note: str = "SOURCE_TRACE: 记录本评审包来源 lineage；不含原文"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "review_package_id": self.review_package_id,
            "snapshot_id": self.snapshot_id,
            "completeness_matrix_id": self.completeness_matrix_id,
            "signoff_matrix_id": self.signoff_matrix_id,
            "generated_by_module": self.generated_by_module,
            "git_head": self.git_head,
            "engineering_enabled_at_generation": self.engineering_enabled_at_generation,
            "derived_from": list(self.derived_from),
            "note": self.note,
        }


@dataclass(frozen=True)
class FinalActivationReviewPacket:
    """最终激活评审包（T6，只读材料 + SourceTrace）。

    内部复用 Phase 3.9.6 的 ``FinalActivationReviewPackage`` 作为材料主体，并叠加
    ``FinalReviewSourceTrace``。评审包本身**不含任何裁决**（红线⑤⑨）。
    """

    packet_id: str
    rc_id: str
    generated_at: str
    generated_for_actor: str
    review_package: FinalActivationReviewPackage
    source_trace: FinalReviewSourceTrace
    completeness_matrix_id: Optional[str] = None
    signoff_matrix_id: Optional[str] = None
    snapshot_id: Optional[str] = None
    readiness_evaluation_id: Optional[str] = None
    note: str = (
        "REVIEW_PACKET: 复用 FinalActivationReviewPackage 模式 + SourceTrace；不含裁决"
    )
    human_action_required: str = (
        "请四位责任角色线下独立复核后，由主理人在人类终端作出 GO / NO-GO 裁决；AI 不参与"
    )

    def __post_init__(self) -> None:
        if not isinstance(self.review_package, FinalActivationReviewPackage):
            raise FinalReviewError(
                "review_packet 必须包裹真实 FinalActivationReviewPackage"
            )
        if self.source_trace.engineering_enabled_at_generation is not False:
            raise FinalReviewError(
                "生成评审包时 engineering_enabled 必须为 False（红线①）"
            )
        # 复核材料包自身红线（材料若已越权，评审包不得成立其上）。
        self.review_package.assert_no_activation_conclusion()

    def assert_no_activation_conclusion(self) -> None:
        """确认评审包未携带任何放行结论（红线②⑤）。"""
        self.review_package.assert_no_activation_conclusion()
        payload = self.to_dict()
        hits = _scan_forbidden_tokens(payload)
        if hits:
            raise FinalReviewError(
                "评审包出现放行类结论词元（红线②⑤）: " + "; ".join(sorted(hits))
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "packet_id": self.packet_id,
            "rc_id": self.rc_id,
            "generated_at": self.generated_at,
            "generated_for_actor": self.generated_for_actor,
            "review_package": self.review_package.to_dict(),
            "source_trace": self.source_trace.to_dict(),
            "completeness_matrix_id": self.completeness_matrix_id,
            "signoff_matrix_id": self.signoff_matrix_id,
            "snapshot_id": self.snapshot_id,
            "readiness_evaluation_id": self.readiness_evaluation_id,
            "note": self.note,
            "human_action_required": self.human_action_required,
        }


def build_final_activation_review_packet(
    *,
    packet_id: str,
    rc_id: str,
    generated_for_actor: str,
    evidence_summary: Mapping[str, Any],
    signoff_snapshot: HumanSignoffRegistrySnapshot,
    submissions: Sequence[Any] = (),
    gate_snapshot: Optional[Mapping[str, Any]] = None,
    decision_log_size: int = 0,
    required_submission_ids: Sequence[str] = (),
    scope_gaps: Optional[Mapping[str, Tuple[str, ...]]] = None,
    snapshot_id: Optional[str] = None,
    completeness_matrix_id: Optional[str] = None,
    signoff_matrix_id: Optional[str] = None,
    readiness_evaluation_id: Optional[str] = None,
    git_head: str = "",
    package_id: Optional[str] = None,
) -> FinalActivationReviewPacket:
    """构建最终激活评审包（T6）：内部复用 3.9.6 评审包工厂 + SourceTrace。

    构建期强制红线前置：``safety_invariants_ok()`` 与 ``engineering_enabled is False``；
    输出自扫描放行类词元（红线②⑤）。不产出半成品、不承载裁决。
    """
    if not safety_invariants_ok():
        raise FinalReviewError(
            "safety_invariants_ok() 失败：禁止在启用态下生成最终评审包（红线①）"
        )
    engineering_enabled = load_engineering_enabled()
    if engineering_enabled is not False:
        raise FinalReviewError(
            f"engineering_enabled 必须为 False，实测 {engineering_enabled!r}（红线①）"
        )

    inner_pkg = build_final_activation_review_package(
        package_id=package_id or f"{packet_id}:pkg",
        rc_id=rc_id,
        generated_for_actor=generated_for_actor,
        evidence_summary=evidence_summary,
        signoff_snapshot=signoff_snapshot,
        submissions=submissions,
        gate_snapshot=gate_snapshot,
        decision_log_size=decision_log_size,
        required_submission_ids=required_submission_ids,
        scope_gaps=scope_gaps,
    )

    trace = FinalReviewSourceTrace(
        review_package_id=inner_pkg.package_id,
        snapshot_id=snapshot_id,
        completeness_matrix_id=completeness_matrix_id,
        signoff_matrix_id=signoff_matrix_id,
        generated_by_module="agents.enterprise.production_release.final_review",
        git_head=git_head,
        engineering_enabled_at_generation=engineering_enabled,
        derived_from=tuple(
            x
            for x in (
                f"snapshot:{snapshot_id}" if snapshot_id else None,
                f"completeness:{completeness_matrix_id}" if completeness_matrix_id else None,
                f"signoff:{signoff_matrix_id}" if signoff_matrix_id else None,
            )
            if x
        ),
    )

    return FinalActivationReviewPacket(
        packet_id=packet_id,
        rc_id=rc_id,
        generated_at=_now(),
        generated_for_actor=generated_for_actor,
        review_package=inner_pkg,
        source_trace=trace,
        completeness_matrix_id=completeness_matrix_id,
        signoff_matrix_id=signoff_matrix_id,
        snapshot_id=snapshot_id,
        readiness_evaluation_id=readiness_evaluation_id,
    )


# --------------------------------------------------------------------------- #
# T7：最终评审就绪度评估（状态不含 GO/APPROVED/ACTIVATED/engineering_approved）      #
# --------------------------------------------------------------------------- #
class FinalReviewReadiness(str, Enum):
    """最终评审就绪度（**刻意不含任何放行终态**）。

    能表达的最高就绪度只有 ``READY_FOR_HUMAN_GO_NO_GO_REVIEW``（"材料齐了，请人来判"）。
    最终 GO 裁决只能发生在本评估**之外**、由真实自然人在人类终端做出（红线⑤）。
    """

    BLOCKED = "blocked"
    EVIDENCE_INCOMPLETE = "evidence_incomplete"
    SIGNOFF_INCOMPLETE = "signoff_incomplete"
    SIGNOFF_CONFLICT = "signoff_conflict"
    DRIFT_DETECTED = "drift_detected"
    READY_FOR_HUMAN_GO_NO_GO_REVIEW = "ready_for_human_go_no_go_review"


ALLOWED_FINAL_REVIEW_READINESS = frozenset(FinalReviewReadiness)


@dataclass(frozen=True)
class FinalReviewReadinessEvaluation:
    """最终评审就绪度评估（T7，只读事实）。

    ``state`` 取值集合不含任何放行语义；本结构不翻转 ``engineering_enabled``、
    不宣布 GO（红线②⑤）。
    """

    evaluation_id: str
    rc_id: str
    state: FinalReviewReadiness
    evaluated_at: str
    reasons: Tuple[str, ...]
    underlying: Dict[str, Any]
    engineering_enabled_false: bool
    human_action_required: str
    note: str = (
        "READINESS_EVAL: 仅评估就绪态；不含 GO/APPROVED/ACTIVATED；"
        "不翻转 engineering_enabled"
    )

    def __post_init__(self) -> None:
        if self.state not in ALLOWED_FINAL_REVIEW_READINESS:
            raise FinalReviewError(f"readiness state {self.state!r} 不在允许集合内")
        if self.engineering_enabled_false is not True:
            raise FinalReviewError(
                "就绪度评估必须断言 engineering_enabled=False（红线①）"
            )
        payload = self.to_dict()
        hits = _scan_forbidden_tokens(payload)
        if hits:
            raise FinalReviewError(
                "就绪度评估出现放行类词元（红线②⑤）: " + "; ".join(sorted(hits))
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evaluation_id": self.evaluation_id,
            "rc_id": self.rc_id,
            "state": self.state.value,
            "evaluated_at": self.evaluated_at,
            "reasons": list(self.reasons),
            "underlying": dict(self.underlying),
            "engineering_enabled_false": self.engineering_enabled_false,
            "human_action_required": self.human_action_required,
            "note": self.note,
        }


class FinalReviewReadinessEvaluator:
    """最终评审就绪度评估器（T7）：按"最差事实优先"归并就绪态。

    优先级（由重到轻）：
    ``BLOCKED`` > ``DRIFT_DETECTED`` > ``SIGNOFF_CONFLICT``
        > ``SIGNOFF_INCOMPLETE`` > ``EVIDENCE_INCOMPLETE``
        > ``READY_FOR_HUMAN_GO_NO_GO_REVIEW``
    """

    def evaluate(
        self,
        *,
        completeness: ActivationEvidenceCompletenessMatrix,
        signoff: FourRoleSignoffMatrix,
        conflicts: Sequence[SignoffConflictCandidate] = (),
        drift: Sequence[EvidenceDriftFinding] = (),
        blocked: bool = False,
    ) -> FinalReviewReadiness:
        if blocked:
            return FinalReviewReadiness.BLOCKED
        if any(f.drifted for f in drift):
            return FinalReviewReadiness.DRIFT_DETECTED
        if conflicts:
            return FinalReviewReadiness.SIGNOFF_CONFLICT
        if not signoff.signoff_complete:
            return FinalReviewReadiness.SIGNOFF_INCOMPLETE
        if not completeness.is_evidence_complete:
            return FinalReviewReadiness.EVIDENCE_INCOMPLETE
        return FinalReviewReadiness.READY_FOR_HUMAN_GO_NO_GO_REVIEW

    def build_evaluation(
        self,
        *,
        evaluation_id: str,
        rc_id: str,
        completeness: ActivationEvidenceCompletenessMatrix,
        signoff: FourRoleSignoffMatrix,
        conflicts: Sequence[SignoffConflictCandidate] = (),
        drift: Sequence[EvidenceDriftFinding] = (),
        blocked: bool = False,
    ) -> FinalReviewReadinessEvaluation:
        state = self.evaluate(
            completeness=completeness,
            signoff=signoff,
            conflicts=conflicts,
            drift=drift,
            blocked=blocked,
        )
        reasons: List[str] = []
        if state is FinalReviewReadiness.DRIFT_DETECTED:
            reasons.append(
                "检测到证据漂移（REVIEW_INVALIDATED_BY_DRIFT），既有评审包失效"
            )
        if conflicts:
            reasons.append(f"存在 {len(conflicts)} 条签署冲突候选，须人工消解")
        if not signoff.signoff_complete:
            reasons.append(
                "四角色真实签署未齐备（缺失："
                + ", ".join(signoff.missing_roles or ("无",))
                + "）"
            )
        if not completeness.is_evidence_complete:
            reasons.append(
                "激活证据未全部达到 HUMAN_REVIEWED（缺失："
                + ", ".join(completeness.missing_items or ("无",))
                + "）"
            )
        if state is FinalReviewReadiness.READY_FOR_HUMAN_GO_NO_GO_REVIEW:
            reasons.append("材料齐备、签署齐备、无冲突无漂移，可供主理人作 GO/NO-GO 裁决")

        engineering_enabled = load_engineering_enabled()
        return FinalReviewReadinessEvaluation(
            evaluation_id=evaluation_id,
            rc_id=rc_id,
            state=state,
            evaluated_at=_now(),
            reasons=tuple(reasons),
            underlying={
                "completeness_complete": completeness.is_evidence_complete,
                "missing_evidence_items": list(completeness.missing_items),
                "signoff_complete": signoff.signoff_complete,
                "missing_roles": list(signoff.missing_roles),
                "conflict_count": len(conflicts),
                "drift_count": sum(1 for f in drift if f.drifted),
            },
            engineering_enabled_false=engineering_enabled is False,
            human_action_required=(
                "请主理人携四角色真实签署与证据，在人类终端作出 GO / NO-GO 裁决；"
                "本评估不代替该裁决（红线②④⑩）"
            ),
        )


# --------------------------------------------------------------------------- #
# T8：最终生产裁决（复用 final_decision.py，不重造）                                #
# --------------------------------------------------------------------------- #
#: T8 复用的裁决原语（来自 Phase 3.9.6 final_decision.py，AI 不得越权使用）。
FinalProductionDecisionRecord = FinalHumanActivationDecision
FinalProductionDecisionOutcome = FinalDecisionOutcome
FinalProductionDecisionError = FinalHumanDecisionError
build_final_production_decision = build_final_human_activation_decision

#: AI 禁止代行的最终裁决动作（结构性拦截清单，仅文档化；真实拦截在 final_decision）。
FORBIDDEN_PRODUCTION_DECISION_TOKENS: Tuple[str, ...] = (
    "create_go_decision",
    "auto_go",
    "approve_release",
    "sign_for_owner",
    "declare_production_go",
    "enable_engineering",
    "activate",
)


# --------------------------------------------------------------------------- #
# T9：人工最终裁决校验（VALID/INVALID/PENDING，VALID 也不开 engineering_enabled）   #
# --------------------------------------------------------------------------- #
class DecisionVerificationStatus(str, Enum):
    """人工最终裁决校验结果（**不含任何放行语义**）。"""

    VALID = "valid"
    INVALID = "invalid"
    PENDING = "pending"


@dataclass(frozen=True)
class HumanFinalDecisionVerification:
    """人工最终裁决校验结果（T9，只读）。

    ``engineering_enabled_remains_false`` 必须恒为 True —— **即便校验 VALID，
    也绝不翻转 ``engineering_enabled``、不宣布上线**（红线①⑤）。
    """

    verification_id: str
    rc_id: str
    decision_id: str
    status: DecisionVerificationStatus
    reasons: Tuple[str, ...]
    verified_at: str
    engineering_enabled_remains_false: bool
    note: str = (
        "DECISION_VERIFICATION: 仅校验登记有效性；VALID 也不翻转 "
        "engineering_enabled、不激活"
    )

    def __post_init__(self) -> None:
        if self.engineering_enabled_remains_false is not True:
            raise FinalReviewError(
                "裁决校验必须断言 engineering_enabled 仍为 False（红线①）"
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verification_id": self.verification_id,
            "rc_id": self.rc_id,
            "decision_id": self.decision_id,
            "status": self.status.value,
            "reasons": list(self.reasons),
            "verified_at": self.verified_at,
            "engineering_enabled_remains_false": self.engineering_enabled_remains_false,
            "note": self.note,
        }


class HumanFinalDecisionVerifier:
    """人工最终裁决校验器（T9）：只校验"登记是否有效"，绝不代决、绝不激活。

    即便校验通过（``VALID``），也**不**翻转 ``engineering_enabled``、不宣布 GO ——
    激活由主理人在人类终端显式执行（红线①⑤）。
    """

    def verify(
        self,
        *,
        decision: Optional[FinalHumanActivationDecision],
        package: FinalActivationReviewPackage,
        readiness: Optional[FinalReviewReadiness] = None,
    ) -> HumanFinalDecisionVerification:
        reasons: List[str] = []
        if decision is None:
            return self._invalid(
                rc_id=package.rc_id,
                decision_id="",
                reasons=("未提供真实人工最终裁决记录",),
            )

        if not decision.decided_by_real_user:
            reasons.append("裁决非真实自然人作出（decided_by_kind != 'user'，红线③⑨）")
        if decision.engineering_enabled_at_decision is not False:
            reasons.append("裁决登记时 engineering_enabled 为真（红线①）")
        if not decision.binds_to(package):
            reasons.append("裁决绑定的评审包与当前材料不一致（材料已变更）")
        if (
            decision.is_go
            and package.readiness is not ReviewPackageReadiness.READY_FOR_HUMAN_FINAL_REVIEW
        ):
            reasons.append(
                "GO 裁决所依据的评审包未达 READY_FOR_HUMAN_FINAL_REVIEW（红线④⑩）"
            )
        if readiness is not None and readiness not in (
            FinalReviewReadiness.READY_FOR_HUMAN_GO_NO_GO_REVIEW,
            FinalReviewReadiness.BLOCKED,
            FinalReviewReadiness.EVIDENCE_INCOMPLETE,
            FinalReviewReadiness.SIGNOFF_INCOMPLETE,
            FinalReviewReadiness.SIGNOFF_CONFLICT,
            FinalReviewReadiness.DRIFT_DETECTED,
        ):
            reasons.append("就绪度状态非法")

        engineering_enabled = load_engineering_enabled()
        if engineering_enabled is not False:
            reasons.append(f"当前 engineering_enabled={engineering_enabled!r}（红线①）")

        if reasons:
            return self._invalid(
                rc_id=package.rc_id,
                decision_id=decision.decision_id,
                reasons=tuple(reasons),
            )
        return HumanFinalDecisionVerification(
            verification_id=f"vf-{decision.decision_id}",
            rc_id=package.rc_id,
            decision_id=decision.decision_id,
            status=DecisionVerificationStatus.VALID,
            reasons=("裁决登记有效：真实自然人、材料绑定一致、GO 材料齐备",),
            verified_at=_now(),
            engineering_enabled_remains_false=True,
        )

    def _invalid(
        self, *, rc_id: str, decision_id: str, reasons: Tuple[str, ...]
    ) -> HumanFinalDecisionVerification:
        return HumanFinalDecisionVerification(
            verification_id=f"vf-{decision_id or 'none'}",
            rc_id=rc_id,
            decision_id=decision_id,
            status=DecisionVerificationStatus.INVALID,
            reasons=reasons,
            verified_at=_now(),
            engineering_enabled_remains_false=True,
        )


# --------------------------------------------------------------------------- #
# T10：生产激活交接包（execution_status 恒 pending，禁部署）                        #
# --------------------------------------------------------------------------- #
class HandoffExecutionStatus(str, Enum):
    """交接包执行态 —— 本模块能表达的取值只有一个。

    刻意只保留 ``PENDING_HUMAN_TERMINAL_ACTION``：任何"已激活 / 已部署"语义都不在
    软件层产生，只能是主理人在人类终端操作后的现实事实（红线①⑤）。
    """

    PENDING_HUMAN_TERMINAL_ACTION = "pending_human_terminal_action"


@dataclass(frozen=True)
class HandoffItem:
    """交接包中的单条交接项（T10）。"""

    item_id: str
    kind: str
    reference: str  # 引用坐标，非原文 / 非 secret
    ready: bool
    note: str = "HANDOFF_ITEM: 仅记录交接引用；不执行部署"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "kind": self.kind,
            "reference": self.reference,
            "ready": self.ready,
            "note": self.note,
        }


@dataclass(frozen=True)
class ProductionActivationHandoffPackage:
    """生产激活交接包（T10，只读交接材料）。

    ``execution_status`` 恒为 ``PENDING_HUMAN_TERMINAL_ACTION``；``engineering_enabled``
    恒为 False。**本包不部署、不激活、不翻转 engineering_enabled**（红线①⑤）。
    """

    handoff_id: str
    rc_id: str
    generated_at: str
    review_packet_id: str
    readiness_state: str
    execution_status: HandoffExecutionStatus = (
        HandoffExecutionStatus.PENDING_HUMAN_TERMINAL_ACTION
    )
    engineering_enabled_at_handoff: bool = False
    items: Tuple[HandoffItem, ...] = ()
    note: str = (
        "HANDOFF_PACKAGE: execution_status 恒 pending；不部署、不激活、"
        "不翻转 engineering_enabled"
    )

    def __post_init__(self) -> None:
        if self.execution_status is not (
            HandoffExecutionStatus.PENDING_HUMAN_TERMINAL_ACTION
        ):
            raise FinalReviewError(
                "交接包不得表达任何已激活 / 已部署语义（红线①⑤）"
            )
        if self.engineering_enabled_at_handoff is not False:
            raise FinalReviewError(
                "交接包生成时 engineering_enabled 必须为 False（红线①）"
            )
        payload = self.to_dict()
        hits = _scan_forbidden_tokens(payload)
        if hits:
            raise FinalReviewError(
                "交接包出现放行类词元（红线②⑤）: " + "; ".join(sorted(hits))
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "handoff_id": self.handoff_id,
            "rc_id": self.rc_id,
            "generated_at": self.generated_at,
            "review_packet_id": self.review_packet_id,
            "readiness_state": self.readiness_state,
            "execution_status": self.execution_status.value,
            "engineering_enabled_at_handoff": self.engineering_enabled_at_handoff,
            "items": [i.to_dict() for i in self.items],
            "note": self.note,
        }


def build_production_activation_handoff_package(
    *,
    handoff_id: str,
    rc_id: str,
    review_packet_id: str,
    readiness_state: str,
    items: Sequence[HandoffItem] = (),
) -> ProductionActivationHandoffPackage:
    """构建生产激活交接包（T10，fail-closed）。

    构建期强制红线前置；``execution_status`` 恒 pending，``engineering_enabled`` 恒 False。
    """
    if not safety_invariants_ok():
        raise FinalReviewError(
            "safety_invariants_ok() 失败：禁止在启用态下生成交接包（红线①）"
        )
    engineering_enabled = load_engineering_enabled()
    if engineering_enabled is not False:
        raise FinalReviewError(
            f"engineering_enabled 必须为 False，实测 {engineering_enabled!r}（红线①）"
        )
    return ProductionActivationHandoffPackage(
        handoff_id=handoff_id,
        rc_id=rc_id,
        generated_at=_now(),
        review_packet_id=review_packet_id,
        readiness_state=readiness_state,
        items=tuple(items),
    )


# --------------------------------------------------------------------------- #
# T11：激活中止条件目录（10 类，仅定义何时停止，不自动整改）                        #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ActivationAbortCondition:
    """单条激活中止条件（T11，只读定义）。

    ``auto_remediation_forbidden`` 恒为 True：本目录**只定义何时必须停止**，
    绝不自动整改、绝不自动恢复（红线⑨⑩）。
    """

    condition_id: str
    title: str
    description: str
    severity: str
    detection_hint: str
    auto_remediation_forbidden: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "condition_id": self.condition_id,
            "title": self.title,
            "description": self.description,
            "severity": self.severity,
            "detection_hint": self.detection_hint,
            "auto_remediation_forbidden": self.auto_remediation_forbidden,
        }


@dataclass(frozen=True)
class ActivationAbortConditionCatalog:
    """激活中止条件目录（T11，只读）。

    汇总 10 类中止条件；用于在最终评审与交接阶段做"是否必须 STOP"的判定依据。
    """

    catalog_id: str
    rc_id: str
    generated_at: str
    conditions: Tuple[ActivationAbortCondition, ...]
    note: str = (
        "ABORT_CATALOG: 仅定义何时必须停止；不自动整改、不自动恢复（红线⑨⑩）"
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "catalog_id": self.catalog_id,
            "rc_id": self.rc_id,
            "generated_at": self.generated_at,
            "condition_count": len(self.conditions),
            "conditions": [c.to_dict() for c in self.conditions],
            "note": self.note,
        }


#: Phase 3.9.7 的 10 类激活中止条件（不可自动整改）。
_ACTIVATION_ABORT_CONDITIONS: Tuple[ActivationAbortCondition, ...] = (
    ActivationAbortCondition(
        condition_id="ABORT_ENGINEERING_ENABLED_TRUE",
        title="engineering_enabled 被置为 true",
        description="全企业层激活开关被打开，任何激活动作都不得继续",
        severity="critical",
        detection_hint="load_engineering_enabled() is not False",
    ),
    ActivationAbortCondition(
        condition_id="ABORT_AUDIT_LEDGER_TAMPERED",
        title="审计账本完整性校验失败",
        description="Audit Ledger 重建 / 校验不通过，治理溯源不可信",
        severity="critical",
        detection_hint="audit_category_ledger_validator.py 返回非 PASS",
    ),
    ActivationAbortCondition(
        condition_id="ABORT_REQUIRED_SIGNOFF_MISSING",
        title="四角色真实签署缺失",
        description="production-owner / release-manager / security-owner / auditor 任一未签署",
        severity="critical",
        detection_hint="signoff_matrix.missing_roles 非空",
    ),
    ActivationAbortCondition(
        condition_id="ABORT_SIGNOFF_CONFLICT",
        title="存在未解决签署冲突",
        description="任一角色标记 CONFLICTING，或阻断性裁决未消解",
        severity="critical",
        detection_hint="conflict_detector 产出非空候选",
    ),
    ActivationAbortCondition(
        condition_id="ABORT_EVIDENCE_DRIFT",
        title="关键证据漂移",
        description="评审依据的关键事实哈希与当前仓库不一致（REVIEW_INVALIDATED_BY_DRIFT）",
        severity="critical",
        detection_hint="drift_detector 命中 invalidates_review=True",
    ),
    ActivationAbortCondition(
        condition_id="ABORT_REDLINE_ASSERTION_FALSE",
        title="红线断言出现 False",
        description="评审包 / 就绪度评估中的红线断言不为真",
        severity="critical",
        detection_hint="redline_assertions 任一为 False",
    ),
    ActivationAbortCondition(
        condition_id="ABORT_GO_ON_INCOMPLETE_PACKAGE",
        title="在评审包未完成时登记 GO",
        description="评审包未达 READY_FOR_HUMAN_FINAL_REVIEW 却登记 GO 裁决",
        severity="critical",
        detection_hint="decision.is_go 但 package.readiness 非 READY",
    ),
    ActivationAbortCondition(
        condition_id="ABORT_UNAUTHORIZED_ACTIVATION_ENDPOINT",
        title="检测到未授权激活端点调用",
        description="系统出现 /activate 或 /deploy-production 等端点请求",
        severity="critical",
        detection_hint="路由表中存在激活类端点（应不存在）",
    ),
    ActivationAbortCondition(
        condition_id="ABORT_SECRET_WRITTEN",
        title="检测到真实密钥被写入",
        description="任何真实密钥 / 凭证被写入代码或配置",
        severity="critical",
        detection_hint="硬编码扫描命中密钥模式",
    ),
    ActivationAbortCondition(
        condition_id="ABORT_AI_FINAL_DECISION",
        title="检测到 AI 尝试构造最终 GO 裁决",
        description="AI 越权生成 GO / 代签 / 宣布 Production GO",
        severity="critical",
        detection_hint="decided_by_kind != 'user' 或出现 forbidden token",
    ),
)


def build_activation_abort_condition_catalog(
    *, rc_id: str, catalog_id: Optional[str] = None
) -> ActivationAbortConditionCatalog:
    """构建激活中止条件目录（T11，只读定义）。"""
    return ActivationAbortConditionCatalog(
        catalog_id=catalog_id or f"abort-catalog-{rc_id}",
        rc_id=rc_id,
        generated_at=_now(),
        conditions=_ACTIVATION_ABORT_CONDITIONS,
    )


__all__ = [
    "FinalReviewError",
    "FINAL_REVIEW_EVIDENCE_FACT_KINDS",
    "FinalReviewEvidenceFact",
    "FinalReviewEvidenceSnapshot",
    "build_final_review_evidence_snapshot",
    "FINAL_REVIEW_COMPLETENESS_ITEMS",
    "CompletenessStatus",
    "CompletenessItem",
    "ActivationEvidenceCompletenessMatrix",
    "build_activation_evidence_completeness_matrix",
    "SignoffMatrixStatus",
    "SignoffMatrixEntry",
    "FourRoleSignoffMatrix",
    "build_four_role_signoff_matrix",
    "SignoffConflictCandidate",
    "HumanSignoffConflictDetector",
    "EvidenceDriftFinding",
    "ActivationEvidenceDriftDetector",
    "FinalReviewSourceTrace",
    "FinalActivationReviewPacket",
    "build_final_activation_review_packet",
    "FinalReviewReadiness",
    "FinalReviewReadinessEvaluation",
    "FinalReviewReadinessEvaluator",
    "FinalProductionDecisionRecord",
    "FinalProductionDecisionOutcome",
    "FinalProductionDecisionError",
    "build_final_production_decision",
    "FORBIDDEN_PRODUCTION_DECISION_TOKENS",
    "DecisionVerificationStatus",
    "HumanFinalDecisionVerification",
    "HumanFinalDecisionVerifier",
    "HandoffExecutionStatus",
    "HandoffItem",
    "ProductionActivationHandoffPackage",
    "build_production_activation_handoff_package",
    "ActivationAbortCondition",
    "ActivationAbortConditionCatalog",
    "build_activation_abort_condition_catalog",
]
