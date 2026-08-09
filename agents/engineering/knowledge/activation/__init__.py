"""Knowledge Activation Layer（Phase 3.4 Sprint 3.4.1–3.4.3）。

只读/声明性激活判定层，全部 fail-closed，不翻转 engineering_enabled。
- gate.py           : KnowledgeActivationGate（G1–G6 激活判定）
- consumption.py    : KnowledgeConsumptionPolicy（citable / auxiliary_only / not_citable）
- read_boundary.py  : KnowledgeReadBoundary（AI 读取边界）
- rollback.py       : KnowledgeRollbackPolicy（Deprecated → successor → replacement）
- consumer_guard.py : EngineeringKnowledgeGuard（消费强制守卫 + 消费审计日志）
"""

from agents.engineering.knowledge.activation.consumption import (
    AUXILIARY_ONLY,
    CITABLE,
    NOT_CITABLE,
    KnowledgeConsumptionPolicy,
)
from agents.engineering.knowledge.activation.gate import (
    ALL_GATES,
    ActivationContext,
    ActivationDecision,
    KnowledgeActivationGate,
)
from agents.engineering.knowledge.activation.read_boundary import (
    ALLOWED_KINDS,
    KnowledgeReadBoundary,
)
from agents.engineering.knowledge.activation.rollback import (
    DEPRECATED_STATUS,
    KnowledgeRollbackPolicy,
)
from agents.engineering.knowledge.activation.consumer_guard import (
    BLOCKED_EVENT,
    CONSUMED_EVENT,
    ConsumptionResult,
    EngineeringKnowledgeGuard,
    KnowledgeConsumptionAuditLog,
    make_guard,
)

__all__ = [
    "ALL_GATES",
    "ActivationContext",
    "ActivationDecision",
    "KnowledgeActivationGate",
    "KnowledgeConsumptionPolicy",
    "CITABLE",
    "AUXILIARY_ONLY",
    "NOT_CITABLE",
    "KnowledgeReadBoundary",
    "ALLOWED_KINDS",
    "KnowledgeRollbackPolicy",
    "DEPRECATED_STATUS",
    "EngineeringKnowledgeGuard",
    "KnowledgeConsumptionAuditLog",
    "ConsumptionResult",
    "CONSUMED_EVENT",
    "BLOCKED_EVENT",
    "make_guard",
]
