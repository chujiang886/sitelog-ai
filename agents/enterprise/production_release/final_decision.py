"""Phase 3.9.6 最终人工裁决契约（T9）—— 登记人的决定，永不代替人决定。

与 Phase 3.9.2 ``human_approval.py`` 的分工
-------------------------------------------
``HumanActivationApproval`` 回答"人批了吗"；本模块回答一个更尖锐的问题：
**人是基于哪一份材料批的？**

真实治理事故里最常见的一类不是"没人签字"，而是"签字对应的材料已经变了"——
评审会看的是 A 版证据清单，落地放行时系统手上却是 B 版。因此
``FinalHumanActivationDecision`` 强制绑定它所依据的评审包摘要
（``reviewed_package_digest``，由 T8 评审包**现算**而非调用方声明），并提供
``binds_to()`` 做事后复核：材料一旦变动，绑定即失效，裁决自动不可复用。

三条不可让渡的契约
------------------
1. **裁决只能来自真实自然人**：``decided_by_kind`` 强制 ``user``，且必须提供
   ``signature_reference``（线下签署件 / 工单 / 邮件存档坐标）。AI 调用工厂
   传 ai / system 直接抛错（红线③⑨）。
2. **裁决必须有材料依据**：工厂只接受真实 ``FinalActivationReviewPackage`` 实例，
   摘要由本模块现算；``GO`` 裁决要求该评审包就绪度为
   ``READY_FOR_HUMAN_FINAL_REVIEW`` —— 机器不阻止人做决定，但拒绝把"基于不齐
   材料的 GO"登记为有效裁决（红线④⑩）。
3. **裁决 ≠ 激活**：``activation_execution`` 恒为
   ``PENDING_HUMAN_TERMINAL_ACTION``，本模块不翻转 ``engineering_enabled``、
   不产出 ``engineering_approved``、不宣布 Production GO；即便 outcome 为 GO，
   激活动作仍须主理人在人类终端显式执行（红线①②⑤）。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

from agents.config_loader import load_engineering_enabled
from agents.enterprise.audit import AuditActorKind, AuditService, require_human_actor
from agents.enterprise.production_release.review_package import (
    FinalActivationReviewPackage,
    ReviewPackageReadiness,
)
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class FinalHumanDecisionError(EnterpriseRedLineViolationError):
    """最终人工裁决契约被违反（继承红线异常，调用方 fail-closed）。"""


#: 裁决者必须是真实自然人。
REQUIRED_DECIDER_KIND = "user"


# --------------------------------------------------------------------------- #
# 枚举                                                                          #
# --------------------------------------------------------------------------- #
class FinalDecisionOutcome(str, Enum):
    """真实人工最终裁决结果（**记录**人的决定，不是 AI 的结论）。"""

    GO = "go"
    NO_GO = "no_go"
    #: 延后：材料不足或存在争议，需补充后重新评审。
    DEFER = "defer"


class ActivationExecutionState(str, Enum):
    """激活执行态 —— 本模块能表达的取值只有一个。

    刻意只保留 ``PENDING_HUMAN_TERMINAL_ACTION``：任何"已激活"语义都不在软件
    层产生，只能是主理人在人类终端操作后的现实事实（红线①⑤⑥）。
    """

    PENDING_HUMAN_TERMINAL_ACTION = "pending_human_terminal_action"


#: 本模块禁止出现的越权方法名（叠加在裁决服务上）。
_FINAL_DECISION_FORBIDDEN: Tuple[str, ...] = (
    "decide",
    "auto_decide",
    "make_final_decision",
    "create_human_decision",
    "fabricate_decision",
    "sign_as_human",
    "forge_signature",
    "approve_activation",
    "mark_activation_approved",
    "declare_production_go",
    "activate",
    "auto_activate",
    "execute_activation",
    "enable_engineering",
    "set_engineering_enabled",
    "override_human_decision",
    "modify_human_decision",
    "delete_human_decision",
    "rewrite_decision_history",
    "bypass_review_package",
    "skip_package_binding",
)


# --------------------------------------------------------------------------- #
# 评审包摘要（裁决与材料的绑定锚点）                                              #
# --------------------------------------------------------------------------- #
def compute_review_package_digest(package: FinalActivationReviewPackage) -> str:
    """对评审包做规范化 JSON 后求 SHA-256，作为裁决绑定锚点。

    使用 ``sort_keys=True`` + ``ensure_ascii=False`` 保证同一份材料在任何机器上
    得到同一摘要；``generated_at`` 参与计算是**刻意**的 —— 每次重新生成的评审包
    都是一份新材料，裁决必须绑定到人真正看过的那一份。
    """
    payload = json.dumps(
        package.to_dict(), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# T9：最终人工裁决记录                                                           #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class FinalHumanActivationDecision:
    """一条**已经发生**的真实人工最终裁决（只读事实）。

    本结构不授权任何事情。它唯一的作用是让"谁、在什么时候、基于哪一份材料、
    做了什么决定、凭什么凭证"变成可审计、可复核、可推翻的事实。
    """

    decision_id: str
    rc_id: str
    outcome: FinalDecisionOutcome
    decided_by: str
    decided_by_kind: str
    decided_at: str
    signature_reference: str
    reason: str

    reviewed_package_id: str
    reviewed_package_digest: str
    reviewed_package_readiness: str
    reviewed_evidence_count: int = 0
    reviewed_signoff_roles: Tuple[str, ...] = field(default_factory=tuple)

    conditions: Tuple[str, ...] = field(default_factory=tuple)
    engineering_enabled_at_decision: bool = False
    activation_execution: ActivationExecutionState = (
        ActivationExecutionState.PENDING_HUMAN_TERMINAL_ACTION
    )
    superseded: bool = False

    note: str = (
        "HUMAN_DECISION_RECORD_ONLY: 如实登记真实人工裁决；AI 不构造、不代决、不改写；"
        "登记 GO 亦不翻转 engineering_enabled、不宣布上线；激活由主理人在人类终端执行"
    )

    def __post_init__(self) -> None:
        if self.decided_by_kind.strip().lower() != REQUIRED_DECIDER_KIND:
            raise FinalHumanDecisionError(
                f"最终裁决必须由真实自然人作出（decided_by_kind='user'），"
                f"实得 {self.decided_by_kind!r}（红线③⑨）"
            )
        if self.activation_execution is not (
            ActivationExecutionState.PENDING_HUMAN_TERMINAL_ACTION
        ):
            raise FinalHumanDecisionError(
                "裁决记录不得表达任何已激活语义（红线①⑤⑥）"
            )
        if self.engineering_enabled_at_decision is not False:
            raise FinalHumanDecisionError(
                "裁决登记时 engineering_enabled 必须为 False（红线①）"
            )

    # -- 派生只读事实 ---------------------------------------------------- #

    @property
    def decided_by_real_user(self) -> bool:
        return self.decided_by_kind.strip().lower() == REQUIRED_DECIDER_KIND

    @property
    def is_go(self) -> bool:
        """人是否作出了 GO 裁决（**不代表系统已放行**）。"""
        return self.outcome is FinalDecisionOutcome.GO and self.decided_by_real_user

    @property
    def is_blocking(self) -> bool:
        return self.outcome in (FinalDecisionOutcome.NO_GO, FinalDecisionOutcome.DEFER)

    @property
    def has_conditions(self) -> bool:
        return bool(self.conditions)

    def binds_to(self, package: FinalActivationReviewPackage) -> bool:
        """核对本裁决是否确实针对给定评审包（ID + 摘要双重匹配）。

        材料只要发生任何变动（哪怕只多了一条证据），摘要即改变，绑定失效 ——
        这正是本契约的价值：**旧裁决不能被复用到新材料上**。
        """
        return (
            self.reviewed_package_id == package.package_id
            and self.reviewed_package_digest == compute_review_package_digest(package)
        )

    def assert_not_activated(self) -> None:
        """显式断言：本裁决未、也不能表达"已激活"（红线①⑤⑥）。"""
        if self.activation_execution is not (
            ActivationExecutionState.PENDING_HUMAN_TERMINAL_ACTION
        ):
            raise FinalHumanDecisionError("裁决记录出现非法激活态（红线①）")
        if self.engineering_enabled_at_decision:
            raise FinalHumanDecisionError(
                "裁决登记时 engineering_enabled 为真，违反红线①"
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "rc_id": self.rc_id,
            "outcome": self.outcome.value,
            "decided_by": self.decided_by,
            "decided_by_kind": self.decided_by_kind,
            "decided_at": self.decided_at,
            "signature_reference": self.signature_reference,
            "reason": self.reason,
            "reviewed_package_id": self.reviewed_package_id,
            "reviewed_package_digest": self.reviewed_package_digest,
            "reviewed_package_readiness": self.reviewed_package_readiness,
            "reviewed_evidence_count": self.reviewed_evidence_count,
            "reviewed_signoff_roles": list(self.reviewed_signoff_roles),
            "conditions": list(self.conditions),
            "engineering_enabled_at_decision": self.engineering_enabled_at_decision,
            "activation_execution": self.activation_execution.value,
            "superseded": self.superseded,
            "is_go": self.is_go,
            "is_blocking": self.is_blocking,
            "note": self.note,
        }


def build_final_human_activation_decision(
    *,
    decision_id: str,
    outcome: FinalDecisionOutcome,
    decided_by: str,
    decided_by_kind: str,
    signature_reference: str,
    reason: str,
    package: FinalActivationReviewPackage,
    conditions: Sequence[str] = (),
    decided_at: Optional[str] = None,
) -> FinalHumanActivationDecision:
    """登记一条**已经发生**的真实人工最终裁决。

    这不是"做决定"，而是"如实记录决定已作出"。因此每一项真实性要件都是硬性的：

    * ``decided_by_kind`` 必须为 ``user``；
    * ``decided_by`` / ``signature_reference`` / ``reason`` 均非空 ——
      无凭证、无理由的裁决不可采信；
    * ``package`` 必须是真实评审包实例，摘要由本函数**现算**（调用方无法声明摘要，
      从而无法把裁决"贴"到一份它没看过的材料上）；
    * ``GO`` 裁决要求评审包就绪度为 ``READY_FOR_HUMAN_FINAL_REVIEW``：
      材料没齐就登记 GO，是治理失效而非人的自由（红线④⑩）。
      ``NO_GO`` / ``DEFER`` 在任何就绪度下均可登记 —— 阻断永远允许。
    """

    if not safety_invariants_ok():
        raise FinalHumanDecisionError(
            "safety_invariants_ok() 失败：禁止在启用态下登记最终裁决（红线①）"
        )
    engineering_enabled = load_engineering_enabled()
    if engineering_enabled is not False:
        raise FinalHumanDecisionError(
            f"engineering_enabled 必须为 False，实测 {engineering_enabled!r}（红线①）"
        )
    if decided_by_kind.strip().lower() != REQUIRED_DECIDER_KIND:
        raise FinalHumanDecisionError(
            "final activation decision must be made by a real human user "
            f"(decided_by_kind='user'), got {decided_by_kind!r}"
        )
    if not str(decided_by).strip():
        raise FinalHumanDecisionError("final decision requires a real decided_by")
    if not str(signature_reference).strip():
        raise FinalHumanDecisionError(
            "final decision requires a real signature_reference "
            "(offline signed document / ticket / archived approval)"
        )
    if not str(reason).strip():
        raise FinalHumanDecisionError(
            "final decision requires a non-empty reason（无理由的裁决不可采信）"
        )
    if not isinstance(package, FinalActivationReviewPackage):
        raise FinalHumanDecisionError(
            "final decision must be bound to a real FinalActivationReviewPackage"
        )

    # 评审包自身红线自检（材料若已越权，裁决不得建立在其之上）。
    package.assert_no_activation_conclusion()

    if (
        outcome is FinalDecisionOutcome.GO
        and package.readiness is not ReviewPackageReadiness.READY_FOR_HUMAN_FINAL_REVIEW
    ):
        raise FinalHumanDecisionError(
            "cannot register a GO decision on an incomplete review package "
            f"(readiness={package.readiness.value}); 未决项："
            + "; ".join(package.outstanding_items[:5])
        )

    return FinalHumanActivationDecision(
        decision_id=decision_id,
        rc_id=package.rc_id,
        outcome=outcome,
        decided_by=str(decided_by),
        decided_by_kind=REQUIRED_DECIDER_KIND,
        decided_at=decided_at or _now(),
        signature_reference=str(signature_reference),
        reason=str(reason),
        reviewed_package_id=package.package_id,
        reviewed_package_digest=compute_review_package_digest(package),
        reviewed_package_readiness=package.readiness.value,
        reviewed_evidence_count=len(package.evidence_index),
        reviewed_signoff_roles=tuple(
            package.signoff_snapshot.get("signed_roles", []) or ()
        ),
        conditions=tuple(conditions),
        engineering_enabled_at_decision=False,
    )


# --------------------------------------------------------------------------- #
# 裁决登记簿（append-only）                                                      #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class FinalDecisionLedgerSnapshot:
    """裁决登记簿只读快照。"""

    rc_id: str
    total_decisions: int
    effective_decision: Optional[Dict[str, Any]]
    superseded_decisions: Tuple[Dict[str, Any], ...]
    human_go_recorded: bool
    blocking_recorded: bool
    generated_at: str
    note: str = (
        "DECISION_LEDGER_SNAPSHOT: 只读聚合；human_go_recorded 仅表示"
        "真实人工已登记 GO 裁决，不等于系统已放行、更不等于已激活"
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rc_id": self.rc_id,
            "total_decisions": self.total_decisions,
            "effective_decision": (
                dict(self.effective_decision) if self.effective_decision else None
            ),
            "superseded_decisions": [dict(d) for d in self.superseded_decisions],
            "human_go_recorded": self.human_go_recorded,
            "blocking_recorded": self.blocking_recorded,
            "generated_at": self.generated_at,
            "note": self.note,
        }


class FinalHumanDecisionLedger(_RedLineForbiddenMixin):
    """最终人工裁决登记簿（T9，append-only，只登记不裁决）。

    * **append-only**：``record()`` 只追加；改判以新记录覆盖，旧记录标记
      ``superseded`` 并完整保留 —— 撤回一次 GO 这件事本身必须留痕；
    * **不代决**：``_FORBIDDEN`` 结构性拦截 ``decide`` / ``approve_activation`` /
      ``activate`` / ``override_human_decision`` 等一切越权动词；
    * **不放行**：即便 ``human_go_recorded`` 为真，登记簿也不翻转
      ``engineering_enabled``、不宣布上线。
    """

    _FORBIDDEN = _FINAL_DECISION_FORBIDDEN

    def __init__(self, *, rc_id: str, audit: AuditService) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构建裁决登记簿（红线①）"
            )
        if not str(rc_id).strip():
            raise FinalHumanDecisionError("decision ledger requires a real rc_id")
        self._rc_id = str(rc_id).strip()
        self._audit = audit
        self._decisions: List[FinalHumanActivationDecision] = []

    @property
    def rc_id(self) -> str:
        return self._rc_id

    @property
    def decisions(self) -> Tuple[FinalHumanActivationDecision, ...]:
        return tuple(self._decisions)

    def record(
        self,
        *,
        actor_kind: AuditActorKind,
        decision: FinalHumanActivationDecision,
    ) -> FinalHumanActivationDecision:
        """追加一条真实人工裁决并审计留痕。

        校验：调用者为真实 USER、裁决归属同一 RC、裁决自身未表达激活态。
        """
        require_human_actor(actor_kind)
        if decision.rc_id != self._rc_id:
            raise FinalHumanDecisionError(
                f"decision rc_id mismatch: ledger={self._rc_id!r}, "
                f"decision={decision.rc_id!r}"
            )
        if not decision.decided_by_real_user:
            raise FinalHumanDecisionError(
                "only a real human decision can be recorded (decided_by_kind='user')"
            )
        decision.assert_not_activated()

        self._decisions.append(decision)
        self._audit.record_human_activation_approval_recorded(
            record_id=f"fhd-{decision.decision_id}",
            actor_id=decision.decided_by,
            action=f"record_final_human_decision_{decision.outcome.value}",
            target=f"{self._rc_id}:{decision.reviewed_package_id}",
            detail=(
                f"outcome={decision.outcome.value};"
                f"package_digest={decision.reviewed_package_digest[:16]};"
                f"readiness={decision.reviewed_package_readiness};"
                f"conditions={len(decision.conditions)};"
                "engineering_enabled=false;activation_executed=false"
            ),
            ts=decision.decided_at,
        )
        return decision

    # -- 只读聚合 --------------------------------------------------------- #

    def effective(self) -> Optional[FinalHumanActivationDecision]:
        """当前有效裁决（最后一条；早前裁决视为被取代）。"""
        return self._decisions[-1] if self._decisions else None

    def superseded(self) -> Tuple[FinalHumanActivationDecision, ...]:
        return tuple(self._decisions[:-1]) if len(self._decisions) > 1 else ()

    def human_go_recorded(self) -> bool:
        """真实人工是否已登记 GO 裁决（**仅此而已**）。"""
        current = self.effective()
        return bool(current and current.is_go)

    def verify_binding(self, package: FinalActivationReviewPackage) -> Dict[str, Any]:
        """只读核对当前有效裁决是否绑定到给定评审包。

        用于放行前的最后一次一致性复核：若人批的材料与当下材料不是同一份，
        ``bound`` 为 False —— 此时任何"沿用旧批准"的行为都应被拒绝。
        """
        current = self.effective()
        if current is None:
            return {
                "bound": False,
                "reason": "no human decision recorded",
                "note": "VERIFY_ONLY: 不放行、不激活",
            }
        bound = current.binds_to(package)
        return {
            "bound": bound,
            "decision_id": current.decision_id,
            "outcome": current.outcome.value,
            "expected_digest": current.reviewed_package_digest,
            "actual_digest": compute_review_package_digest(package),
            "reason": "" if bound else "review package changed since the human decision",
            "note": "VERIFY_ONLY: 绑定成立也不代表放行；激活由主理人在人类终端执行",
        }

    def snapshot(self) -> FinalDecisionLedgerSnapshot:
        current = self.effective()
        return FinalDecisionLedgerSnapshot(
            rc_id=self._rc_id,
            total_decisions=len(self._decisions),
            effective_decision=current.to_dict() if current else None,
            superseded_decisions=tuple(
                {**d.to_dict(), "superseded": True} for d in self.superseded()
            ),
            human_go_recorded=self.human_go_recorded(),
            blocking_recorded=bool(current and current.is_blocking),
            generated_at=_now(),
        )


__all__ = [
    "FinalHumanDecisionError",
    "REQUIRED_DECIDER_KIND",
    "FinalDecisionOutcome",
    "ActivationExecutionState",
    "compute_review_package_digest",
    "FinalHumanActivationDecision",
    "build_final_human_activation_decision",
    "FinalDecisionLedgerSnapshot",
    "FinalHumanDecisionLedger",
]
