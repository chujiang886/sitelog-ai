"""Unified Activation Gate（Phase 3.4 Sprint 3.4.2）。

聚合三类域的激活判定为单一统一决策：

- 知识域（knowledge）：``KnowledgeActivationGate.can_activate_knowledge``
- 阈值域（threshold）：``can_enable_engineering``（enable_gate）
- 发布域（publishing）：发布/放行闸门，复用同一套 G1–G6 语义

统一语义（知识域与阈值域共享，发布域复用）：
- G1  governance  ：治理护栏完备（``engineering_enabled=False`` + 域专属治理条件）
- G2  dual_sign   ：双签齐全（专家 + 工程/管理）
- G3  CI          ：CI 全绿（注入，默认红）
- G4  audit       ：审核链完整（无 forbidden ``approved``，链式无断裂）
- G5  rollback    ：回滚就绪（注入，默认不就绪）
- G6  authorization：主理人单独书面授权（ReleaseApproval，注入，默认缺失）

设计要点：
- **Fail-closed 默认全阻断**：缺失任何外部条件 → 该域（及整体）判定拒绝。
- **绝不翻转 ``engineering_enabled``**、不输出 ``engineering_approved``、
  不创建 ``ReleaseApproval``、不修改 ``verified.json``；AI 只编排容器与判定。
- 消费接入（任务4）：``UnifiedConsumptionController`` 定义
  ActivationGate → ConsumptionPolicy 流程，禁止未 Approved 知识进入工程计算。

红线（全 Phase 3.4 适用）：
①不开 engineering_enabled ②不输出 engineering_approved ③不改 verified.json
④不建 ReleaseApproval ⑤AI 不代专家审核。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from agents.config_loader import load_engineering_enabled
from agents.engineering.gate.enable_gate import (
    GATE_G1_GOVERNANCE,
    GATE_G2_DUAL_SIGN,
    GATE_G3_CI,
    GATE_G4_AUDIT_CHAIN,
    GATE_G5_ROLLBACK,
    GATE_G6_AUTHORIZATION,
    can_enable_engineering,
)
from agents.engineering.knowledge.activation.consumption import (
    AUXILIARY_ONLY,
    CITABLE,
    NOT_CITABLE,
    KnowledgeConsumptionPolicy,
)
from agents.engineering.knowledge.activation.gate import (
    ALL_GATES,
    ActivationContext,
    APPROVED_STATUS,
    KnowledgeActivationGate,
)
from agents.engineering.knowledge.repository import (
    FORBIDDEN_EVENT_TYPE,
    KnowledgeRepository,
)

# 统一门禁标签（与 KnowledgeActivationGate 一致："G1".."G6"）。
G1, G2, G3, G4, G5, G6 = ALL_GATES

# 发布域 G1 治理原因码（复用 GATE_G1_GOVERNANCE 语义：engineering_enabled 必须为 False）。
_PUBLISH_G1_REASON = GATE_G1_GOVERNANCE


@dataclass
class DomainResult:
    """单个域（knowledge / threshold / publishing）的判定结果。"""

    domain: str
    allowed: bool
    gate_results: dict[str, bool] = field(default_factory=dict)
    blocking_reasons: list[str] = field(default_factory=list)
    detail: str = ""


@dataclass
class UnifiedActivationDecision:
    """统一激活判定结果（聚合三域）。"""

    allowed: bool
    blocking_reasons: list[str] = field(default_factory=list)
    domain_results: dict[str, DomainResult] = field(default_factory=dict)
    detail: str = ""


@dataclass
class ConsumptionDecision:
    """知识进入工程计算的消费判定（任务4）。"""

    permitted: bool
    policy: str
    as_authoritative: bool
    requires_pending_verification: bool
    reason: str = ""


class UnifiedActivationGate:
    """任务1+2+3：统一激活闸门（知识域 + 阈值域 + 发布域，fail-closed）。"""

    def __init__(self) -> None:
        self._knowledge_gate = KnowledgeActivationGate()

    # ------------------------------------------------------------------ #
    # 主入口
    # ------------------------------------------------------------------ #
    def evaluate(
        self,
        repository: Any,
        *,
        context: Optional[ActivationContext] = None,
        thresholds: Optional[Any] = None,
        review_log_path: Any = None,
    ) -> UnifiedActivationDecision:
        """聚合三域判定为统一决策。

        - ``repository``：知识仓库（知识域 + 发布域依赖；须为 KnowledgeRepository）。
        - ``context``：共享注入信号（ci_green / rollback_ready /
          authorization_present / dual_sign_present / require_audit_chain）。
        - ``thresholds``：阈值域待启用阈值（缺省由 can_enable_engineering 加载）。
        - ``review_log_path``：阈值域审核链日志路径（缺省默认）。

        红线：本方法只判定，绝不翻转 engineering_enabled / 写 verified.json /
        创建 ReleaseApproval / 输出 engineering_approved。
        """
        ctx = context or ActivationContext()

        knowledge = self._evaluate_knowledge(repository, ctx)
        threshold = self._evaluate_threshold(ctx, thresholds, review_log_path)
        publishing = self._evaluate_publishing(repository, ctx)

        domains = {
            "knowledge": knowledge,
            "threshold": threshold,
            "publishing": publishing,
        }

        # 顶层安全不变量：engineering_enabled 必须保持 False。
        safety_ok = load_engineering_enabled() is False
        allowed = safety_ok and all(d.allowed for d in domains.values())

        reasons: list[str] = []
        if not safety_ok:
            reasons.append(f"{G1}_engineering_enabled_must_be_false")
        for name, d in domains.items():
            for r in d.blocking_reasons:
                reasons.append(f"[{name}] {r}")

        detail = (
            "统一激活允许" if allowed
            else f"统一激活被阻止（fail-closed，{len(reasons)} 项原因）"
        )
        return UnifiedActivationDecision(
            allowed=allowed,
            blocking_reasons=reasons,
            domain_results=domains,
            detail=detail,
        )

    # ------------------------------------------------------------------ #
    # 知识域
    # ------------------------------------------------------------------ #
    def _evaluate_knowledge(
        self, repository: Any, ctx: ActivationContext
    ) -> DomainResult:
        dec = self._knowledge_gate.can_activate_knowledge(repository, context=ctx)
        return DomainResult(
            domain="knowledge",
            allowed=dec.allowed,
            gate_results=dict(dec.gate_results),
            blocking_reasons=list(dec.blocking_reasons),
            detail=dec.detail,
        )

    # ------------------------------------------------------------------ #
    # 阈值域（复用 can_enable_engineering，解析原因到统一 G1–G6）
    # ------------------------------------------------------------------ #
    def _evaluate_threshold(
        self, ctx: ActivationContext, thresholds: Optional[Any], review_log_path: Any
    ) -> DomainResult:
        try:
            allowed, reasons = can_enable_engineering(
                thresholds=thresholds,
                ci_green=ctx.ci_green is True,
                rollback_ready=ctx.rollback_ready is True,
                authorization_present=ctx.authorization_present is True,
                review_log_path=review_log_path,
                require_audit_chain=ctx.require_audit_chain,
            )
        except Exception:  # noqa: BLE001 - 任何异常均视为阈值域不可信
            allowed, reasons = False, [f"{GATE_G1_GOVERNANCE}:unexpected_error"]

        gate_results = self._threshold_gate_results(reasons)
        return DomainResult(
            domain="threshold",
            allowed=allowed,
            gate_results=gate_results,
            blocking_reasons=list(reasons),
            detail="阈值域判定",
        )

    @staticmethod
    def _threshold_gate_results(reasons: list[str]) -> dict[str, bool]:
        """将 can_enable_engineering 的原因码映射到统一 G1–G6 标签。"""
        gates: dict[str, bool] = {g: True for g in ALL_GATES}
        for raw in reasons:
            s = str(raw)
            if s.startswith("G1_"):
                gates[G1] = False
            elif GATE_G2_DUAL_SIGN in s or s.startswith("G2_"):
                gates[G2] = False
            elif GATE_G3_CI in s or s.startswith("G3_"):
                gates[G3] = False
            elif GATE_G4_AUDIT_CHAIN in s or s.startswith("G4_"):
                gates[G4] = False
            elif GATE_G5_ROLLBACK in s or s.startswith("G5_"):
                gates[G5] = False
            elif GATE_G6_AUTHORIZATION in s or s.startswith("G6_"):
                gates[G6] = False
        return gates

    # ------------------------------------------------------------------ #
    # 发布域（发布/放行闸门，复用统一 G1–G6 语义）
    # ------------------------------------------------------------------ #
    def _evaluate_publishing(
        self, repository: Any, ctx: ActivationContext
    ) -> DomainResult:
        results: dict[str, bool] = {}
        reasons: list[str] = []

        # G1 治理护栏：engineering_enabled 必须保持 False。
        if load_engineering_enabled() is False:
            results[G1] = True
        else:
            results[G1] = False
            reasons.append(_PUBLISH_G1_REASON)

        # G2 双签（发布放行须显式双签到位）。
        if ctx.dual_sign_present is True:
            results[G2] = True
        else:
            results[G2] = False
            reasons.append(GATE_G2_DUAL_SIGN)

        # G3 CI 全绿。
        if ctx.ci_green is True:
            results[G3] = True
        else:
            results[G3] = False
            reasons.append(GATE_G3_CI)

        # G4 审核链完整（复用知识仓库审计检查；不要求时直接通过）。
        if not ctx.require_audit_chain:
            results[G4] = True
        elif isinstance(repository, KnowledgeRepository) and self._audit_chain_ok(
            repository
        ):
            results[G4] = True
        else:
            results[G4] = False
            reasons.append(GATE_G4_AUDIT_CHAIN)

        # G5 回滚就绪。
        if ctx.rollback_ready is True:
            results[G5] = True
        else:
            results[G5] = False
            reasons.append(GATE_G5_ROLLBACK)

        # G6 主理人书面授权（ReleaseApproval 到位）。
        if ctx.authorization_present is True:
            results[G6] = True
        else:
            results[G6] = False
            reasons.append(GATE_G6_AUTHORIZATION)

        allowed = all(results.values())
        return DomainResult(
            domain="publishing",
            allowed=allowed,
            gate_results=results,
            blocking_reasons=reasons,
            detail="发布域判定",
        )

    @staticmethod
    def _audit_chain_ok(repo: KnowledgeRepository) -> bool:
        """审核链完整性：无 forbidden ``approved`` 事件 + approved item 含 create+verify。"""
        for ev in repo.event_log.all_events():
            if ev.event_type == FORBIDDEN_EVENT_TYPE:
                return False
        approved = repo.query(validation_status=APPROVED_STATUS)
        for item in approved:
            types = [e.event_type for e in repo.history(item.knowledge_id)]
            if "create" not in types or "verify" not in types:
                return False
        return True

    @staticmethod
    def safety_invariants_ok() -> bool:
        """只读护栏断言：engineering_enabled 必须保持 False。"""
        return load_engineering_enabled() is False


class UnifiedConsumptionController:
    """任务4：ActivationGate → ConsumptionPolicy 消费接入控制器。

    规则：
    - 统一闸门不允许 → 任何知识都不得进入工程计算。
    - 允许前提下，仅 ``citable``（Engineering_Approved）可作为权威工程依据；
      ``auxiliary_only`` 仅作上下文（须标 pending_verification）；
      ``not_citable`` 一律禁止进入工程计算。
    """

    def __init__(self, policy: Optional[KnowledgeConsumptionPolicy] = None) -> None:
        self.policy = policy or KnowledgeConsumptionPolicy()

    def evaluate(
        self, item: Any, unified: UnifiedActivationDecision
    ) -> ConsumptionDecision:
        if not unified.allowed:
            return ConsumptionDecision(
                permitted=False,
                policy=NOT_CITABLE,
                as_authoritative=False,
                requires_pending_verification=False,
                reason="unified_gate_blocked",
            )
        cls = self.policy.classify(item)
        if cls == CITABLE:
            return ConsumptionDecision(
                permitted=True,
                policy=cls,
                as_authoritative=True,
                requires_pending_verification=False,
            )
        if cls == AUXILIARY_ONLY:
            return ConsumptionDecision(
                permitted=True,
                policy=cls,
                as_authoritative=False,
                requires_pending_verification=True,
            )
        return ConsumptionDecision(
            permitted=False,
            policy=cls,
            as_authoritative=False,
            requires_pending_verification=False,
            reason="not_citable_forbidden",
        )


__all__ = [
    "G1",
    "G2",
    "G3",
    "G4",
    "G5",
    "G6",
    "DomainResult",
    "UnifiedActivationDecision",
    "ConsumptionDecision",
    "UnifiedActivationGate",
    "UnifiedConsumptionController",
]
