"""Phase 3.9.7 企业生产变更管控平面 —— 数据模型（T1–T9 / T23–T25）。

全部为**只读管控 / 仿真 / 证据包 / 候选 / 清单 / 回滚引用结构**：本模块不持有任何生产状态，
不写入任何密钥，不执行任何真实激活 / 真实授权 / 真实数据覆盖 / 真实部署 / 真实回滚 /
真实迁移 / 真实应用；所有 ``approved`` / ``completed`` / ``verified`` 类放行字段恒为
``False`` 或处于 ``*_FOR_HUMAN_REVIEW`` / ``HUMAN_DRAFTED`` / ``HUMAN_ABORTED`` 状态，
最终放行只能源于真实人工（production-owner / release-manager / security-owner / auditor）
线下签署 ``ChangeSignoff``（复用 ``production_release.models.SignoffRole`` / ``SignoffDecision``）。

本层**新增 13 个审计动作大类**（CHANGE_*），审计总数由 108 → 121；其余可审计动作复用
既有 ``record_user_action``（actor_kind 恒 USER）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

# reuse-not-duplicate：签署角色 / 决策语义与发布闸门层完全一致。
from agents.enterprise.production_release.models import (  # noqa: F401
    SignoffDecision,
    SignoffRole,
)


# --------------------------------------------------------------------------- #
# 枚举                                                                          #
# --------------------------------------------------------------------------- #
class ChangeExecutionMode(str, Enum):
    """变更执行模式（T1）。

    AI 只能构造 ``HUMAN_MANUAL``（真实自然人手操）或 ``EXTERNAL_CONTROLLED_SYSTEM``
    （受控外部系统代执行，仍须真实责任人触发）；``AI_AUTOMATIC`` **禁止**作为任何候选的
    执行模式（红线③/⑩：AI 不得自动执行生产变更）。
    """

    HUMAN_MANUAL = "human_manual"
    EXTERNAL_CONTROLLED_SYSTEM = "external_controlled_system"


class ChangeState(str, Enum):
    """变更状态（T1 / T23）。

    AI 只能构造 ``HUMAN_DRAFTED`` / ``AWAITING_HUMAN_REVIEW``；``HUMAN_COMPLETED`` 与
    ``HUMAN_ABORTED`` 只能由真实人工（主理人线下决策 / 签署 ChangeSignoff）产生，
    AI 不可进入。``AUTO_EXECUTING`` / ``AUTO_COMPLETED`` / ``AI_APPROVED`` **禁止**作为
    AI 终态（红线②/③/⑩）。
    """

    HUMAN_DRAFTED = "human_drafted"
    AWAITING_HUMAN_REVIEW = "awaiting_human_review"
    HUMAN_COMPLETED = "human_completed"
    HUMAN_ABORTED = "human_aborted"


class ChangePreflightStatus(str, Enum):
    """变更前预检状态（T4）。

    AI 只可产出 ``READY_FOR_HUMAN_REVIEW`` / ``BLOCKED`` / ``PENDING_VERIFICATION``；
    ``APPROVED`` / ``AUTO_APPROVED`` / ``ENGINEERING_APPROVED`` **禁止**作为 AI 终态
    （红线②/③/⑩）。
    """

    READY_FOR_HUMAN_REVIEW = "ready_for_human_review"
    BLOCKED = "blocked"
    PENDING_VERIFICATION = "pending_verification"


class ChangeVerificationStatus(str, Enum):
    """变更后验证状态（T8）。

    注意：AI **不得**把 ``PENDING_VERIFICATION`` 自动提升为 ``VERIFIED_BY_HUMAN``
    （红线⑩）。缺失真实人工核验的验证一律保持 ``PENDING_VERIFICATION``。
    """

    VERIFIED_BY_HUMAN = "verified_by_human"
    PENDING_VERIFICATION = "pending_verification"
    FAILED = "failed"


class ChangeDecisionDraftStatus(str, Enum):
    """变更裁决草稿状态（T9）。

    AI 只可产出 ``READY_FOR_HUMAN_GO_NO_GO`` / ``BLOCKED`` / ``NEEDS_MORE_EVIDENCE``；
    ``GO_LIVE_APPROVED`` **禁止**作为 AI 生成状态（红线②/⑧/⑩）。
    """

    READY_FOR_HUMAN_GO_NO_GO = "ready_for_human_go_no_go"
    BLOCKED = "blocked"
    NEEDS_MORE_EVIDENCE = "needs_more_evidence"


class ChangeSimulationOutcome(str, Enum):
    """受控仿真结果（T23）。

    仿真**永远是仿真**：``PASS`` / ``FAIL`` / ``BLOCKED`` 仅描述"在受控仿真环境里观察到
    的行为"，绝不描述真实生产变更结果；``is_simulation`` 恒 ``True``（红线⑨）。
    """

    PASS = "pass"
    FAIL = "fail"
    BLOCKED = "blocked"


# --------------------------------------------------------------------------- #
# T1：变更请求                                                                   #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ChangeRequest:
    """T1 变更请求：仅描述变更对象，不决策、不执行。

    ``change_approved`` 恒为 ``False``（fail-closed）；``state`` 取值只能由真实人工
    推进到 ``HUMAN_COMPLETED`` / ``HUMAN_ABORTED``，AI 只可造 ``HUMAN_DRAFTED`` /
    ``AWAITING_HUMAN_REVIEW``。``execution_mode`` 仅允许 ``HUMAN_MANUAL`` /
    ``EXTERNAL_CONTROLLED_SYSTEM``，AI 不得把自身标为执行方。
    """

    change_id: str
    title: str
    description: str
    requested_by: str  # 真实 USER actor_id
    execution_mode: ChangeExecutionMode = ChangeExecutionMode.HUMAN_MANUAL
    state: ChangeState = ChangeState.HUMAN_DRAFTED
    change_approved: bool = False  # fail-closed：AI 路径恒 False
    created_at: str = ""
    note: str = (
        "CHANGE_REQUEST_ONLY: 变更请求仅描述变更对象，不执行；最终执行须主理人在"
        "人类终端、四角色签署后显式发起"
    )

    def to_dict(self) -> Dict[str, object]:
        return {
            "change_id": self.change_id,
            "title": self.title,
            "description": self.description,
            "requested_by": self.requested_by,
            "execution_mode": self.execution_mode.value,
            "state": self.state.value,
            "change_approved": self.change_approved,
            "created_at": self.created_at,
            "note": self.note,
        }


# --------------------------------------------------------------------------- #
# T2：变更计划                                                                   #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ChangePlan:
    """T2 变更计划：仅描述步骤与回滚预案引用，不执行。"""

    change_id: str
    plan_reference: str
    rollback_plan_reference: str
    steps: List[str] = field(default_factory=list)
    state: ChangeState = ChangeState.HUMAN_DRAFTED
    created_at: str = ""
    note: str = "CHANGE_PLAN_ONLY: 描述步骤与回滚预案引用，不执行真实变更"

    def to_dict(self) -> Dict[str, object]:
        return {
            "change_id": self.change_id,
            "plan_reference": self.plan_reference,
            "rollback_plan_reference": self.rollback_plan_reference,
            "steps": list(self.steps),
            "state": self.state.value,
            "created_at": self.created_at,
            "note": self.note,
        }


# --------------------------------------------------------------------------- #
# T3：变更窗口                                                                   #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ChangeWindow:
    """T3 变更窗口：真实 USER 预约的维护时段（只读登记）。"""

    change_id: str
    window_start: str
    window_end: str
    reserved_by: str  # 真实 USER actor_id
    state: ChangeState = ChangeState.HUMAN_DRAFTED
    created_at: str = ""
    note: str = "CHANGE_WINDOW_ONLY: 维护时段预约登记，不触发任何执行"

    def to_dict(self) -> Dict[str, object]:
        return {
            "change_id": self.change_id,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "reserved_by": self.reserved_by,
            "state": self.state.value,
            "created_at": self.created_at,
            "note": self.note,
        }


# --------------------------------------------------------------------------- #
# T4：变更前预检                                                                 #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ChangePreflightResult:
    """T4 变更前预检结果：AI 只产出 READY_FOR_HUMAN_REVIEW / BLOCKED /
    PENDING_VERIFICATION；绝不产出 APPROVED / AUTO_APPROVED / ENGINEERING_APPROVED。
    """

    status: ChangePreflightStatus
    checks: Dict[str, bool] = field(default_factory=dict)
    missing: List[str] = field(default_factory=list)
    note: str = (
        "PREFLIGHT_ONLY: AI 不直接返回 APPROVED；最终放行须真实 ChangeSignoff 组合决定"
    )

    def to_dict(self) -> Dict[str, object]:
        return {
            "status": self.status.value,
            "checks": dict(self.checks),
            "missing": list(self.missing),
            "note": self.note,
        }


# --------------------------------------------------------------------------- #
# T5：变更检查点                                                                 #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ChangeCheckpoint:
    """T5 变更检查点：真实 USER 在执行过程中记录的里程碑（只读留痕）。"""

    checkpoint_id: str
    change_id: str
    recorded_by: str  # 真实 USER actor_id
    note: str = ""
    timestamp: str = ""
    note_meta: str = "CHECKPOINT_ONLY: 人工记录的变更里程碑，不触发任何动作"

    def to_dict(self) -> Dict[str, object]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "change_id": self.change_id,
            "recorded_by": self.recorded_by,
            "note": self.note,
            "timestamp": self.timestamp,
            "note_meta": self.note_meta,
        }


# --------------------------------------------------------------------------- #
# T6：中止策略                                                                   #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ChangeAbortPolicy:
    """T6 中止策略：明确「自动中止条件 + 必须人工中止」约束（fail-closed）。

    ``human_abort_required`` 恒 ``True``：AI 不得自动中止真实生产变更（红线③/⑩）；
    中止只能源于真实人工在终端显式动作。
    """

    change_id: str
    auto_abort_conditions: List[str] = field(default_factory=list)
    human_abort_required: bool = True  # fail-closed：AI 不得自动中止
    note: str = "ABORT_POLICY_ONLY: 仅描述中止约束，AI 不执行任何中止动作"

    def to_dict(self) -> Dict[str, object]:
        return {
            "change_id": self.change_id,
            "auto_abort_conditions": list(self.auto_abort_conditions),
            "human_abort_required": self.human_abort_required,
            "note": self.note,
        }


# --------------------------------------------------------------------------- #
# T7：回滚引用                                                                   #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ChangeRollbackReference:
    """T7 回滚引用：记录 last_known_good 版本 / commit / 数据库修订 / 配置基线 /
    回滚步骤与恢复校验引用。

    本阶段**不真正执行** production rollback；只验证回滚引用是否完整。
    """

    change_id: str
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
            "change_id": self.change_id,
            "last_known_good_version": self.last_known_good_version,
            "last_known_good_commit": self.last_known_good_commit,
            "database_revision": self.database_revision,
            "config_baseline": self.config_baseline,
            "rollback_steps_reference": self.rollback_steps_reference,
            "recovery_validation_reference": self.recovery_validation_reference,
            "verified": self.verified,
            "note": self.note,
        }


# --------------------------------------------------------------------------- #
# T8：变更后验证                                                                 #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PostChangeVerification:
    """T8 变更后验证：描述待验证项与状态。

    ``status`` 初始由真实来源决定；AI 不得把 ``PENDING_VERIFICATION`` 自动提升为
    ``VERIFIED_BY_HUMAN``（红线⑩）。``verified_by`` 仅可填入真实 USER actor_id。
    """

    verification_id: str
    change_id: str
    verification_type: str
    status: ChangeVerificationStatus = ChangeVerificationStatus.PENDING_VERIFICATION
    verified_by: Optional[str] = None  # 仅真实 USER actor_id
    detail: str = ""
    note: str = (
        "POST_VERIFICATION_ONLY: AI 不替人验证；VERIFIED_BY_HUMAN 须真实 USER 核验"
    )

    def to_dict(self) -> Dict[str, object]:
        return {
            "verification_id": self.verification_id,
            "change_id": self.change_id,
            "verification_type": self.verification_type,
            "status": self.status.value,
            "verified_by": self.verified_by,
            "detail": self.detail,
            "note": self.note,
        }


# --------------------------------------------------------------------------- #
# T9：变更证据                                                                   #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ChangeEvidence:
    """T9 变更证据：可关联 phase / artifact / test_result / security_scan /
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
    integrity_status: str = "pending"  # intact | pending | tampered | unknown
    verification_status: str = "pending_verification"
    change_id: Optional[str] = None
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
    sha256: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "evidence_id": self.evidence_id,
            "evidence_type": self.evidence_type,
            "source": self.source,
            "source_reference": self.source_reference,
            "created_at": self.created_at,
            "integrity_status": self.integrity_status,
            "verification_status": self.verification_status,
            "change_id": self.change_id,
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
# T23：受控仿真结果                                                             #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ChangeSimulationResult:
    """T23 受控仿真结果：永远是仿真（``is_simulation`` 恒 ``True``，红线⑨）。

    ``outcome`` 仅描述"在受控仿真环境里观察到的行为"，绝不描述真实生产变更结果；
    本结构**不**执行任何真实变更、不翻转 ``engineering_enabled``、不宣布 GO。
    """

    simulation_id: str
    change_id: str
    scenario: str
    outcome: ChangeSimulationOutcome
    is_simulation: bool = True  # 恒 True：仿真≠真实变更
    detail: str = ""
    note: str = (
        "SIMULATION_ONLY: 受控仿真结果，绝不描述真实生产变更；不执行、不激活、不翻转"
        "engineering_enabled"
    )

    def to_dict(self) -> Dict[str, object]:
        return {
            "simulation_id": self.simulation_id,
            "change_id": self.change_id,
            "scenario": self.scenario,
            "outcome": self.outcome.value,
            "is_simulation": self.is_simulation,
            "detail": self.detail,
            "note": self.note,
        }


