"""Knowledge Consumption Policy（Phase 3.4 Sprint 3.4.1, Task 2）。

定义 Engineering AI 对知识的消费分类：
- citable（可引用）      : Engineering_Approved —— 可作为权威工程依据。
- auxiliary_only（仅辅助）: Source_Verified / Expert_Verified / Engineering_Verified
                           —— 仅作上下文/提示，引用须标 pending_verification。
- not_citable（不可引用） : Captured / Pending_Verification / Deprecated
                           —— 一律不进入工程结论。

不变量：任何非 Engineering_Approved 的知识被引用时**必须**标 pending_verification。
本策略仅做分类判定，不写盘、不产生 approved。
"""

from __future__ import annotations

from typing import Any

from agents.engineering.knowledge.connector import KnowledgeItem

CITABLE: str = "citable"
AUXILIARY_ONLY: str = "auxiliary_only"
NOT_CITABLE: str = "not_citable"

APPROVED_STATUS: str = "Engineering_Approved"

# validation_status -> 消费分类（声明性映射，与设计文档 phase3.4.0 §5 对齐）。
# 注意：Pending_Verification 尚未完成任何验证，归为 not_citable（而非 auxiliary_only）；
# 其余非 Approved 态 requires_pending_verification 均返回 True。
_STATE_POLICY: dict[str, str] = {
    "Engineering_Approved": CITABLE,
    "Engineering_Verified": AUXILIARY_ONLY,
    "Expert_Verified": AUXILIARY_ONLY,
    "Source_Verified": AUXILIARY_ONLY,
    "Pending_Verification": NOT_CITABLE,
    "Captured": NOT_CITABLE,
    "Deprecated": NOT_CITABLE,
}


class KnowledgeConsumptionPolicy:
    """Task 2：知识消费策略分类器（只读判定）。"""

    def classify(self, item: KnowledgeItem) -> str:
        """返回 item 的消费分类：citable / auxiliary_only / not_citable。"""
        return _STATE_POLICY.get(item.validation_status, NOT_CITABLE)

    def is_citable(self, item: KnowledgeItem) -> bool:
        """是否可作为权威工程依据引用（仅 Engineering_Approved）。"""
        return self.classify(item) == CITABLE

    def is_auxiliary_only(self, item: KnowledgeItem) -> bool:
        """是否仅可作辅助上下文（须标 pending_verification）。"""
        return self.classify(item) == AUXILIARY_ONLY

    def is_not_citable(self, item: KnowledgeItem) -> bool:
        """是否不可引用（须规避）。"""
        return self.classify(item) == NOT_CITABLE

    def requires_pending_verification(self, item: KnowledgeItem) -> bool:
        """除 Engineering_Approved 外，任何知识被引用都必须标 pending_verification。"""
        return self.classify(item) != CITABLE

    def decision_for(self, item: KnowledgeItem) -> dict[str, Any]:
        """聚合判定，便于消费层一次性读取。"""
        cls = self.classify(item)
        return {
            "knowledge_id": item.knowledge_id,
            "validation_status": item.validation_status,
            "policy": cls,
            "citable": cls == CITABLE,
            "requires_pending_verification": cls != CITABLE,
        }


__all__ = [
    "CITABLE",
    "AUXILIARY_ONLY",
    "NOT_CITABLE",
    "APPROVED_STATUS",
    "KnowledgeConsumptionPolicy",
]
