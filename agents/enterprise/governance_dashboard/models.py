"""Phase 3.8.26 治理驾驶舱层 —— 视图模型（只读 DTO + 人工操作者载体）。

这些 DTO 只用于「驾驶舱展示」与「人工确认入参」，不持有任何治理状态；治理状态仍由
3.8.25 ``GovernanceWorkflowOrchestrator`` 单一真相源持有。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional


@dataclass
class DashboardUser:
    """驾驶舱人工操作者载体（Task3/4：强制真实 USER）。

    由 HTTP 层从鉴权头构造，或由测试显式构造。``actor_kind`` 必须是
    ``AuditActorKind.USER``（或字面 ``"user"``），否则任何写操作都会被
    ``require_human_actor`` 拦截（红线⑥）。
    """

    actor_id: str
    actor_kind: Any = "user"  # AuditActorKind.USER 或 "user"
    display_name: str = ""

    def is_user(self) -> bool:
        # 宽松判定：枚举或字面 "user" 均视为真实人工。
        return str(self.actor_kind).lower() == "user"


@dataclass
class ExecutionStatusView:
    """单条工作流的执行状态视图（Task1：执行状态）。"""

    workflow_id: str
    status: str
    confirmed_by: str = ""
    confirmed_at: str = ""
    completed_by: str = ""
    completed_at: str = ""
    archived: bool = False
    reviews: List[Any] = field(default_factory=list)
    execution_records: List[Any] = field(default_factory=list)


@dataclass
class RiskAlert:
    """只读风险提示（Task1：风险提示）。

    纯信息派生，由驾驶舱基于工作流状态计算，**不构成 AI 治理决定**（红线③）。
    """

    workflow_id: str
    severity: str  # info | warning | action
    title: str
    message: str
    status: str = ""


@dataclass
class DashboardSummary:
    """驾驶舱总览（Task1：workflow 列表 + 待审核 + 风险聚合）。"""

    total: int = 0
    pending_review: int = 0
    in_progress: int = 0
    waiting_result: int = 0
    completed: int = 0
    risk_count: int = 0


__all__ = [
    "DashboardUser",
    "ExecutionStatusView",
    "RiskAlert",
    "DashboardSummary",
]
