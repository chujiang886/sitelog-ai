"""Engineering Runtime Integration（Phase 3.4 Sprint 3.4.4）。

将 ``EngineeringKnowledgeGuard`` 接入真实工程 AI 入口（WindPressure / Glass /
Profile / Hardware / InstallationRisk）与 RAG 检索链路，使工程计算 / RAG 上下文
在纳入任何知识前强制经过 ``UnifiedActivationGate`` + ``ConsumptionPolicy`` 判定。

设计：
- 任务1 入口识别：五工程接口标识（与 ``EngineeringAgent.ANALYSIS_INTERFACES`` 对齐）。
- 任务2 接入：``EngineeringRuntimeGuard.guard_interface`` 在每个接口计算前对候选
  知识逐项调用 ``guard_engineering_computation_input``，分区为 authoritative /
  auxiliary / blocked；仅 authoritative 可作权威依据，auxiliary 仅辅助须
  pending_verification，blocked 一律不得进入。只读判定，不修改任何计算逻辑。
- 任务3 RAG：与 ``knowledge/rag`` 包协作，Retriever → Consumption Guard →
  ContextBuilder → Engineering Agent（见 ``agents/engineering/knowledge/rag``）。
- 红线：不开启 ``engineering_enabled`` / 不输出 ``engineering_approved`` /
  不建 ``ReleaseApproval`` / 不修改 ``verified.json`` / AI 不代专家授权；审计仅记
  knowledge_consumed / knowledge_blocked，显式拒绝 approved。

红线（全 Phase 3.4 适用）：
①不开 engineering_enabled ②不输出 engineering_approved ③不改 verified.json
④不建 ReleaseApproval ⑤AI 不代专家审核。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

from agents.engineering.gate.unified_activation_gate import (
    UnifiedActivationDecision,
    UnifiedActivationGate,
)
from agents.engineering.knowledge.activation.consumer_guard import (
    ConsumptionResult,
    EngineeringKnowledgeGuard,
)
from agents.engineering.knowledge.connector import KnowledgeItem


# 五工程接口（与 EngineeringAgent.ANALYSIS_INTERFACES 对齐；此处独立声明以避免
# 自 agent.py 反向导入形成循环依赖）。runtime_intégration 不 import agent.py。
ENGINEERING_INTERFACES: tuple[str, ...] = (
    "wind_pressure",
    "glass_safety",
    "profile",
    "hardware",
    "installation_risk",
)


# --------------------------------------------------------------------------- #
# 单接口守卫结果（分区）                                                        #
# --------------------------------------------------------------------------- #
@dataclass
class InterfaceGuardResult:
    """单个工程接口的知识消费分区结果。"""

    interface: str
    decision_allowed: bool
    authoritative: list[ConsumptionResult] = field(default_factory=list)
    auxiliary: list[ConsumptionResult] = field(default_factory=list)
    blocked: list[ConsumptionResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        def _ser(r: ConsumptionResult) -> dict[str, Any]:
            ev = r.event.to_dict() if r.event is not None else None
            return {
                "permitted": r.permitted,
                "policy": r.policy,
                "as_authoritative": r.as_authoritative,
                "requires_pending_verification": r.requires_pending_verification,
                "reason": r.reason,
                "event": ev,
            }

        def _kid(r: ConsumptionResult) -> str:
            return r.event.knowledge_id if r.event is not None else ""

        return {
            "interface": self.interface,
            "decision_allowed": self.decision_allowed,
            "authoritative": [_ser(r) for r in self.authoritative],
            "auxiliary": [_ser(r) for r in self.auxiliary],
            "blocked": [_ser(r) for r in self.blocked],
            "authoritative_ids": [_kid(r) for r in self.authoritative],
            "auxiliary_ids": [_kid(r) for r in self.auxiliary],
            "blocked_ids": [_kid(r) for r in self.blocked],
        }

    def has_authoritative(self) -> bool:
        """该接口是否拥有可作权威依据的知识（存在任意 authoritative）。"""

        return len(self.authoritative) > 0

    def is_fully_blocked(self) -> bool:
        """该接口是否全部候选知识都被阻断。"""

        return len(self.authoritative) == 0 and len(self.auxiliary) == 0


# --------------------------------------------------------------------------- #
# 运行时守卫（工程 Agent / RAG 统一接入点）                                       #
# --------------------------------------------------------------------------- #
class EngineeringRuntimeGuard:
    """任务1+2：将消费守卫接入五工程接口与 RAG 流程（read-only 判定）。

    使用方（Engineering Agent / RAG Pipeline）在把知识纳入工程计算 / 上下文前调用
    ``guard_interface`` / ``guard_item``；本类只判定与记录审计，绝不翻转
    ``engineering_enabled`` / 写 ``verified.json`` / 创建 ``ReleaseApproval`` /
    输出 ``engineering_approved``。
    """

    def __init__(
        self,
        gate: Optional[UnifiedActivationGate] = None,
        guard: Optional[EngineeringKnowledgeGuard] = None,
        audit_log: Any = None,
    ) -> None:
        self._gate = gate or UnifiedActivationGate()
        self._guard = guard or EngineeringKnowledgeGuard(audit_log=audit_log)

    @property
    def guard(self) -> EngineeringKnowledgeGuard:
        return self._guard

    @property
    def audit_log(self) -> Any:
        return self._guard.audit_log

    # ------------------------------------------------------------------ #
    # 统一闸门决策解析（系统级，fail-closed）                              #
    # ------------------------------------------------------------------ #
    def resolve_decision(
        self,
        repository: Any = None,
        *,
        context: Any = None,
    ) -> UnifiedActivationDecision:
        """解析系统级统一激活决策。

        - 提供 repository → 经 ``UnifiedActivationGate.evaluate`` 产出；
        - 未提供 repository → 直接 fail-closed 拒绝（不调用 gate，避免 None 崩溃）。
        """
        if repository is None:
            return UnifiedActivationDecision(
                allowed=False,
                blocking_reasons=["no_repository:fail_closed"],
                domain_results={},
                detail="未提供知识仓库，fail-closed 拒绝",
            )
        return self._gate.evaluate(repository, context=context)

    # ------------------------------------------------------------------ #
    # 单条知识（RAG 流程用）                                              #
    # ------------------------------------------------------------------ #
    def guard_item(
        self, item: KnowledgeItem, decision: UnifiedActivationDecision
    ) -> ConsumptionResult:
        """RAG 检索流程用：对单条候选知识执行消费守卫判定。"""

        return self._guard.guard_engineering_computation_input(item, decision)

    # ------------------------------------------------------------------ #
    # 单接口分区（Engineering Agent 计算前用）                            #
    # ------------------------------------------------------------------ #
    def guard_interface(
        self,
        interface: str,
        items: Sequence[KnowledgeItem],
        decision: UnifiedActivationDecision,
    ) -> InterfaceGuardResult:
        """工程接口计算前接入点：对候选知识逐项过 guard 并分区。

        - interface 必须是 ``ENGINEERING_INTERFACES`` 之一（识别入口）；
        - 未允许（permitted=False）→ blocked；
        - 允许且权威（as_authoritative）→ authoritative（可作权威依据）；
        - 允许但仅辅助（requires_pending_verification）→ auxiliary（须标 pending）。
        """
        if interface not in ENGINEERING_INTERFACES:
            raise ValueError(
                f"未知工程接口：{interface!r}（须为 ENGINEERING_INTERFACES 之一）"
            )
        result = InterfaceGuardResult(
            interface=interface, decision_allowed=bool(decision.allowed)
        )
        for item in items:
            res = self._guard.guard_engineering_computation_input(item, decision)
            if not res.permitted:
                result.blocked.append(res)
            elif res.as_authoritative:
                result.authoritative.append(res)
            else:
                result.auxiliary.append(res)
        return result

    def guard_all_interfaces(
        self,
        interfaces_items: Mapping[str, Sequence[KnowledgeItem]],
        decision: UnifiedActivationDecision,
    ) -> dict[str, InterfaceGuardResult]:
        """批量分区多个工程接口。"""

        return {
            name: self.guard_interface(name, items, decision)
            for name, items in interfaces_items.items()
        }

    @staticmethod
    def safety_invariants_ok() -> bool:
        """只读护栏断言：engineering_enabled 必须保持 False。"""

        return EngineeringKnowledgeGuard.safety_invariants_ok()


__all__ = [
    "ENGINEERING_INTERFACES",
    "InterfaceGuardResult",
    "EngineeringRuntimeGuard",
]