# --------------------------------------------------------------------------- #
# T24：失败场景评估                                                             #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class FailureScenarioEvaluation:
    """T24 失败场景评估：只读评估某失败场景下是否有缓解措施（不执行任何回滚/修复）。"""

    scenario_id: str
    change_id: str
    scenario_name: str
    severity: str  # low | medium | high | critical
    mitigation_present: bool = False
    status: ChangePreflightStatus = ChangePreflightStatus.PENDING_VERIFICATION
    note: str = "FAILURE_SCENARIO_ONLY: 只读评估缓解措施存在性，不执行回滚/修复"

    def to_dict(self) -> Dict[str, object]:
        return {
            "scenario_id": self.scenario_id,
            "change_id": self.change_id,
            "scenario_name": self.scenario_name,
            "severity": self.severity,
            "mitigation_present": self.mitigation_present,
            "status": self.status.value,
            "note": self.note,
        }


# --------------------------------------------------------------------------- #
# T25：受控变更包                                                               #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ControlledChangePackage:
    """T25 受控变更包：描述变更材料与引用（材料 ≠ 执行）。

    ``simulated_only`` 恒 ``True``：本包仅供人工评审，绝不触发真实变更执行。
    """

    package_id: str
    change_id: str
    contents: Dict[str, object] = field(default_factory=dict)
    simulated_only: bool = True  # 恒 True：材料≠执行
    generated_at: str = ""
    note: str = "CHANGE_PACKAGE_ONLY: 描述变更材料与引用，不执行部署"

    def to_dict(self) -> Dict[str, object]:
        return {
            "package_id": self.package_id,
            "change_id": self.change_id,
            "contents": dict(self.contents),
            "simulated_only": self.simulated_only,
            "generated_at": self.generated_at,
            "note": self.note,
        }


