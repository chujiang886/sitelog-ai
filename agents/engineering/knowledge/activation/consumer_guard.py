"""Engineering AI Consumption Enforcement（Phase 3.4 Sprint 3.4.3）。

让 Engineering AI / RAG 消费链强制遵守 ``UnifiedActivationGate`` + ``ConsumptionPolicy``。

职责：
- 任务1 ``EngineeringKnowledgeGuard.consume_knowledge``：检查统一闸门决策 +
  消费策略，决定知识能否进入工程计算 / RAG 上下文。
- 任务2 RAG 消费边界：``Engineering_Approved`` 可作权威引用；``Verified`` 系列仅辅助
  （须标 pending_verification）；``Pending`` / ``Captured`` / ``Deprecated`` 禁止进入。
- 任务3 工程 Agent 接入：提供只读 Guard 接入点（``guard_engineering_computation_input``），
  工程计算入口在计算前调用；**不修改任何现有计算逻辑**。
- 任务4 审计记录：``KnowledgeConsumptionAuditLog`` 记录 ``knowledge_consumed`` /
  ``knowledge_blocked``；**明确拒绝 ``approved`` 事件**（红线）。

红线（全 Phase 3.4 适用）：
①不开 ``engineering_enabled`` ②不输出 ``engineering_approved`` ③不改 ``verified.json``
④不建 ``ReleaseApproval`` ⑤AI 不代专家授权。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

from agents.config_loader import load_engineering_enabled
from agents.engineering.knowledge.activation.consumption import (
    NOT_CITABLE,
    KnowledgeConsumptionPolicy,
)
from agents.engineering.knowledge.connector import KnowledgeItem
from agents.engineering.knowledge.repository import (
    FORBIDDEN_EVENT_TYPE,
    KnowledgeEvent,
)

if TYPE_CHECKING:  # 避免与 unified_activation_gate 的循环导入（仅用于类型标注）
    from agents.engineering.gate.unified_activation_gate import UnifiedActivationDecision

# 消费审计事件类型（独立于 repository EVENT_TYPES 白名单，不触碰 verified.json）。
CONSUMED_EVENT: str = "knowledge_consumed"
BLOCKED_EVENT: str = "knowledge_blocked"

# 消费审计严禁事件：approved 被红线禁止，绝不记录。
_CONSUMPTION_FORBIDDEN_EVENTS = frozenset({FORBIDDEN_EVENT_TYPE, "approved"})


# --------------------------------------------------------------------------- #
# 任务4：消费审计日志（append-only，独立存储）
# --------------------------------------------------------------------------- #
class KnowledgeConsumptionAuditLog:
    """消费审计日志：仅记录 knowledge_consumed / knowledge_blocked。

    与 repository 事件白名单解耦；明确拒绝 approved（红线）。不触碰 verified.json。
    """

    def __init__(self) -> None:
        self._events: list[KnowledgeEvent] = []

    def record(
        self,
        item: KnowledgeItem,
        *,
        allowed: bool,
        actor: str = "engineering_ai",
        detail: Optional[str] = None,
    ) -> KnowledgeEvent:
        event_type = CONSUMED_EVENT if allowed else BLOCKED_EVENT
        if event_type in _CONSUMPTION_FORBIDDEN_EVENTS:
            raise ValueError(
                f"消费审计事件类型 '{event_type}' 被红线禁止（AI 不代签/不代授权）"
            )
        ev = KnowledgeEvent(
            event_id=(
                f"CEVT-{abs(hash((item.knowledge_id, event_type, datetime.now(timezone.utc).isoformat()))) % 10**12:012d}"
            ),
            knowledge_id=item.knowledge_id,
            event_type=event_type,
            actor=actor,
            timestamp=datetime.now(timezone.utc).isoformat(),
            detail=detail,
            version=None,
        )
        self._events.append(ev)
        return ev

    def events_for(self, knowledge_id: str) -> list[KnowledgeEvent]:
        return [e for e in self._events if e.knowledge_id == knowledge_id]

    def all_events(self) -> list[KnowledgeEvent]:
        return list(self._events)

    def to_list(self) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self._events]


# --------------------------------------------------------------------------- #
# 任务1+2：消费判定结果 + 守卫
# --------------------------------------------------------------------------- #
@dataclass
class ConsumptionResult:
    """单次消费判定结果。"""

    permitted: bool
    policy: str
    as_authoritative: bool
    requires_pending_verification: bool
    reason: str = ""
    event: Optional[KnowledgeEvent] = None


class EngineeringKnowledgeGuard:
    """任务1+2+3：Engineering AI / RAG 消费强制守卫（read-only 判定）。

    使用方（Engineering Agent / RAG 检索层）在把知识纳入工程计算前调用
    ``consume_knowledge``；本类只判定与记录审计，绝不翻转 ``engineering_enabled`` /
    写 ``verified.json`` / 创建 ``ReleaseApproval`` / 输出 ``engineering_approved``。
    """

    def __init__(
        self,
        policy: Optional[KnowledgeConsumptionPolicy] = None,
        audit_log: Optional[KnowledgeConsumptionAuditLog] = None,
    ) -> None:
        # 延迟导入，避免与 unified_activation_gate 形成循环导入。
        from agents.engineering.gate.unified_activation_gate import (
            UnifiedConsumptionController,
        )

        self._controller = UnifiedConsumptionController(policy or KnowledgeConsumptionPolicy())
        self._audit = audit_log or KnowledgeConsumptionAuditLog()

    @property
    def audit_log(self) -> KnowledgeConsumptionAuditLog:
        return self._audit

    # ------------------------------------------------------------------ #
    # 主入口
    # ------------------------------------------------------------------ #
    def consume_knowledge(
        self,
        item: KnowledgeItem,
        unified: UnifiedActivationDecision,
        *,
        actor: str = "engineering_ai",
        detail: Optional[str] = None,
    ) -> ConsumptionResult:
        """判断知识能否进入工程计算 / RAG 上下文。

        - 红线不变量：``engineering_enabled`` 必须保持 ``False``（否则 fail-closed 拒绝）。
        - 统一闸门不允许 → 禁止任何知识。
        - 允许前提下，按消费策略分级：
          citable → 权威；auxiliary_only → 仅辅助（须 pending_verification）；
          not_citable → 禁止进入工程计算。
        """
        # 红线不变量（顶层）。
        if load_engineering_enabled() is not False:
            return self._deny(item, "engineering_enabled_must_be_false", actor, detail)

        # 统一闸门判定。
        if not unified.allowed:
            return self._deny(item, "unified_gate_blocked", actor, detail)

        # 消费策略分级。
        dec = self._controller.evaluate(item, unified)
        if not dec.permitted:
            return self._deny(item, dec.reason or "not_citable_forbidden", actor, detail)

        ev = self._audit.record(item, allowed=True, actor=actor, detail=detail)
        return ConsumptionResult(
            permitted=True,
            policy=dec.policy,
            as_authoritative=dec.as_authoritative,
            requires_pending_verification=dec.requires_pending_verification,
            reason="consumed",
            event=ev,
        )

    # ------------------------------------------------------------------ #
    # 任务3：工程计算入口只读接入点（不修改计算逻辑）
    # ------------------------------------------------------------------ #
    def guard_engineering_computation_input(
        self,
        item: KnowledgeItem,
        unified: UnifiedActivationDecision,
        *,
        actor: str = "engineering_agent",
        detail: Optional[str] = None,
    ) -> ConsumptionResult:
        """工程计算入口（WindPressure / Glass / Profile / Hardware / InstallationRisk 等）

        在计算前调用；返回 ``ConsumptionResult``。若 ``permitted=False`` 或
        ``as_authoritative=False``，则该知识**不得**作为权威计算依据——仅可作辅助上下文
        且须标 ``pending_verification``。本方法只读判定，不修改任何计算逻辑。
        """
        return self.consume_knowledge(item, unified, actor=actor, detail=detail)

    # ------------------------------------------------------------------ #
    # 内部
    # ------------------------------------------------------------------ #
    def _deny(
        self, item: KnowledgeItem, reason: str, actor: str, detail: Optional[str]
    ) -> ConsumptionResult:
        ev = self._audit.record(
            item, allowed=False, actor=actor, detail=detail or reason
        )
        return ConsumptionResult(
            permitted=False,
            policy=NOT_CITABLE,
            as_authoritative=False,
            requires_pending_verification=False,
            reason=reason,
            event=ev,
        )

    @staticmethod
    def safety_invariants_ok() -> bool:
        """只读护栏断言：engineering_enabled 必须保持 False。"""
        return load_engineering_enabled() is False


# 便捷构造（任务3 接入点复用）。
def make_guard() -> EngineeringKnowledgeGuard:
    return EngineeringKnowledgeGuard()


__all__ = [
    "CONSUMED_EVENT",
    "BLOCKED_EVENT",
    "KnowledgeConsumptionAuditLog",
    "ConsumptionResult",
    "EngineeringKnowledgeGuard",
    "make_guard",
]
