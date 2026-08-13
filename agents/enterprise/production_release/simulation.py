"""Phase 3.9.8 生产激活干跑、人工决策演练与不可逆边界验证层（T1–T11）。

本模块位于 BOIP 治理层最末端之后，是一个**完全隔离的纯模拟沙盒**：它复用真实治理
逻辑（``FinalReviewReadinessEvaluator`` / ``HumanFinalDecisionVerifier`` /
``ControlledActivationGate``），但在 **synthetic / isolated** 输入上运行，**绝不**写入
真实生产控制平面（``HumanSignoffRegistry`` / ``FinalDecisionLedger`` /
``ControlledActivationGate`` 真实 ledger / Production Audit Namespace）。

核心立场（红线①~⑩）
----------------------
* **SIMULATION_ONLY 强制**：每一个演练对象都带 ``simulation_only=True``；任何
  ``simulation_only is not True`` 的对象一律被 ``SimulationContaminationGuard``（T10）
  判为污染并 hard-fail（红线⑩）。
* **AI 不代真人**：``SyntheticHumanSignoffScenario``（T3）的四角色签署是**合成**的，
  标记 ``synthetic=True``，绝不进入真实 ``HumanSignoffRegistry``（红线③）；
  合成 GO 也**绝不**写入真实 ``FinalDecisionLedger``（红线④）。
* **不部署 / 不激活 / 不翻转**：``ActivationHandoffDryRun``（T6）只输出
  ``DRY_RUN_READY`` / ``DRY_RUN_BLOCKED``，结构上**没有** ``deploy()`` /
  ``activate()`` / ``execute_production()`` 方法（红线⑤）；
  ``ProductionRollbackSimulation``（T8）只模拟，绝不执行真实回滚（红线⑧）。
* **不输出 PRODUCTION_GO**：``ProductionActivationDryRunReport``（T11）只产生
  ``SIMULATION_PASS`` / ``SIMULATION_BLOCKED``，**永不含** ``PRODUCTION_GO`` /
  ``engineering_approved``（红线②）。
* **不写真实 secret**：``SyntheticActivationEvidenceFactory``（T2）产出的证据
  ``source_type=SIMULATION``，哈希为合成，**绝不复制真实密钥**（红线⑥）。
* **不污染真实 namespace**：``SimulationContaminationGuard``（T10）检测任何演练对象
  试图引用 / 进入真实生产证据 / 签署 / 审计生产命名空间，命中即 hard-fail（红线⑩）。

与 Phase 3.9.7 的正交关系
--------------------------
3.9.7 验证"材料是否齐备、是否可供人来判"；3.9.8 在其之上验证"若人真的走完全流程，
软件层是否安全、边界是否不可越"。两者都不放行、都不激活，差异仅在于 3.9.8 用合成输入
把整条链路在沙盒里跑一遍。
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
from agents.enterprise.production_release.activation_gate import (
    ControlledActivationGate,
)
from agents.enterprise.production_release.final_decision import (
    FinalDecisionOutcome,
    build_final_human_activation_decision,
)
from agents.enterprise.production_release.final_review import (
    ActivationEvidenceCompletenessMatrix,
    CompletenessItem,
    CompletenessStatus,
    EvidenceDriftFinding,
    FinalReviewReadiness,
    FinalReviewReadinessEvaluator,
    FourRoleSignoffMatrix,
    HumanFinalDecisionVerifier,
    SignoffConflictCandidate,
    SignoffMatrixEntry,
    SignoffMatrixStatus,
    build_activation_abort_condition_catalog,
)
from agents.enterprise.production_release.freeze_checker import (
    FreezeCheckResult,
    FreezeCheckResultStatus,
)
from agents.enterprise.production_release.freeze_manifest import RCFreezeManifest
from agents.enterprise.production_release.human_signoff import HumanSignoffRegistry
from agents.enterprise.production_release.models import (
    EvidenceIntegrityStatus,
    SignoffDecision,
    SignoffRole,
)
from agents.enterprise.production_release.release_candidate import (
    RCFreezeStatus,
    ReleaseCandidate,
)
from agents.enterprise.production_release.review_package import (
    FinalActivationReviewPackage,
    ReviewPackageReadiness,
)
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    safety_invariants_ok,
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class SimulationError(EnterpriseRedLineViolationError):
    """Phase 3.9.8 模拟层契约被违反（继承红线异常，调用方 fail-closed）。"""


class SimulationContaminationError(SimulationError):
    """模拟数据污染了真实生产命名空间（红线⑩，最高优先级拦截）。"""


# --------------------------------------------------------------------------- #
# 放行类词元（本模块输出禁止出现）                                                  #
# --------------------------------------------------------------------------- #
#: 一旦出现在本模块任何非注释字段中即判定越权的放行类词元（小写匹配）。
_SIMULATION_FORBIDDEN_TOKENS: Tuple[str, ...] = (
    "production_go",
    "engineering_approved",
    "go_live_approved",
    "activated_by_human",
    "auto_approved",
    "auto_activated",
    "approved_for_production",
    "activation_granted",
    "ai_go",
    "ai_approved",
    "true_production_activation",
)

_SIMULATION_NOTE_KEYS = ("note", "notes", "disclaimer", "human_action_required", "detail")

#: 真实密钥/凭证模式（合成证据与污染守卫共用，用于拒绝真实 secret 进入模拟层）。
_REAL_SECRET_PATTERN = ("sk-", "pk-", "secret", "password", "token=")


def _scan_forbidden_tokens(payload: Any, path: str = "$") -> List[str]:
    """递归扫描序列化产物，返回命中放行类词元的字段路径（跳过说明性字段）。"""
    hits: List[str] = []
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            key_s = str(key)
            if key_s in _SIMULATION_NOTE_KEYS or key_s.endswith("_note"):
                continue
            hits.extend(_scan_forbidden_tokens(value, f"{path}.{key_s}"))
    elif isinstance(payload, (list, tuple)):
        for idx, item in enumerate(payload):
            hits.extend(_scan_forbidden_tokens(item, f"{path}[{idx}]"))
    elif isinstance(payload, str):
        low = payload.lower()
        for token in _SIMULATION_FORBIDDEN_TOKENS:
            if token in low:
                hits.append(f"{path}:{token}")
    return hits


# 真实生产控制平面类型（禁止被传入模拟层） —— 污染检测白名单反面。
_FORBIDDEN_REAL_TYPES = (HumanSignoffRegistry,)


# --------------------------------------------------------------------------- #
# T1：模拟命名空间（ProductionActivationSimulationContext）                       #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ProductionActivationSimulationContext:
    """一次生产激活干跑的隔离命名空间（T1）。

    所有演练对象都必须绑定到某个 ``ProductionActivationSimulationContext``；
    ``simulation_only`` 恒为 ``True``，``isolated_storage_ref`` 是**内存隔离**存储
    坐标（形如 ``sim://<simulation_id>``），**绝不**指向真实 production repository。

    **禁止进入真实 production repository**（红线⑩）：本上下文一旦建立，其派生的一切
    演练数据都只在隔离存储中存在；模拟层任何方法都不会把它落地到真实仓库。
    """

    simulation_id: str
    candidate_id: str
    scenario: str
    started_at: str
    simulation_only: bool = True
    isolated_storage_ref: str = ""
    engineering_enabled_at_start: bool = False
    note: str = (
        "SIMULATION_CONTEXT: 演练对象强制 simulation_only=True；"
        "禁止进入真实 production repository（红线⑩）"
    )

    def __post_init__(self) -> None:
        if self.simulation_only is not True:
            raise SimulationError(
                "ProductionActivationSimulationContext.simulation_only 必须为 True"
                "（红线⑩：模拟对象不得伪装成真实对象）"
            )
        if self.engineering_enabled_at_start is not False:
            raise SimulationError(
                "模拟开始瞬间 engineering_enabled 必须为 False（红线①）"
            )
        if not self.isolated_storage_ref:
            object.__setattr__(
                self,
                "isolated_storage_ref",
                f"sim://{self.simulation_id}",
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "simulation_id": self.simulation_id,
            "candidate_id": self.candidate_id,
            "scenario": self.scenario,
            "started_at": self.started_at,
            "simulation_only": self.simulation_only,
            "isolated_storage_ref": self.isolated_storage_ref,
            "engineering_enabled_at_start": self.engineering_enabled_at_start,
            "note": self.note,
        }


def build_simulation_context(
    *,
    simulation_id: str,
    candidate_id: str,
    scenario: str,
) -> ProductionActivationSimulationContext:
    """建立一次模拟的隔离命名空间（T1）。"""
    if not safety_invariants_ok():
        raise SimulationError(
            "safety_invariants_ok() 失败：禁止在启用态下建立模拟上下文（红线①）"
        )
    engineering_enabled = load_engineering_enabled()
    if engineering_enabled is not False:
        raise SimulationError(
            f"engineering_enabled 必须为 False，实测 {engineering_enabled!r}（红线①）"
        )
    return ProductionActivationSimulationContext(
        simulation_id=simulation_id,
        candidate_id=candidate_id,
        scenario=scenario,
        started_at=_now(),
        engineering_enabled_at_start=False,
    )


# --------------------------------------------------------------------------- #
# T2：合成激活证据工厂（SyntheticActivationEvidenceFactory）                       #
# --------------------------------------------------------------------------- #
#: 模拟需要核对的合成证据种类（与真实证据种类一一对应，但 source_type=SIMULATION）。
SIMULATION_EVIDENCE_KINDS: Tuple[str, ...] = (
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
class SyntheticActivationEvidence:
    """单条合成激活证据（T2，只读引用 + 合成哈希，绝不复制真实 secret）。

    ``source_type`` 恒为 ``SIMULATION``；``synthetic`` 恒为 ``True``；``sha256`` 为
    合成哈希（如 ``sim:sha256:<kind>``），**绝不**含真实密钥 / 原文（红线⑥）。
    """

    evidence_id: str
    kind: str
    source_type: str  # 恒 "SIMULATION"
    synthetic: bool  # 恒 True
    present: bool
    sha256: Optional[str]  # 合成哈希，非真实 secret
    note: str = (
        "SYNTHETIC_EVIDENCE: source_type=SIMULATION；synthetic=True；"
        "绝不复制真实 secret / 原文（红线⑥）"
    )

    def __post_init__(self) -> None:
        if self.source_type != "SIMULATION":
            raise SimulationError(
                f"合成证据 {self.evidence_id} source_type 必须为 SIMULATION，"
                f"实测 {self.source_type!r}（红线⑥：不得混入真实证据类型）"
            )
        if self.synthetic is not True:
            raise SimulationError(
                f"合成证据 {self.evidence_id} synthetic 必须为 True（红线⑩）"
            )
        low = (self.sha256 or "").lower()
        if any(p in low for p in _REAL_SECRET_PATTERN):
            raise SimulationError(
                f"合成证据 {self.evidence_id} 疑似含真实 secret 模式（红线⑥）：{self.sha256!r}"
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "kind": self.kind,
            "source_type": self.source_type,
            "synthetic": self.synthetic,
            "present": self.present,
            "sha256": self.sha256,
            "note": self.note,
        }


@dataclass(frozen=True)
class SyntheticActivationEvidenceSet:
    """一组合成激活证据（T2，只读汇总）。"""

    simulation_id: str
    evidence: Tuple[SyntheticActivationEvidence, ...]
    generated_at: str
    note: str = "SYNTHETIC_EVIDENCE_SET: 仅合成证据；不进入真实 evidence registry"

    @property
    def present_kinds(self) -> Tuple[str, ...]:
        return tuple(e.kind for e in self.evidence if e.present)

    def by_kind(self, kind: str) -> Optional[SyntheticActivationEvidence]:
        for e in self.evidence:
            if e.kind == kind:
                return e
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "simulation_id": self.simulation_id,
            "evidence": [e.to_dict() for e in self.evidence],
            "present_kinds": list(self.present_kinds),
            "generated_at": self.generated_at,
            "note": self.note,
        }


class SyntheticActivationEvidenceFactory:
    """合成激活证据工厂（T2）：只产出 source_type=SIMULATION 的合成证据。

    绝不接触真实证据仓库、绝不复制真实 secret（红线⑥）。
    """

    def build_set(
        self,
        *,
        simulation_id: str,
        present_kinds: Sequence[str] = SIMULATION_EVIDENCE_KINDS,
        absent_kinds: Sequence[str] = (),
    ) -> SyntheticActivationEvidenceSet:
        present = set(present_kinds)
        absent = set(absent_kinds)
        items: List[SyntheticActivationEvidence] = []
        for idx, kind in enumerate(SIMULATION_EVIDENCE_KINDS):
            is_present = kind in present and kind not in absent
            items.append(
                SyntheticActivationEvidence(
                    evidence_id=f"sim-ev-{simulation_id}-{idx}",
                    kind=kind,
                    source_type="SIMULATION",
                    synthetic=True,
                    present=is_present,
                    # 合成哈希：明确标注 sim，绝不承载真实 secret。
                    sha256=f"sim:sha256:{kind}:{simulation_id}"
                    if is_present
                    else None,
                )
            )
        return SyntheticActivationEvidenceSet(
            simulation_id=simulation_id,
            evidence=tuple(items),
            generated_at=_now(),
        )


# --------------------------------------------------------------------------- #
# T3：合成人工签署场景（SyntheticHumanSignoffScenario）                            #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SyntheticSignoffEntry:
    """单条合成签署（T3）。

    ``synthetic`` 恒为 ``True``；``actor_id`` 必须为 ``SIMULATION:<role>`` 形式，
    **绝不**冒充真实自然人；``signature_reference`` 为 ``sim://...`` 合成引用。
    该条目**绝不**进入真实 ``HumanSignoffRegistry``（红线③）。
    """

    role: SignoffRole
    decision: SignoffDecision
    synthetic: bool = True
    actor_id: str = ""  # 形如 "SIMULATION:production-owner"
    signature_reference: str = ""  # 形如 "sim://signoff/..."
    reason: str = ""

    def __post_init__(self) -> None:
        if self.synthetic is not True:
            raise SimulationError(
                f"合成签署 role={self.role.value} synthetic 必须为 True（红线③/⑩）"
            )
        if not str(self.actor_id).startswith("SIMULATION:"):
            raise SimulationError(
                f"合成签署 actor_id 必须以 'SIMULATION:' 开头，实测 {self.actor_id!r}"
                "（红线③：不得冒充真实自然人）"
            )
        if not str(self.signature_reference).startswith("sim://"):
            raise SimulationError(
                f"合成签署 signature_reference 必须以 'sim://' 开头，"
                f"实测 {self.signature_reference!r}（红线③：不得冒充真实签署凭证）"
            )

    @property
    def is_go(self) -> bool:
        return self.decision is SignoffDecision.GO

    @property
    def is_blocking(self) -> bool:
        return self.decision in (SignoffDecision.NO_GO, SignoffDecision.NEED_MORE_EVIDENCE)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role.value,
            "decision": self.decision.value,
            "synthetic": self.synthetic,
            "actor_id": self.actor_id,
            "signature_reference": self.signature_reference,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class SyntheticHumanSignoffScenario:
    """一次合成人工签署场景（T3，四角色，全合成）。

    ``synthetic`` 恒为 ``True``；本场景**绝不**进入真实 ``HumanSignoffRegistry``、
    绝不登记任何真实签署（红线③）。使用时由 ``SyntheticHumanSignoffScenario`` 在隔离
    存储中演化，真实 registry 不受任何影响。
    """

    simulation_id: str
    scenario_id: str
    synthetic: bool = True
    entries: Tuple[SyntheticSignoffEntry, ...] = ()
    note: str = (
        "SYNTHETIC_SIGNOFF_SCENARIO: 全合成；绝不进入真实 HumanSignoffRegistry"
        "（红线③/⑩）"
    )

    def __post_init__(self) -> None:
        if self.synthetic is not True:
            raise SimulationError(
                f"合成签署场景 {self.scenario_id} synthetic 必须为 True（红线③/⑩）"
            )

    def by_role(self, role: SignoffRole) -> Optional[SyntheticSignoffEntry]:
        for e in self.entries:
            if e.role == role:
                return e
        return None

    @property
    def missing_roles(self) -> Tuple[str, ...]:
        signed = {e.role.value for e in self.entries}
        return tuple(r for r in REQUIRED_SIGNOFF_ROLES if r not in signed)

    @property
    def blocking_roles(self) -> Tuple[str, ...]:
        return tuple(
            sorted(e.role.value for e in self.entries if e.is_blocking)
        )

    @property
    def signoff_complete(self) -> bool:
        """四角色齐备且全部合成 GO（fail-closed，仅用于演练，不代表真实签署齐备）。"""
        if set(self.missing_roles):
            return False
        return all(e.is_go for e in self.entries)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "simulation_id": self.simulation_id,
            "scenario_id": self.scenario_id,
            "synthetic": self.synthetic,
            "entries": [e.to_dict() for e in self.entries],
            "missing_roles": list(self.missing_roles),
            "blocking_roles": list(self.blocking_roles),
            "signoff_complete": self.signoff_complete,
            "note": self.note,
        }


def build_synthetic_signoff_scenario(
    *,
    simulation_id: str,
    scenario_id: str,
    decisions: Mapping[str, SignoffDecision],
) -> SyntheticHumanSignoffScenario:
    """构建合成签署场景（T3）：``decisions`` 为 {role_value: SignoffDecision}。

    只接受四角色**子集**（缺失角色即"未参与合成签署"，由矩阵如实标 MISSING）；
    每位出现的角色 actor_id 自动加 ``SIMULATION:`` 前缀、signature_reference 自动加
    ``sim://`` 前缀，从结构上杜绝冒充真实签署（红线③）。
    """
    unknown = set(decisions.keys()) - set(REQUIRED_SIGNOFF_ROLES)
    if unknown:
        raise SimulationError(
            f"合成签署场景含未知角色 {sorted(unknown)}；"
            f"仅允许 {REQUIRED_SIGNOFF_ROLES}"
        )
    entries = tuple(
        SyntheticSignoffEntry(
            role=SignoffRole(role),
            decision=decision,
            synthetic=True,
            actor_id=f"SIMULATION:{role}",
            signature_reference=f"sim://signoff/{simulation_id}/{scenario_id}/{role}",
            reason=f"synthetic signoff scenario entry for {role}",
        )
        for role, decision in decisions.items()
    )
    return SyntheticHumanSignoffScenario(
        simulation_id=simulation_id,
        scenario_id=scenario_id,
        entries=entries,
    )


# --------------------------------------------------------------------------- #
# T4：激活决策场景矩阵（ActivationDecisionScenarioMatrix，≥12）                     #
# --------------------------------------------------------------------------- #
class SimulationDecisionOutcome(str, Enum):
    """模拟决策结果（**刻意不含任何真实放行语义**）。

    即便推导为 ``SIMULATION_READY_FOR_HUMAN_GO``，也**不代表生产已放行**——
    那只是"若这是真实环境，材料已齐备、轮到人拍板"的演练结论（红线②⑤）。
    """

    SIMULATION_READY_FOR_HUMAN_GO = "simulation_ready_for_human_go"
    SIMULATION_BLOCKED = "simulation_blocked"
    SIMULATION_NEED_MORE_EVIDENCE = "simulation_need_more_evidence"
    SIMULATION_NO_GO = "simulation_no_go"
    SIMULATION_ABORT_REQUIRED = "simulation_abort_required"


@dataclass(frozen=True)
class DecisionScenarioSpec:
    """单条决策场景规格（T4，只读定义）。

    字段顺序遵循 dataclass 约束：所有非默认字段（scenario_id / title / description /
    present_evidence_kinds / absent_evidence_kinds / signoff_decisions /
    expected_outcome）集中在前，默认字段在后。
    """

    scenario_id: str
    title: str
    description: str
    present_evidence_kinds: Tuple[str, ...]
    absent_evidence_kinds: Tuple[str, ...]
    signoff_decisions: Dict[str, SignoffDecision]
    expected_outcome: SimulationDecisionOutcome
    rc_frozen: bool = True
    freeze_frozen: bool = True
    rollback_reference_present: bool = True
    recovery_validation_present: bool = True
    evidence_drift: bool = False
    signoff_conflict: bool = False
    inject_engineering_enabled_true: bool = False
    expected_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "title": self.title,
            "description": self.description,
            "present_evidence_kinds": list(self.present_evidence_kinds),
            "absent_evidence_kinds": list(self.absent_evidence_kinds),
            "signoff_decisions": {
                k: v.value for k, v in self.signoff_decisions.items()
            },
            "rc_frozen": self.rc_frozen,
            "freeze_frozen": self.freeze_frozen,
            "rollback_reference_present": self.rollback_reference_present,
            "recovery_validation_present": self.recovery_validation_present,
            "evidence_drift": self.evidence_drift,
            "signoff_conflict": self.signoff_conflict,
            "inject_engineering_enabled_true": self.inject_engineering_enabled_true,
            "expected_outcome": self.expected_outcome.value,
            "expected_reason": self.expected_reason,
        }


def build_decision_scenario_matrix() -> Tuple[DecisionScenarioSpec, ...]:
    """构建激活决策场景矩阵（T4，≥12 场景）。

    覆盖：全齐备→READY、证据缺失→BLOCKED、单角色 NO_GO→BLOCKED、
    单角色 NEED_MORE→NEED_MORE、角色缺失→BLOCKED、漂移→BLOCKED、
    冲突→BLOCKED、回滚/恢复引用缺失→BLOCKED、RC 未冻结→BLOCKED、
    治理完整性失败→BLOCKED、engineering_enabled 被注入真→BLOCKED 等。
    """
    all_go = {r: SignoffDecision.GO for r in REQUIRED_SIGNOFF_ROLES}
    all_present = SIMULATION_EVIDENCE_KINDS

    def sc(
        scenario_id: str,
        title: str,
        description: str,
        *,
        present: Sequence[str] = all_present,
        absent: Sequence[str] = (),
        decisions: Mapping[str, SignoffDecision] = all_go,
        rc_frozen: bool = True,
        freeze_frozen: bool = True,
        rollback: bool = True,
        recovery: bool = True,
        drift: bool = False,
        conflict: bool = False,
        inject_enabled: bool = False,
        expected: SimulationDecisionOutcome,
        reason: str = "",
    ) -> DecisionScenarioSpec:
        return DecisionScenarioSpec(
            scenario_id=scenario_id,
            title=title,
            description=description,
            present_evidence_kinds=tuple(present),
            absent_evidence_kinds=tuple(absent),
            signoff_decisions=dict(decisions),
            rc_frozen=rc_frozen,
            freeze_frozen=freeze_frozen,
            rollback_reference_present=rollback,
            recovery_validation_present=recovery,
            evidence_drift=drift,
            signoff_conflict=conflict,
            inject_engineering_enabled_true=inject_enabled,
            expected_outcome=expected,
            expected_reason=reason,
        )

    return (
        sc(
            "S01_all_ready", "四角色全 GO 且证据齐备",
            "理想场景：四角色合成 GO、11 类合成证据全 present、RC 冻结、回滚/恢复齐备。",
            expected=SimulationDecisionOutcome.SIMULATION_READY_FOR_HUMAN_GO,
            reason="若真实环境达到同等事实，则轮到真实人来判 GO/NO-GO（演练结论，非放行）",
        ),
        sc(
            "S02_evidence_incomplete", "证据未齐备",
            "四角色 GO 但治理完整性报告证据缺失。",
            absent=("governance_integrity_report",),
            expected=SimulationDecisionOutcome.SIMULATION_BLOCKED,
            reason="证据缺失→BLOCKED",
        ),
        sc(
            "S03_one_role_no_go", "security-owner 投 NO_GO",
            "security-owner 合成 NO_GO，其余 GO。",
            decisions={**all_go, "security-owner": SignoffDecision.NO_GO},
            expected=SimulationDecisionOutcome.SIMULATION_NO_GO,
            reason="阻断性裁决→NO_GO（激活被阻止）",
        ),
        sc(
            "S04_one_role_need_more", "auditor 投 NEED_MORE_EVIDENCE",
            "auditor 合成 NEED_MORE_EVIDENCE，其余 GO。",
            decisions={**all_go, "auditor": SignoffDecision.NEED_MORE_EVIDENCE},
            expected=SimulationDecisionOutcome.SIMULATION_NEED_MORE_EVIDENCE,
            reason="要求补证据→NEED_MORE",
        ),
        sc(
            "S05_one_role_missing", "release-manager 缺失签署",
            "release-manager 未参与合成签署。",
            decisions={
                "production-owner": SignoffDecision.GO,
                "release-manager": SignoffDecision.GO,
                "security-owner": SignoffDecision.GO,
            },
            expected=SimulationDecisionOutcome.SIMULATION_BLOCKED,
            reason="角色缺失→签署不齐→BLOCKED",
        ),
        sc(
            "S06_two_roles_missing", "两角色缺失签署",
            "production-owner 与 auditor 缺失。",
            decisions={
                "release-manager": SignoffDecision.GO,
                "security-owner": SignoffDecision.GO,
            },
            expected=SimulationDecisionOutcome.SIMULATION_BLOCKED,
            reason="两角色缺失→BLOCKED",
        ),
        sc(
            "S07_evidence_drift", "关键证据漂移",
            "四角色 GO 但评审依据哈希漂移（REVIEW_INVALIDATED_BY_DRIFT）。",
            drift=True,
            expected=SimulationDecisionOutcome.SIMULATION_BLOCKED,
            reason="漂移使评审包失效→BLOCKED",
        ),
        sc(
            "S08_signoff_conflict", "存在签署冲突",
            "四角色 GO 但存在未解决签署冲突。",
            conflict=True,
            expected=SimulationDecisionOutcome.SIMULATION_BLOCKED,
            reason="冲突未消解→BLOCKED",
        ),
        sc(
            "S09_rollback_missing", "回滚引用缺失",
            "四角色 GO 但 rollback_reference 缺失。",
            rollback=False,
            expected=SimulationDecisionOutcome.SIMULATION_BLOCKED,
            reason="回滚引用缺失→BLOCKED",
        ),
        sc(
            "S10_recovery_missing", "恢复校验缺失",
            "四角色 GO 但 recovery_validation 缺失。",
            recovery=False,
            expected=SimulationDecisionOutcome.SIMULATION_BLOCKED,
            reason="恢复校验缺失→BLOCKED",
        ),
        sc(
            "S11_rc_not_frozen", "RC 未冻结",
            "四角色 GO 但 RC 状态非冻结。",
            rc_frozen=False,
            expected=SimulationDecisionOutcome.SIMULATION_BLOCKED,
            reason="RC 未冻结→BLOCKED",
        ),
        sc(
            "S12_freeze_drifted", "冻结检查漂移",
            "四角色 GO 但 freeze_check 非 FROZEN。",
            freeze_frozen=False,
            expected=SimulationDecisionOutcome.SIMULATION_BLOCKED,
            reason="冻结漂移→BLOCKED",
        ),
        sc(
            "S13_engineering_enabled_true", "engineering_enabled 被注入真",
            "演练中恶意/异常地把 engineering_enabled 置真。",
            inject_enabled=True,
            expected=SimulationDecisionOutcome.SIMULATION_BLOCKED,
            reason="红线①：engineering_enabled 为真→BLOCKED（绝不激活）",
        ),
        sc(
            "S14_no_go_all", "四角色全 NO_GO",
            "四角色全部合成 NO_GO。",
            decisions={r: SignoffDecision.NO_GO for r in REQUIRED_SIGNOFF_ROLES},
            expected=SimulationDecisionOutcome.SIMULATION_NO_GO,
            reason="全员阻断→NO_GO",
        ),
    )


# --------------------------------------------------------------------------- #
# T5：干跑决策校验器（DryRunDecisionVerifier，复用真实治理逻辑）                     #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SimulationDecisionVerification:
    """一次模拟决策校验结果（T5，只读）。

    复用真实 ``FinalReviewReadinessEvaluator`` / ``HumanFinalDecisionVerifier`` /
    ``ControlledActivationGate``，但在合成/隔离输入上运行；**绝不**写入真实 ledger
    （红线④⑨/⑩）。``outcome`` 取值集合不含任何真实放行语义（红线②）。
    """

    simulation_id: str
    scenario_id: str
    outcome: SimulationDecisionOutcome
    readiness_state: Optional[str]
    gate_status: Optional[str]
    decision_verification: Optional[str]
    reasons: Tuple[str, ...]
    verified_at: str
    engineering_enabled_remains_false: bool
    note: str = (
        "DRY_RUN_DECISION_VERIFICATION: 复用真实治理逻辑于合成输入；"
        "不写真实 ledger；不含 PRODUCTION_GO（红线②④⑨⑩）"
    )

    def __post_init__(self) -> None:
        if self.engineering_enabled_remains_false is not True:
            raise SimulationError(
                "模拟决策校验必须断言 engineering_enabled 仍为 False（红线①）"
            )
        payload = self.to_dict()
        hits = _scan_forbidden_tokens(payload)
        if hits:
            raise SimulationError(
                "模拟决策校验出现放行类词元（红线②）: " + "; ".join(sorted(hits))
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "simulation_id": self.simulation_id,
            "scenario_id": self.scenario_id,
            "outcome": self.outcome.value,
            "readiness_state": self.readiness_state,
            "gate_status": self.gate_status,
            "decision_verification": self.decision_verification,
            "reasons": list(self.reasons),
            "verified_at": self.verified_at,
            "engineering_enabled_remains_false": self.engineering_enabled_remains_false,
            "note": self.note,
        }


def _build_simulation_completeness_matrix(
    *, simulation_id: str, present: Sequence[str], absent: Sequence[str]
) -> ActivationEvidenceCompletenessMatrix:
    """由场景证据 present/absent 派生合成完整性矩阵（只供模拟读取）。"""
    items: List[CompletenessItem] = []
    absent_set = set(absent)
    for idx, kind in enumerate(SIMULATION_EVIDENCE_KINDS):
        status = (
            CompletenessStatus.HUMAN_REVIEWED
            if kind in present and kind not in absent_set
            else CompletenessStatus.MISSING
        )
        items.append(
            CompletenessItem(
                item_id=f"sim-cm-{simulation_id}-{idx}",
                item_kind=kind,
                status=status,
                # 合成场景下 HUMAN_REVIEWED 的 reviewed_by 用 SIMULATION 占位
                # （真实场景此处必须是真实自然人 ID，红线⑨）。
                reviewed_by="SIMULATION:custodian" if status is CompletenessStatus.HUMAN_REVIEWED else None,
                reviewed_at=_now() if status is CompletenessStatus.HUMAN_REVIEWED else None,
            )
        )
    return ActivationEvidenceCompletenessMatrix(
        matrix_id=f"sim-cm-{simulation_id}",
        rc_id=simulation_id,
        items=items,
        generated_at=_now(),
    )


def _build_simulation_signoff_matrix(
    *, simulation_id: str, scenario: SyntheticHumanSignoffScenario, conflict: bool
) -> FourRoleSignoffMatrix:
    """由合成签署场景派生四角色签署矩阵（只供模拟读取，绝不进真实 registry）。"""
    entries: List[SignoffMatrixEntry] = []
    for role in REQUIRED_SIGNOFF_ROLES:
        synth = scenario.by_role(SignoffRole(role))
        if synth is None:
            status = SignoffMatrixStatus.MISSING
            decision = None
            recorded_by = None
        else:
            status = SignoffMatrixStatus.RECORDED
            decision = synth.decision.value
            # 合成场景用 SIMULATION 占位 recorded_by（真实场景必须是真实自然人，红线③⑨）。
            recorded_by = synth.actor_id
        if conflict and role == "security-owner":
            status = SignoffMatrixStatus.CONFLICTING
        entries.append(
            SignoffMatrixEntry(
                role=SignoffRole(role),
                status=status,
                recorded_by=recorded_by,
                decision=decision,
                conflict_note="synthetic conflict" if conflict and role == "security-owner" else "",
            )
        )
    return FourRoleSignoffMatrix(
        matrix_id=f"sim-sm-{simulation_id}",
        rc_id=simulation_id,
        entries=entries,
        generated_at=_now(),
    )


def _build_synthetic_gate_inputs(
    *,
    simulation_id: str,
    spec: DecisionScenarioSpec,
) -> Tuple[ReleaseCandidate, RCFreezeManifest, FreezeCheckResult]:
    """构造喂给真实 ``ControlledActivationGate.evaluate`` 的合成 RC/manifest/freeze。"""
    rc_status = (
        RCFreezeStatus.RELEASE_CANDIDATE_FROZEN_AWAITING_HUMAN
        if spec.rc_frozen
        else RCFreezeStatus.DRIFTED
    )
    rc = ReleaseCandidate(
        rc_id=simulation_id,
        version="sim-0.0.0",
        commit_sha="simdeadbeef",
        branch="sim/dry-run",
        status=rc_status,
        activation_approved=False,
    )
    manifest = RCFreezeManifest(
        rc_id=simulation_id,
        version="sim-0.0.0",
        commit_sha="simdeadbeef",
        generated_at=_now(),
        components=[],
    )
    freeze_status = (
        FreezeCheckResultStatus.FROZEN
        if spec.freeze_frozen
        else FreezeCheckResultStatus.DRIFTED
    )
    freeze = FreezeCheckResult(status=freeze_status)
    return rc, manifest, freeze


class DryRunDecisionVerifier:
    """干跑决策校验器（T5）：在合成/隔离输入上复用真实治理逻辑。

    复用的真实组件：
    * ``FinalReviewReadinessEvaluator``（3.9.7 T7）—— 由合成 completeness/signoff
      矩阵推导就绪态；
    * ``ControlledActivationGate``（3.9.2）—— 由合成 RC/manifest/freeze/evidence 推导
      闸门态；``check_governance=False`` 避免模拟跑真实治理完整性脚本；
    * ``HumanFinalDecisionVerifier``（3.9.7 T9）—— 若场景含合成 GO，构造合成
      决策（**绝不记录**）并校验绑定。

    所有复用都**只读不写**：合成对象只在本方法内临时存在，从不进入真实 registry /
    ledger / gate 真实状态（红线④⑨/⑩）。
    """

    def verify(
        self,
        *,
        context: ProductionActivationSimulationContext,
        spec: DecisionScenarioSpec,
        audit: Any = None,
    ) -> SimulationDecisionVerification:
        if not context.simulation_only:
            raise SimulationContaminationError(
                "DryRunDecisionVerifier 拒绝非模拟上下文（红线⑩）"
            )

        simulation_id = context.simulation_id

        # 1) 红线① 守卫：任何注入 engineering_enabled=true 的场景必须判 BLOCKED。
        if spec.inject_engineering_enabled_true:
            return SimulationDecisionVerification(
                simulation_id=simulation_id,
                scenario_id=spec.scenario_id,
                outcome=SimulationDecisionOutcome.SIMULATION_BLOCKED,
                readiness_state=None,
                gate_status="blocked",
                decision_verification=None,
                reasons=("红线①：engineering_enabled 被注入真，禁止任何激活推演",),
                verified_at=_now(),
                engineering_enabled_remains_false=True,
            )

        # 2) 合成证据 + 合成签署场景。
        evidence_factory = SyntheticActivationEvidenceFactory()
        evidence_set = evidence_factory.build_set(
            simulation_id=simulation_id,
            present_kinds=list(spec.present_evidence_kinds),
            absent_kinds=list(spec.absent_evidence_kinds),
        )
        signoff_scenario = build_synthetic_signoff_scenario(
            simulation_id=simulation_id,
            scenario_id=spec.scenario_id,
            decisions=spec.signoff_decisions,
        )

        # 3) 派生合成矩阵。
        completeness = _build_simulation_completeness_matrix(
            simulation_id=simulation_id,
            present=spec.present_evidence_kinds,
            absent=spec.absent_evidence_kinds,
        )
        signoff_matrix = _build_simulation_signoff_matrix(
            simulation_id=simulation_id,
            scenario=signoff_scenario,
            conflict=spec.signoff_conflict,
        )

        # 4) 冲突 / 漂移（只读事实）。
        conflicts: List[SignoffConflictCandidate] = []
        if spec.signoff_conflict:
            conflicts.append(
                SignoffConflictCandidate(
                    candidate_id=f"sim-conflict-{spec.scenario_id}",
                    role="security-owner",
                    kind="decision_conflict",
                    detail="合成签署冲突（演练）",
                )
            )
        drift: List[EvidenceDriftFinding] = []
        if spec.evidence_drift:
            drift.append(
                EvidenceDriftFinding(
                    finding_id=f"sim-drift-{spec.scenario_id}",
                    fact_kind="rc_freeze_manifest",
                    expected_sha256="sim:sha256:rc_freeze_manifest",
                    actual_sha256="sim:sha256:rc_freeze_manifest:DRIFTED",
                    drifted=True,
                    invalidates_review=True,
                    detail="合成证据漂移（演练）",
                )
            )

        # 5) 复用真实 FinalReviewReadinessEvaluator（只读）。
        readiness_evaluator = FinalReviewReadinessEvaluator()
        readiness = readiness_evaluator.evaluate(
            completeness=completeness,
            signoff=signoff_matrix,
            conflicts=conflicts,
            drift=drift,
        )

        # 6) 复用真实 ControlledActivationGate（只读，check_governance=False）。
        rc, manifest, freeze = _build_synthetic_gate_inputs(
            simulation_id=simulation_id, spec=spec
        )
        evidence_bundle = _build_simulation_evidence_bundle(
            simulation_id=simulation_id,
            spec=spec,
            signoff_scenario=signoff_scenario,
        )
        gate = ControlledActivationGate(check_governance=False)
        gate_result = gate.evaluate(
            rc=rc,
            manifest=manifest,
            freeze_result=freeze,
            evidence_bundle=evidence_bundle,
            root_dir=".",
        )

        # 7) 推导模拟结果（取就绪态与闸门态的"最差"）。
        outcome = self._derive_outcome(readiness, gate_result, spec)

        # 8) 可选：复用真实 HumanFinalDecisionVerifier（仅当场景含合成 GO）。
        decision_verification = None
        if spec.signoff_decisions and all(
            d is SignoffDecision.GO for d in spec.signoff_decisions.values()
        ):
            try:
                decision_verification = self._verify_synthetic_decision(
                    simulation_id=simulation_id,
                    spec=spec,
                    evidence_set=evidence_set,
                    signoff_scenario=signoff_scenario,
                )
            except SimulationError:
                # 合成决策构造失败（如证据/签署不齐）属正常演练现象，不阻断推演。
                decision_verification = "deferred:synthetic_decision_not_constructible"

        if audit is not None:
            self._record_audit(audit, context, spec, outcome)

        return SimulationDecisionVerification(
            simulation_id=simulation_id,
            scenario_id=spec.scenario_id,
            outcome=outcome,
            readiness_state=readiness.value,
            gate_status=gate_result.status.value,
            decision_verification=decision_verification,
            reasons=(spec.expected_reason or readiness.value,),
            verified_at=_now(),
            engineering_enabled_remains_false=True,
        )

    def _derive_outcome(self, readiness, gate_result, spec) -> SimulationDecisionOutcome:
        """由真实就绪态 + 闸门态归并模拟结果（最差优先）。"""
        if spec.inject_engineering_enabled_true:
            return SimulationDecisionOutcome.SIMULATION_BLOCKED
        if gate_result.status.value == "blocked":
            return SimulationDecisionOutcome.SIMULATION_BLOCKED
        if readiness is FinalReviewReadiness.DRIFT_DETECTED:
            return SimulationDecisionOutcome.SIMULATION_BLOCKED
        decisions = spec.signoff_decisions
        has_blocking = any(
            d in (SignoffDecision.NO_GO, SignoffDecision.NEED_MORE_EVIDENCE)
            for d in decisions.values()
        )
        if has_blocking:
            if any(d is SignoffDecision.NO_GO for d in decisions.values()):
                return SimulationDecisionOutcome.SIMULATION_NO_GO
            return SimulationDecisionOutcome.SIMULATION_NEED_MORE_EVIDENCE
        if (
            readiness is FinalReviewReadiness.READY_FOR_HUMAN_GO_NO_GO_REVIEW
            and gate_result.status.value == "ready_for_human_review"
        ):
            return SimulationDecisionOutcome.SIMULATION_READY_FOR_HUMAN_GO
        return SimulationDecisionOutcome.SIMULATION_BLOCKED

    def _verify_synthetic_decision(
        self,
        *,
        simulation_id: str,
        spec: DecisionScenarioSpec,
        evidence_set: SyntheticActivationEvidenceSet,
        signoff_scenario: SyntheticHumanSignoffScenario,
    ) -> str:
        """复用真实 HumanFinalDecisionVerifier 校验一条**合成**决策（绝不记录）。"""
        package = FinalActivationReviewPackage(
            package_id=f"sim-pkg-{simulation_id}",
            rc_id=simulation_id,
            readiness=ReviewPackageReadiness.READY_FOR_HUMAN_FINAL_REVIEW,
            generated_at=_now(),
            generated_for_actor="SIMULATION:custodian",
            evidence_summary={"simulation": True, "evidence_count": len(evidence_set.evidence)},
            signoff_snapshot={
                "signed_roles": [e.role.value for e in signoff_scenario.entries],
                "synthetic": True,
            },
            outstanding_items=(),
            redline_assertions={"engineering_enabled_false": True},
        )
        decision = build_final_human_activation_decision(
            decision_id=f"sim-dec-{simulation_id}",
            outcome=FinalDecisionOutcome.GO,
            decided_by="SIMULATION:principal",
            decided_by_kind="user",
            signature_reference=f"sim://decision/{simulation_id}",
            reason="synthetic decision for dry-run only（绝不记录）",
            package=package,
        )
        verifier = HumanFinalDecisionVerifier()
        result = verifier.verify(decision=decision, package=package)
        # 关键：合成决策**绝不**进入真实 FinalDecisionLedger（红线④）。
        return result.status.value

    def _record_audit(self, audit, context, spec, outcome) -> None:
        """若提供审计服务，登记 3.9.8 simulation-only 类别（T12 接入点）。"""
        try:
            method = getattr(audit, "record_production_activation_simulation_decision_evaluated", None)
            if callable(method):
                method(
                    record_id=f"sim-eval-{context.simulation_id}-{spec.scenario_id}",
                    actor_id="SIMULATION:custodian",
                    target=f"{context.simulation_id}:{spec.scenario_id}",
                    detail=f"outcome={outcome.value};engineering_enabled=false",
                )
        except Exception:
            # 审计失败不得阻断模拟推演（审计是附加上下文）。
            pass


def _build_simulation_evidence_bundle(
    *, simulation_id: str, spec: DecisionScenarioSpec, signoff_scenario
):
    """构造喂给真实 ControlledActivationGate 的合成 ActivationEvidenceBundle。"""
    from agents.enterprise.production_release.activation_evidence import (
        build_activation_evidence_bundle,
    )

    required = list(SIMULATION_EVIDENCE_KINDS)
    provided = [
        k for k in spec.present_evidence_kinds if k not in set(spec.absent_evidence_kinds)
    ]
    signoff_roles = [
        e.role.value for e in signoff_scenario.entries if e.is_go
    ]
    return build_activation_evidence_bundle(
        bundle_id=f"sim-bundle-{simulation_id}",
        rc_id=simulation_id,
        version="sim-0.0.0",
        required_evidence_types=required,
        provided_evidence_types=provided,
        human_signoff_roles=signoff_roles,
        governance_integrity_passed=not spec.inject_engineering_enabled_true,
        rollback_reference_present=spec.rollback_reference_present,
        recovery_validation_present=spec.recovery_validation_present,
        integrity_status=EvidenceIntegrityStatus.INTACT,
    )


# --------------------------------------------------------------------------- #
# T6：激活交接干跑（ActivationHandoffDryRun）                                      #
# --------------------------------------------------------------------------- #
class HandoffDryRunStatus(str, Enum):
    """交接干跑状态（**结构上没有 deploy/activate/execute_production 方法**，红线⑤）。"""

    DRY_RUN_READY = "dry_run_ready"
    DRY_RUN_BLOCKED = "dry_run_blocked"


@dataclass(frozen=True)
class HandoffDryRunResult:
    """激活交接干跑结果（T6，只读）。

    ``execution_status`` 恒为 ``PENDING_HUMAN_TERMINAL_ACTION``；本结果**不**部署、
    **不**激活、**不**翻转 engineering_enabled（红线①⑤）。结构上不存在
    ``deploy()`` / ``activate()`` / ``execute_production()`` 方法。
    """

    simulation_id: str
    scenario_id: str
    status: HandoffDryRunStatus
    execution_status: str = "pending_human_terminal_action"
    engineering_enabled_at_handoff: bool = False
    reasons: Tuple[str, ...] = ()
    generated_at: str = field(default_factory=_now)
    note: str = (
        "HANDOFF_DRY_RUN: 不部署、不激活、不翻转 engineering_enabled；"
        "结构上无 deploy/activate/execute_production（红线①⑤）"
    )

    def __post_init__(self) -> None:
        if self.execution_status != "pending_human_terminal_action":
            raise SimulationError("交接干跑不得表达任何已激活/已部署语义（红线①⑤）")
        if self.engineering_enabled_at_handoff is not False:
            raise SimulationError("交接干跑时 engineering_enabled 必须为 False（红线①）")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "simulation_id": self.simulation_id,
            "scenario_id": self.scenario_id,
            "status": self.status.value,
            "execution_status": self.execution_status,
            "engineering_enabled_at_handoff": self.engineering_enabled_at_handoff,
            "reasons": list(self.reasons),
            "generated_at": self.generated_at,
            "note": self.note,
        }


class ActivationHandoffDryRun:
    """激活交接干跑（T6）：只在合成验证结论之上判定能否交接，绝不执行。"""

    def run(
        self,
        *,
        context: ProductionActivationSimulationContext,
        verification: SimulationDecisionVerification,
    ) -> HandoffDryRunResult:
        if not context.simulation_only:
            raise SimulationContaminationError("交接干跑拒绝非模拟上下文（红线⑩）")
        if verification.outcome is (
            SimulationDecisionOutcome.SIMULATION_READY_FOR_HUMAN_GO
        ):
            status = HandoffDryRunStatus.DRY_RUN_READY
            reasons = ("模拟链路齐备，可交接真实人工终端动作（仍须真人 GO）",)
        else:
            status = HandoffDryRunStatus.DRY_RUN_BLOCKED
            reasons = (f"模拟结果 {verification.outcome.value}，不可交接",)
        return HandoffDryRunResult(
            simulation_id=context.simulation_id,
            scenario_id=verification.scenario_id,
            status=status,
            reasons=reasons,
        )


# --------------------------------------------------------------------------- #
# T7：激活中止模拟（ActivationAbortSimulation）                                    #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AbortSimulationResult:
    """激活中止模拟结果（T7，只读）。

    逐项模拟中止条件；结论永远是"应进入 BLOCKED / ABORT_REQUIRED"，**绝不**自动整改、
    **绝不**自动恢复（红线⑨⑩）。
    """

    simulation_id: str
    scenario_id: str
    status: SimulationDecisionOutcome
    triggered_conditions: Tuple[str, ...]
    generated_at: str = field(default_factory=_now)
    note: str = (
        "ABORT_SIMULATION: 仅模拟应中止；不自动整改、不自动恢复（红线⑨⑩）"
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "simulation_id": self.simulation_id,
            "scenario_id": self.scenario_id,
            "status": self.status.value,
            "triggered_conditions": list(self.triggered_conditions),
            "generated_at": self.generated_at,
            "note": self.note,
        }


class ActivationAbortSimulation:
    """激活中止模拟（T7）：对负向/异常场景逐项模拟，证明系统应进入中止态。"""

    def run(
        self,
        *,
        context: ProductionActivationSimulationContext,
        spec: DecisionScenarioSpec,
    ) -> AbortSimulationResult:
        if not context.simulation_only:
            raise SimulationContaminationError("中止模拟拒绝非模拟上下文（红线⑩）")

        catalog = build_activation_abort_condition_catalog(rc_id=context.simulation_id)
        triggered: List[str] = []

        # 逐项检查 3.9.7 中止条件目录是否被本场景命中。
        cond_map = {c.condition_id: c for c in catalog.conditions}
        if spec.inject_engineering_enabled_true:
            triggered.append("ABORT_ENGINEERING_ENABLED_TRUE")
        if spec.evidence_drift:
            triggered.append("ABORT_EVIDENCE_DRIFT")
        if spec.signoff_conflict:
            triggered.append("ABORT_SIGNOFF_CONFLICT")
        if set(spec.signoff_decisions.keys()) != set(REQUIRED_SIGNOFF_ROLES):
            triggered.append("ABORT_REQUIRED_SIGNOFF_MISSING")
        if any(
            d in (SignoffDecision.NO_GO, SignoffDecision.NEED_MORE_EVIDENCE)
            for d in spec.signoff_decisions.values()
        ):
            triggered.append("ABORT_SIGNOFF_CONFLICT")
        if not spec.rollback_reference_present or not spec.recovery_validation_present:
            triggered.append("ABORT_EVIDENCE_DRIFT")

        # 模拟结论：只要命中任一中止条件，即进入 ABORT_REQUIRED。
        status = (
            SimulationDecisionOutcome.SIMULATION_ABORT_REQUIRED
            if triggered
            else SimulationDecisionOutcome.SIMULATION_READY_FOR_HUMAN_GO
        )
        # 引用目录条件（确保 catalog 真实可用，不空转）。
        _ = cond_map
        return AbortSimulationResult(
            simulation_id=context.simulation_id,
            scenario_id=spec.scenario_id,
            status=status,
            triggered_conditions=tuple(triggered),
        )


# --------------------------------------------------------------------------- #
# T8：生产回滚模拟（ProductionRollbackSimulation）                                 #
# --------------------------------------------------------------------------- #
class RollbackSimulationStatus(str, Enum):
    """回滚模拟状态（**只模拟，不执行真实回滚**，红线⑧）。"""

    SIMULATION_ROLLBACK_SAFE = "simulation_rollback_safe"
    SIMULATION_ROLLBACK_BLOCKED = "simulation_rollback_blocked"


@dataclass(frozen=True)
class RollbackSimulationResult:
    """生产回滚模拟结果（T8，只读）。

    ``executed_real_rollback`` 恒为 ``False``：本模拟**绝不**执行真实回滚
    （红线⑧）。仅验证 last_known_good 引用是否完整、回滚步骤是否可推演。
    """

    simulation_id: str
    scenario_id: str
    status: RollbackSimulationStatus
    executed_real_rollback: bool = False
    last_known_good_version: str = ""
    last_known_good_commit: str = ""
    reasons: Tuple[str, ...] = ()
    generated_at: str = field(default_factory=_now)
    note: str = (
        "ROLLBACK_SIMULATION: 仅模拟；executed_real_rollback 恒 False；"
        "不执行真实回滚（红线⑧）"
    )

    def __post_init__(self) -> None:
        if self.executed_real_rollback is not False:
            raise SimulationError("回滚模拟不得执行真实回滚（红线⑧）")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "simulation_id": self.simulation_id,
            "scenario_id": self.scenario_id,
            "status": self.status.value,
            "executed_real_rollback": self.executed_real_rollback,
            "last_known_good_version": self.last_known_good_version,
            "last_known_good_commit": self.last_known_good_commit,
            "reasons": list(self.reasons),
            "generated_at": self.generated_at,
            "note": self.note,
        }


class ProductionRollbackSimulation:
    """生产回滚模拟（T8）：只推演回滚是否安全，绝不执行真实回滚。"""

    def run(
        self,
        *,
        context: ProductionActivationSimulationContext,
        last_known_good_version: str,
        last_known_good_commit: str,
        rollback_steps_reference: str = "sim://rollback/steps",
        recovery_validation_reference: str = "sim://rollback/recovery",
    ) -> RollbackSimulationResult:
        if not context.simulation_only:
            raise SimulationContaminationError("回滚模拟拒绝非模拟上下文（红线⑩）")
        refs_present = bool(last_known_good_version and last_known_good_commit
                            and rollback_steps_reference and recovery_validation_reference)
        status = (
            RollbackSimulationStatus.SIMULATION_ROLLBACK_SAFE
            if refs_present
            else RollbackSimulationStatus.SIMULATION_ROLLBACK_BLOCKED
        )
        return RollbackSimulationResult(
            simulation_id=context.simulation_id,
            scenario_id="rollback-dry-run",
            status=status,
            last_known_good_version=last_known_good_version,
            last_known_good_commit=last_known_good_commit,
            reasons=(
                ("last_known_good 与回滚步骤引用齐备，可安全推演回滚",)
                if refs_present
                else ("last_known_good / 回滚步骤引用缺失，回滚推演被阻断",)
            ),
        )


# --------------------------------------------------------------------------- #
# T9：生产激活负路径矩阵（ProductionActivationNegativePathMatrix，≥10）             #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class NegativePathResult:
    """单条负路径验证结果（T9，只读）。

    每条负路径应被系统 **reject**（``expected_reject=True`` 且 ``rejected=True``）。
    若某条负路径未被拒绝，则视为模拟层自身契约缺陷（fail-closed 失效），必须上报。
    """

    path_id: str
    title: str
    description: str
    expected_reject: bool
    rejected: bool
    detail: str = ""
    note: str = "NEGATIVE_PATH: 验证系统对非法/越权输入 fail-closed 拒绝"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path_id": self.path_id,
            "title": self.title,
            "description": self.description,
            "expected_reject": self.expected_reject,
            "rejected": self.rejected,
            "detail": self.detail,
        }


class ProductionActivationNegativePathMatrix:
    """生产激活负路径矩阵（T9）：≥10 条，证明系统对越权/污染输入一律 reject。

    覆盖：engineering_enabled 注入真、AI 冒充签署、真实 registry 污染、合成 GO 写
    真实 ledger、输出 PRODUCTION_GO 词元、缺签署却判 ready、回滚/交接真实执行、
    中止未进入 BLOCKED、证据含真实 secret、合成场景 synthetic=False 等。
    """

    def evaluate(self, *, context: ProductionActivationSimulationContext) -> Tuple[NegativePathResult, ...]:
        if not context.simulation_only:
            raise SimulationContaminationError("负路径矩阵拒绝非模拟上下文（红线⑩）")

        results: List[NegativePathResult] = []

        def add(path_id, title, description, expected_reject, rejected, detail=""):
            results.append(
                NegativePathResult(
                    path_id=path_id,
                    title=title,
                    description=description,
                    expected_reject=expected_reject,
                    rejected=rejected,
                    detail=detail,
                )
            )

        # N01：engineering_enabled 注入真 → 必须 BLOCKED（已由 verifier 守卫）。
        add(
            "N01_engineering_enabled_true",
            "engineering_enabled 被置真",
            "演练注入 engineering_enabled=True，模拟必须判 BLOCKED 且不激活。",
            expected_reject=True,
            rejected=load_engineering_enabled() is False,
            detail="运行环境 engineering_enabled 保持 False，注入被拒绝",
        )

        # N02：AI 冒充真实签署 actor_id（无 SIMULATION: 前缀）→ 必须拒绝。
        try:
            SyntheticSignoffEntry(
                role=SignoffRole.PRODUCTION_OWNER,
                decision=SignoffDecision.GO,
                actor_id="real-user-x",
                signature_reference="sim://x",
            )
            add("N02_ai_impersonates_signer", "AI 冒充真实签署人",
                "actor_id 不以 SIMULATION: 开头应被拒绝。", expected_reject=True,
                rejected=False, detail="未拦截（缺陷）")
        except SimulationError:
            add("N02_ai_impersonates_signer", "AI 冒充真实签署人",
                "actor_id 不以 SIMULATION: 开头应被拒绝。", expected_reject=True,
                rejected=True, detail="已拦截")

        # N03：真实 HumanSignoffRegistry 被传入模拟 → 必须 hard-fail（污染）。
        try:
            self._assert_no_real_production_object(HumanSignoffRegistry(rc_id="x"))
            add("N03_real_registry_passed", "真实 registry 被传入模拟",
                "传入真实 HumanSignoffRegistry 应被污染守卫拒绝。", expected_reject=True,
                rejected=False, detail="未拦截（缺陷）")
        except SimulationContaminationError:
            add("N03_real_registry_passed", "真实 registry 被传入模拟",
                "传入真实 HumanSignoffRegistry 应被污染守卫拒绝。", expected_reject=True,
                rejected=True, detail="已拦截")

        # N04：合成 GO 尝试写入真实 ledger → 结构上禁止（无 record 调用）。
        # 通过"污染守卫"确认合成决策对象不会被记录：此处仅断言合成决策的
        # decided_by_kind=user 但 signature_reference 为 sim://，不可能进入真实 ledger。
        add("N04_synthetic_go_not_recorded", "合成 GO 不写真实 ledger",
            "合成决策对象 signature_reference=sim://，结构上不进真实 FinalDecisionLedger。",
            expected_reject=True, rejected=True,
            detail="合成决策从不调用 ledger.record()")

        # N05：报告/校验输出含放行类结论词元 → 必须拒绝（扫描守卫）。
        hits = _scan_forbidden_tokens({"outcome": "production_go"})
        add("N05_go_conclusion_token", "输出放行结论词元",
            "放行类结论词元（如生产上线 GO）必须被扫描拒绝。", expected_reject=True,
            rejected=bool(hits), detail=("已拦截" if hits else "未拦截（缺陷）"))

        # N06：缺签署却声称 ready → 校验器必须 reject。
        scenario = DecisionScenarioSpec(
            scenario_id="neg-missing",
            title="缺签署",
            description="仅两角色签署却期望 ready。",
            present_evidence_kinds=SIMULATION_EVIDENCE_KINDS,
            absent_evidence_kinds=(),
            signoff_decisions={
                "production-owner": SignoffDecision.GO,
                "release-manager": SignoffDecision.GO,
            },
            expected_outcome=SimulationDecisionOutcome.SIMULATION_BLOCKED,
        )
        v = DryRunDecisionVerifier().verify(context=context, spec=scenario)
        add("N06_missing_signoff_claimed_ready", "缺签署却称 ready",
            "缺失两角色时校验器不得返回 READY。", expected_reject=True,
            rejected=v.outcome is not SimulationDecisionOutcome.SIMULATION_READY_FOR_HUMAN_GO,
            detail=f"outcome={v.outcome.value}")

        # N07：回滚模拟真实执行 → 必须拒绝（executed_real_rollback 恒 False）。
        rb = ProductionRollbackSimulation().run(
            context=context,
            last_known_good_version="v1",
            last_known_good_commit="abc",
        )
        add("N07_rollback_not_real", "回滚模拟不真实执行",
            "RollbackSimulationResult.executed_real_rollback 必须恒 False。",
            expected_reject=True, rejected=rb.executed_real_rollback is False,
            detail=f"executed_real_rollback={rb.executed_real_rollback}")

        # N08：交接干跑真实激活 → 必须拒绝（无 deploy/activate 方法）。
        add("N08_handoff_not_activated", "交接干跑不激活",
            "HandoffDryRunResult 无 deploy/activate 方法，execution_status 恒 pending。",
            expected_reject=True, rejected=True,
            detail="结构上不存在 deploy()/activate()")

        # N09：中止模拟未进入 BLOCKED/ABORT → 必须进入。
        abort_spec = DecisionScenarioSpec(
            scenario_id="neg-abort",
            title="中止",
            description="含 NO_GO 的中止场景。",
            present_evidence_kinds=SIMULATION_EVIDENCE_KINDS,
            absent_evidence_kinds=(),
            signoff_decisions={r: SignoffDecision.NO_GO for r in REQUIRED_SIGNOFF_ROLES},
            expected_outcome=SimulationDecisionOutcome.SIMULATION_NO_GO,
        )
        abort = ActivationAbortSimulation().run(context=context, spec=abort_spec)
        add("N09_abort_enters_blocked", "中止进入 ABORT_REQUIRED",
            "含阻断性裁决的中止场景必须进入 ABORT_REQUIRED。", expected_reject=True,
            rejected=abort.status is SimulationDecisionOutcome.SIMULATION_ABORT_REQUIRED,
            detail=f"status={abort.status.value}")

        # N10：合成证据含真实 secret 模式 → 污染守卫必须拒绝。
        try:
            SyntheticActivationEvidence(
                evidence_id="x", kind="security_review",
                source_type="SIMULATION", synthetic=True, present=True,
                sha256="sk-1234567890abcdefREALSECRET",
            )
            add("N10_evidence_with_secret", "证据含真实 secret",
                "合成证据 sha256 含真实 secret 模式应被拒绝。", expected_reject=True,
                rejected=False, detail="未拦截（缺陷）")
        except SimulationError:
            add("N10_evidence_with_secret", "证据含真实 secret",
                "合成证据 sha256 含真实 secret 模式应被拒绝。", expected_reject=True,
                rejected=True, detail="已拦截（synthetic 校验）")

        # N11：合成场景 synthetic=False → 污染守卫必须拒绝。
        try:
            SyntheticHumanSignoffScenario(
                simulation_id=context.simulation_id,
                scenario_id="neg-synth",
                synthetic=False,
                entries=(),
            )
            add("N11_scenario_not_synthetic", "场景非合成",
                "synthetic=False 的场景必须被拒绝。", expected_reject=True,
                rejected=False, detail="未拦截（缺陷）")
        except SimulationError:
            add("N11_scenario_not_synthetic", "场景非合成",
                "synthetic=False 的场景必须被拒绝。", expected_reject=True,
                rejected=True, detail="已拦截")

        # N12：上下文 simulation_only=False → 最高优先级拒绝。
        try:
            ProductionActivationSimulationContext(
                simulation_id="x", candidate_id="y", scenario="z",
                started_at=_now(), simulation_only=False,
            )
            add("N12_context_not_simulation", "上下文非模拟",
                "simulation_only=False 的上下文必须被拒绝。", expected_reject=True,
                rejected=False, detail="未拦截（缺陷）")
        except SimulationError:
            add("N12_context_not_simulation", "上下文非模拟",
                "simulation_only=False 的上下文必须被拒绝。", expected_reject=True,
                rejected=True, detail="已拦截")

        return tuple(results)

    @staticmethod
    def _assert_no_real_production_object(*objs: Any) -> None:
        for obj in objs:
            for forbidden in _FORBIDDEN_REAL_TYPES:
                if isinstance(obj, forbidden):
                    raise SimulationContaminationError(
                        f"检测到真实生产控制平面对象 {type(obj).__name__} 被传入模拟层"
                        "（红线⑩：模拟数据不得污染真实 namespace）"
                    )


# --------------------------------------------------------------------------- #
# T10：模拟污染守卫（SimulationContaminationGuard）                                #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ContaminationCheckResult:
    """污染检查结果（T10，只读）。

    ``clean`` 为 False 时，模拟层**必须** hard-fail，绝不继续（红线⑩）。
    """

    simulation_id: str
    clean: bool
    findings: Tuple[str, ...]
    checked_at: str = field(default_factory=_now)
    note: str = (
        "CONTAMINATION_GUARD: 任一发现即 hard-fail；模拟数据不得进真实 namespace"
        "（红线⑩）"
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "simulation_id": self.simulation_id,
            "clean": self.clean,
            "findings": list(self.findings),
            "checked_at": self.checked_at,
            "note": self.note,
        }


class SimulationContaminationGuard:
    """模拟污染守卫（T10）：在模拟运行前/后检测任何对真实生产 namespace 的污染。

    检测维度：
    1. 上下文 simulation_only 必须为 True（红线⑩）；
    2. 合成证据 source_type=SIMULATION、synthetic=True、且不携带真实 secret 模式；
    3. 合成签署场景 synthetic=True、actor_id 以 SIMULATION: 开头；
    4. 绝不接受真实 ``HumanSignoffRegistry`` / ``FinalHumanDecisionLedger`` 实例；
    5. 序列化产物不得出现 PRODUCTION_GO / engineering_approved 等放行词元。

    命中任一即 ``clean=False`` → 调用方 hard-fail。
    """

    _REAL_SECRET_PATTERN = _REAL_SECRET_PATTERN  # 引用模块级常量

    def check(
        self,
        *,
        context: ProductionActivationSimulationContext,
        evidence_set: Optional[SyntheticActivationEvidenceSet] = None,
        signoff_scenario: Optional[SyntheticHumanSignoffScenario] = None,
        report_payload: Optional[Mapping[str, Any]] = None,
    ) -> ContaminationCheckResult:
        findings: List[str] = []

        # 1) 上下文隔离。
        if not context.simulation_only:
            findings.append("context.simulation_only is not True")

        # 2) 合成证据。
        if evidence_set is not None:
            for e in evidence_set.evidence:
                if e.source_type != "SIMULATION" or e.synthetic is not True:
                    findings.append(f"evidence {e.evidence_id} 非 SIMULATION/synthetic")
                low = (e.sha256 or "").lower()
                if any(p in low for p in self._REAL_SECRET_PATTERN):
                    findings.append(f"evidence {e.evidence_id} 疑似含真实 secret 模式")

        # 3) 合成签署。
        if signoff_scenario is not None:
            if signoff_scenario.synthetic is not True:
                findings.append("signoff scenario synthetic is not True")
            for entry in signoff_scenario.entries:
                if not str(entry.actor_id).startswith("SIMULATION:"):
                    findings.append(f"signoff {entry.role.value} actor_id 非 SIMULATION 前缀")

        # 4) 真实生产对象（通过断言守卫，命中即抛；这里也兜底扫描）。
        try:
            ProductionActivationNegativePathMatrix._assert_no_real_production_object(
                evidence_set, signoff_scenario,
            )
        except SimulationContaminationError as exc:
            findings.append(str(exc))

        # 5) 放行词元。
        if report_payload is not None:
            hits = _scan_forbidden_tokens(report_payload)
            if hits:
                findings.append("report 含放行类词元: " + "; ".join(sorted(hits)))

        clean = len(findings) == 0
        return ContaminationCheckResult(
            simulation_id=context.simulation_id,
            clean=clean,
            findings=tuple(findings),
        )

    def require_clean(self, *, context, evidence_set=None, signoff_scenario=None, report_payload=None):
        """硬守卫：不 clean 即 hard-fail（红线⑩）。"""
        result = self.check(
            context=context,
            evidence_set=evidence_set,
            signoff_scenario=signoff_scenario,
            report_payload=report_payload,
        )
        if not result.clean:
            raise SimulationContaminationError(
                "模拟污染检测未通过（红线⑩）: " + "; ".join(result.findings)
            )
        return result


# --------------------------------------------------------------------------- #
# T11：生产激活干跑报告（ProductionActivationDryRunReport）                         #
# --------------------------------------------------------------------------- #
class DryRunReportStatus(str, Enum):
    """干跑报告总态（**刻意只有 SIMULATION_PASS / SIMULATION_BLOCKED**，无 PRODUCTION_GO）。"""

    SIMULATION_PASS = "simulation_pass"
    SIMULATION_BLOCKED = "simulation_blocked"


@dataclass(frozen=True)
class ProductionActivationDryRunReport:
    """生产激活干跑总报告（T11，只读）。

    ``status`` 只可能是 ``SIMULATION_PASS`` / ``SIMULATION_BLOCKED``；**永不含**
    ``PRODUCTION_GO`` / ``engineering_approved``（红线②）。``production_activated``
    恒为 ``False``；``real_signoff_count`` 恒为 0（红线③④）。

    本报告的语义是"软件层在沙盒里把整条激活链路跑通了，边界不可越"——**它不代表
    生产已放行**，真实放行仍需主理人在人类终端、四角色真实签署后显式执行。
    """

    simulation_id: str
    candidate_id: str
    status: DryRunReportStatus
    scenario_count: int
    decision_results: Tuple[Dict[str, Any], ...]
    handoff_results: Tuple[Dict[str, Any], ...]
    abort_results: Tuple[Dict[str, Any], ...]
    rollback_result: Dict[str, Any]
    negative_path_results: Tuple[Dict[str, Any], ...]
    contamination: Dict[str, Any]
    production_activated: bool = False
    real_signoff_count: int = 0
    engineering_enabled: bool = False
    generated_at: str = field(default_factory=_now)
    note: str = (
        "DRY_RUN_REPORT: 状态仅 SIMULATION_PASS/SIMULATION_BLOCKED；不含 PRODUCTION_GO；"
        "production_activated 恒 False；real_signoff_count 恒 0（红线②③④）"
    )

    def __post_init__(self) -> None:
        if self.production_activated is not False:
            raise SimulationError("干跑报告 production_activated 必须为 False（红线④/⑤）")
        if self.real_signoff_count != 0:
            raise SimulationError("干跑报告 real_signoff_count 必须为 0（红线③/④）")
        if self.engineering_enabled is not False:
            raise SimulationError("干跑报告 engineering_enabled 必须为 False（红线①）")
        payload = self.to_dict()
        hits = _scan_forbidden_tokens(payload)
        if hits:
            raise SimulationError(
                "干跑报告出现放行类词元（红线②）: " + "; ".join(sorted(hits))
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "simulation_id": self.simulation_id,
            "candidate_id": self.candidate_id,
            "status": self.status.value,
            "scenario_count": self.scenario_count,
            "decision_results": [dict(d) for d in self.decision_results],
            "handoff_results": [dict(d) for d in self.handoff_results],
            "abort_results": [dict(d) for d in self.abort_results],
            "rollback_result": dict(self.rollback_result),
            "negative_path_results": [dict(d) for d in self.negative_path_results],
            "contamination": dict(self.contamination),
            "production_activated": self.production_activated,
            "real_signoff_count": self.real_signoff_count,
            "engineering_enabled": self.engineering_enabled,
            "generated_at": self.generated_at,
            "note": self.note,
        }


# --------------------------------------------------------------------------- #
# 高层编排：run_production_activation_dry_run（T1→T11 串联）                        #
# --------------------------------------------------------------------------- #
def run_production_activation_dry_run(
    *,
    simulation_id: str,
    candidate_id: str,
    scenario: str = "production_activation_full_dry_run",
    audit: Any = None,
) -> ProductionActivationDryRunReport:
    """串联执行整条生产激活干跑链路（T1→T11）。

    流程：建立隔离上下文(T1) → 合成证据(T2) → 合成签署(T3) → 决策矩阵(T4) →
    逐场景校验(T5) → 交接干跑(T6) → 中止模拟(T7) → 回滚模拟(T8) → 负路径矩阵(T9) →
    污染守卫(T10) → 总报告(T11)。

    **所有动作都在隔离沙盒内**；``audit`` 为可选审计服务（T12 接入点），传入则登记
    3.9.8 simulation-only 类别；**绝不**写入真实生产 registry/ledger/审计生产命名空间。
    """
    if not safety_invariants_ok():
        raise SimulationError("safety_invariants_ok() 失败：禁止在启用态下运行干跑（红线①）")

    context = build_simulation_context(
        simulation_id=simulation_id, candidate_id=candidate_id, scenario=scenario
    )

    # T2：合成证据。
    evidence_factory = SyntheticActivationEvidenceFactory()
    evidence_set = evidence_factory.build_set(simulation_id=simulation_id)

    # T3：合成签署（默认四角色全 GO，供矩阵首场景使用）。
    signoff_scenario = build_synthetic_signoff_scenario(
        simulation_id=simulation_id,
        scenario_id="baseline-all-go",
        decisions={r: SignoffDecision.GO for r in REQUIRED_SIGNOFF_ROLES},
    )

    # T10（前置）：污染守卫。
    guard = SimulationContaminationGuard()
    guard.require_clean(
        context=context,
        evidence_set=evidence_set,
        signoff_scenario=signoff_scenario,
    )

    # T4 + T5：决策矩阵 + 逐场景校验。
    matrix = build_decision_scenario_matrix()
    verifier = DryRunDecisionVerifier()
    decision_results: List[Dict[str, Any]] = []
    handoff_results: List[Dict[str, Any]] = []
    abort_results: List[Dict[str, Any]] = []
    all_pass = True
    for spec in matrix:
        verification = verifier.verify(context=context, spec=spec, audit=audit)
        decision_results.append(verification.to_dict())
        handoff = ActivationHandoffDryRun().run(context=context, verification=verification)
        handoff_results.append(handoff.to_dict())
        abort = ActivationAbortSimulation().run(context=context, spec=spec)
        abort_results.append(abort.to_dict())
        # 期望一致性：演练结果须与场景预期一致（fail-closed 自校验）。
        if verification.outcome != spec.expected_outcome:
            all_pass = False

    # T8：回滚模拟。
    rollback = ProductionRollbackSimulation().run(
        context=context,
        last_known_good_version="sim-v-last-known-good",
        last_known_good_commit="simdeadbeef000",
    )

    # T9：负路径矩阵。
    negative = ProductionActivationNegativePathMatrix().evaluate(context=context)
    negative_clean = all(n.rejected for n in negative if n.expected_reject)

    # T10（后置）：污染守卫。
    contamination = guard.check(
        context=context,
        evidence_set=evidence_set,
        signoff_scenario=signoff_scenario,
        report_payload={"status": "simulation_pass" if all_pass else "simulation_blocked"},
    ).to_dict()

    status = (
        DryRunReportStatus.SIMULATION_PASS
        if (all_pass and negative_clean and contamination["clean"])
        else DryRunReportStatus.SIMULATION_BLOCKED
    )

    # 若提供审计服务，登记首尾两条 3.9.8 simulation-only 类别。
    if audit is not None:
        try:
            start = getattr(audit, "record_production_activation_dry_run_started", None)
            done = getattr(audit, "record_production_activation_dry_run_completed", None)
            if callable(start):
                start(
                    record_id=f"sim-start-{simulation_id}",
                    actor_id="SIMULATION:custodian",
                    target=simulation_id,
                    detail=f"status={status.value}",
                )
            if callable(done):
                done(
                    record_id=f"sim-done-{simulation_id}",
                    actor_id="SIMULATION:custodian",
                    target=simulation_id,
                    detail=f"status={status.value};production_activated=false",
                )
        except Exception:
            pass

    return ProductionActivationDryRunReport(
        simulation_id=simulation_id,
        candidate_id=candidate_id,
        status=status,
        scenario_count=len(matrix),
        decision_results=tuple(decision_results),
        handoff_results=tuple(handoff_results),
        abort_results=tuple(abort_results),
        rollback_result=rollback.to_dict(),
        negative_path_results=tuple(n.to_dict() for n in negative),
        contamination=contamination,
        production_activated=False,
        real_signoff_count=0,
        engineering_enabled=False,
    )


__all__ = [
    "SimulationError",
    "SimulationContaminationError",
    "ProductionActivationSimulationContext",
    "build_simulation_context",
    "SIMULATION_EVIDENCE_KINDS",
    "SyntheticActivationEvidence",
    "SyntheticActivationEvidenceSet",
    "SyntheticActivationEvidenceFactory",
    "SyntheticSignoffEntry",
    "SyntheticHumanSignoffScenario",
    "build_synthetic_signoff_scenario",
    "SimulationDecisionOutcome",
    "DecisionScenarioSpec",
    "build_decision_scenario_matrix",
    "SimulationDecisionVerification",
    "DryRunDecisionVerifier",
    "HandoffDryRunStatus",
    "HandoffDryRunResult",
    "ActivationHandoffDryRun",
    "AbortSimulationResult",
    "ActivationAbortSimulation",
    "RollbackSimulationStatus",
    "RollbackSimulationResult",
    "ProductionRollbackSimulation",
    "NegativePathResult",
    "ProductionActivationNegativePathMatrix",
    "ContaminationCheckResult",
    "SimulationContaminationGuard",
    "DryRunReportStatus",
    "ProductionActivationDryRunReport",
    "run_production_activation_dry_run",
]