# --------------------------------------------------------------------------- #
# T9(决策草稿)：变更裁决草稿                                                     #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ChangeDecisionDraft:
    """变更裁决草稿：只能是草稿。

    AI 可汇总证据摘要 / 通过项 / 阻断项 / pending_verification / 风险项 / 回滚准备情况；
    最终状态必须由真实 ``ChangeSignoff`` 组合决定。``status`` 只能源于
    ``READY_FOR_HUMAN_GO_NO_GO`` / ``BLOCKED`` / ``NEEDS_MORE_EVIDENCE``；
    ``GO_LIVE_APPROVED`` 禁止作为 AI 生成状态。
    """

    draft_id: str
    change_id: str
    evidence_summary: Dict[str, object] = field(default_factory=dict)
    passed_items: List[str] = field(default_factory=list)
    blocked_items: List[str] = field(default_factory=list)
    pending_verification: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    rollback_readiness: str = "pending_verification"
    status: ChangeDecisionDraftStatus = ChangeDecisionDraftStatus.READY_FOR_HUMAN_GO_NO_GO
    generated_at: str = ""
    note: str = (
        "DRAFT_ONLY: AI 生成草稿；最终 GO / NO-GO 只能由真实 ChangeSignoff 组合决定"
    )

    def to_dict(self) -> Dict[str, object]:
        return {
            "draft_id": self.draft_id,
            "change_id": self.change_id,
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


__all__ = [
    "ChangeExecutionMode",
    "ChangeState",
    "ChangePreflightStatus",
    "ChangeVerificationStatus",
    "ChangeDecisionDraftStatus",
    "ChangeSimulationOutcome",
    "ChangeRequest",
    "ChangePlan",
    "ChangeWindow",
    "ChangePreflightResult",
    "ChangeCheckpoint",
    "ChangeAbortPolicy",
    "ChangeRollbackReference",
    "PostChangeVerification",
    "ChangeEvidence",
    "ChangeSimulationResult",
    "FailureScenarioEvaluation",
    "ControlledChangePackage",
    "ChangeDecisionDraft",
]
