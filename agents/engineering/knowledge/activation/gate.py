"""Knowledge Activation Gate（Phase 3.4 Sprint 3.4.1, Task 1）。

KnowledgeActivationGate.can_activate_knowledge(repository, *, context=None)
-> ActivationDecision(allowed, blocking_reasons, gate_results, detail)

检查 G1–G6（知识域适配自 enable_gate.py）：

- G1  knowledge_governance : 治理护栏 ok（engineering_enabled=False）+ 存在 Engineering_Approved 候选。
- G2  dual_sign             : 候选 item 的审核链含专家 + 工程双签 verify 事件。
- G3  ci_status             : local_ci 8/8 全绿（注入，默认红）。
- G4  audit_chain           : 候选 item 审计链完整（create + verify，无 forbidden approved）。
- G5  rollback_ready        : 回滚就绪（注入，默认不就绪）。
- G6  authorization         : 主理人单独书面授权（ReleaseApproval）到位（注入，默认缺失）。

语义边界（红线，与 can_enable_engineering 一致）：
- 默认拒绝（fail-closed）：所有外部条件默认不满足 → (False, reasons)。
- 本类**只判定**是否允许激活，**绝不**翻转 engineering_enabled、
  不输出 engineering_approved、不创建 ReleaseApproval、不修改 verified.json。
- 真实激活仍须主理人在 config 显式置 orchestrator.engineering_enabled=true
  并经 G6 书面授权（SoD 独立于双签），违反红线由 config_loader 拦截。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from agents.config_loader import load_engineering_enabled
from agents.engineering.knowledge.repository import KnowledgeRepository

# Gate 标识
G_KNOWLEDGE_GOVERNANCE: str = "G1"
G_DUAL_SIGN: str = "G2"
G_CI: str = "G3"
G_AUDIT_CHAIN: str = "G4"
G_ROLLBACK: str = "G5"
G_AUTHORIZATION: str = "G6"

ALL_GATES: tuple[str, ...] = (
    G_KNOWLEDGE_GOVERNANCE,
    G_DUAL_SIGN,
    G_CI,
    G_AUDIT_CHAIN,
    G_ROLLBACK,
    G_AUTHORIZATION,
)

# 门禁原因码（与设计文档 phase3.4.0 对齐）
GATE_G1_GOVERNANCE = "G1_knowledge_governance_incomplete"
GATE_G2_DUAL_SIGN = "G2_dual_sign_incomplete"
GATE_G3_CI = "G3_ci_not_green"
GATE_G4_AUDIT_CHAIN = "G4_audit_chain_incomplete"
GATE_G5_ROLLBACK = "G5_rollback_not_ready"
GATE_G6_AUTHORIZATION = "G6_authorization_missing"

APPROVED_STATUS: str = "Engineering_Approved"
FORBIDDEN_EVENT_TYPE: str = "approved"

# 双签 actor 标记（审核链 verify 事件的 actor 字段判定）
_EXPERT_MARKERS: tuple[str, ...] = ("expert",)
_ENGINEER_MARKERS: tuple[str, ...] = ("engineer", "mgmt", "manager")


@dataclass
class ActivationContext:
    """门禁所需的外部信号（全部可选；缺失 => 默认不满足 => 默认 fail-closed）。"""

    ci_green: Optional[bool] = None
    rollback_ready: Optional[bool] = None
    authorization_present: Optional[bool] = None
    dual_sign_present: Optional[bool] = None  # 显式注入；None => 从 repo 审核链推导
    require_audit_chain: bool = True


@dataclass
class ActivationDecision:
    """单次激活判定结果。"""

    allowed: bool
    blocking_reasons: list[str] = field(default_factory=list)
    gate_results: dict[str, bool] = field(default_factory=dict)
    detail: str = ""


class KnowledgeActivationGate:
    """Task 1：知识激活判定门禁（只读判定，fail-closed）。"""

    # ------------------------------------------------------------------ #
    # 主入口
    # ------------------------------------------------------------------ #
    def can_activate_knowledge(
        self,
        repository: Any,
        *,
        context: Optional[ActivationContext] = None,
    ) -> ActivationDecision:
        """判定是否允许将知识库激活为 Engineering AI 权威依据。

        返回 (allowed, blocking_reasons, gate_results, detail)。
        红线：不翻转 engineering_enabled、不输出 approved、不创建 ReleaseApproval。
        """
        if not isinstance(repository, KnowledgeRepository):
            return ActivationDecision(
                allowed=False,
                blocking_reasons=["G0_repository_required"],
                gate_results={},
                detail="repository 缺失或非 KnowledgeRepository 实例",
            )

        ctx = context or ActivationContext()
        reasons: list[str] = []
        results: dict[str, bool] = {}

        # G1 knowledge_governance
        ok, r = self._g1_knowledge_governance(repository, ctx)
        results[G_KNOWLEDGE_GOVERNANCE] = ok
        if not ok:
            reasons.append(r)

        # G2 dual_sign
        ok, r = self._g2_dual_sign(repository, ctx)
        results[G_DUAL_SIGN] = ok
        if not ok:
            reasons.append(r)

        # G3 ci_status
        ok, r = self._g3_ci(ctx)
        results[G_CI] = ok
        if not ok:
            reasons.append(r)

        # G4 audit_chain
        ok, r = self._g4_audit_chain(repository, ctx)
        results[G_AUDIT_CHAIN] = ok
        if not ok:
            reasons.append(r)

        # G5 rollback_ready
        ok, r = self._g5_rollback(ctx)
        results[G_ROLLBACK] = ok
        if not ok:
            reasons.append(r)

        # G6 authorization
        ok, r = self._g6_authorization(ctx)
        results[G_AUTHORIZATION] = ok
        if not ok:
            reasons.append(r)

        # 红线：本方法绝不调用任何会翻转 engineering_enabled / 写 verified.json /
        # 创建 ReleaseApproval 的代码。allowed 仅为判定结论。
        allowed = len(reasons) == 0 and all(results.values())
        detail = (
            "激活允许" if allowed else f"激活被阻止，原因 {len(reasons)} 项（fail-closed）"
        )
        return ActivationDecision(
            allowed=allowed,
            blocking_reasons=reasons,
            gate_results=results,
            detail=detail,
        )

    # ------------------------------------------------------------------ #
    # 各门禁（全部 fail-closed）
    # ------------------------------------------------------------------ #
    @staticmethod
    def _g1_knowledge_governance(
        repo: KnowledgeRepository, _ctx: ActivationContext
    ) -> tuple[bool, str]:
        """G1：治理护栏 + 存在 Engineering_Approved 候选。"""
        if not repo.safety_invariants_ok():
            return (
                False,
                f"{GATE_G1_GOVERNANCE}:safety_invariants_not_ok(engineering_enabled 必须为 False)",
            )
        approved = repo.query(validation_status=APPROVED_STATUS)
        if not approved:
            return False, f"{GATE_G1_GOVERNANCE}:no_Engineering_Approved_candidate"
        return True, ""

    @staticmethod
    def _g2_dual_sign(
        repo: KnowledgeRepository, ctx: ActivationContext
    ) -> tuple[bool, str]:
        """G2：双签齐备（专家 + 工程）。显式注入优先，否则从审核链推导。"""
        if ctx.dual_sign_present is not None:
            return (ctx.dual_sign_present, "" if ctx.dual_sign_present else GATE_G2_DUAL_SIGN)
        approved = repo.query(validation_status=APPROVED_STATUS)
        if not approved:
            return False, GATE_G2_DUAL_SIGN  # 无候选 => 无法证明双签
        for item in approved:
            if not KnowledgeActivationGate._has_dual_sign(repo, item.knowledge_id):
                return False, GATE_G2_DUAL_SIGN
        return True, ""

    @staticmethod
    def _g3_ci(ctx: ActivationContext) -> tuple[bool, str]:
        """G3：CI 全绿（注入，默认红）。"""
        if ctx.ci_green is True:
            return True, ""
        return False, GATE_G3_CI

    @staticmethod
    def _g4_audit_chain(
        repo: KnowledgeRepository, ctx: ActivationContext
    ) -> tuple[bool, str]:
        """G4：候选 item 审计链完整（create + verify，无 forbidden approved）。"""
        if not ctx.require_audit_chain:
            return True, ""
        # 防御性：整个事件日志不得含 forbidden 'approved'（KnowledgeEventLog 已硬拒）。
        for ev in repo.event_log.all_events():
            if ev.event_type == FORBIDDEN_EVENT_TYPE:
                return False, GATE_G4_AUDIT_CHAIN
        approved = repo.query(validation_status=APPROVED_STATUS)
        for item in approved:
            types = [e.event_type for e in repo.history(item.knowledge_id)]
            if "create" not in types or "verify" not in types:
                return False, GATE_G4_AUDIT_CHAIN
        return True, ""

    @staticmethod
    def _g5_rollback(ctx: ActivationContext) -> tuple[bool, str]:
        """G5：回滚就绪（注入，默认不就绪）。"""
        if ctx.rollback_ready is True:
            return True, ""
        return False, GATE_G5_ROLLBACK

    @staticmethod
    def _g6_authorization(ctx: ActivationContext) -> tuple[bool, str]:
        """G6：主理人单独书面授权到位（注入，默认缺失）。"""
        if ctx.authorization_present is True:
            return True, ""
        return False, GATE_G6_AUTHORIZATION

    # ------------------------------------------------------------------ #
    # 工具
    # ------------------------------------------------------------------ #
    @staticmethod
    def _has_dual_sign(repo: KnowledgeRepository, knowledge_id: str) -> bool:
        actors = [
            e.actor.lower()
            for e in repo.history(knowledge_id)
            if e.event_type == "verify"
        ]
        has_expert = any(any(m in a for m in _EXPERT_MARKERS) for a in actors)
        has_engineer = any(any(m in a for m in _ENGINEER_MARKERS) for a in actors)
        return has_expert and has_engineer

    @staticmethod
    def safety_invariants_ok() -> bool:
        """只读护栏断言：engineering_enabled 必须保持 False。"""
        return load_engineering_enabled() is False


__all__ = [
    "G_KNOWLEDGE_GOVERNANCE",
    "G_DUAL_SIGN",
    "G_CI",
    "G_AUDIT_CHAIN",
    "G_ROLLBACK",
    "G_AUTHORIZATION",
    "ALL_GATES",
    "GATE_G1_GOVERNANCE",
    "GATE_G2_DUAL_SIGN",
    "GATE_G3_CI",
    "GATE_G4_AUDIT_CHAIN",
    "GATE_G5_ROLLBACK",
    "GATE_G6_AUTHORIZATION",
    "APPROVED_STATUS",
    "FORBIDDEN_EVENT_TYPE",
    "ActivationContext",
    "ActivationDecision",
    "KnowledgeActivationGate",
]
