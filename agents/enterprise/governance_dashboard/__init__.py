"""Phase 3.8.26 企业智能体治理驾驶舱层（Governance Dashboard）。

链路补完：在 3.8.25 编排层之上提供**只读查询 + 单一人工确认入口**的驾驶舱 API，
供真实治理责任人查看 / 审核 / 确认 / 执行追踪 / 归档，所有动作可审计，AI 无法越权。

包内分工：
- ``forbidden``：结构级禁名（3.8.25 编排层 166 项 ∪ 本层增量）；
- ``models``：视图 DTO（DashboardUser / ExecutionStatusView / RiskAlert / DashboardSummary）；
- ``service``：``GovernanceDashboardService``（驾驶舱服务，唯一写入口 confirm_review）。
"""

from __future__ import annotations

from agents.enterprise.governance_dashboard.forbidden import (
    _DASHBOARD_EXTRA_FORBIDDEN,
    _DASHBOARD_FORBIDDEN,
    DASHBOARD_FORBIDDEN_COUNT,
)
from agents.enterprise.governance_dashboard.models import (
    DashboardSummary,
    DashboardUser,
    ExecutionStatusView,
    RiskAlert,
)
from agents.enterprise.governance_dashboard.service import GovernanceDashboardService

__all__ = [
    "GovernanceDashboardService",
    "DashboardUser",
    "ExecutionStatusView",
    "RiskAlert",
    "DashboardSummary",
    "_DASHBOARD_FORBIDDEN",
    "_DASHBOARD_EXTRA_FORBIDDEN",
    "DASHBOARD_FORBIDDEN_COUNT",
]
