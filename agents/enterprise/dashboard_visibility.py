"""Enterprise Intelligence Dashboard Layer —— 驾驶舱可见性策略（任务4，Phase 3.8.5）。

新增：``AnalyticsVisibilityPolicy``，按角色（``RoleKind``）控制不同数据源在驾驶舱中的可见性。

设计要点（fail-closed，默认拒绝）：
- ``_ROLE_VISIBLE_SOURCES``：每个角色仅显式允许若干事实数据源；未列出的源默认不可见。
- ``Dashboard.visibility``（``private`` / ``org`` / ``role:<role_kind>``）与角色策略**叠加**生效：
  先校验驾驶舱整体是否对该角色/查看者可见，再按角色过滤数据源。
- 本策略**仅**决定「展示哪些事实组件」，不授予任何权限、不做任何决策（红线③/⑥）。
- 真实权限（如 view_project / view_audit）仍由 identity 层 ``IdentityService.check`` 校验，
  本策略是「展示层」的细化，而非权限替代。
- 不持有批准/报价/审批/记录为人工方法（红线②/③/④/⑥）。
"""

from __future__ import annotations

from dataclasses import replace

from agents.enterprise.dashboard import Dashboard, DashboardWidget
from agents.enterprise.identity import RoleKind


# 角色 → 允许可见的事实数据源（默认拒绝：未列出的源对该角色不可见）。
# 数据源取值对应各 *Dashboard 组装时打的 source 标记。
# Phase 3.8.8：新增 knowledge_view（查看知识版本/候选/审核/冲突等治理事实，全员可见）
# 与 knowledge_manage（管理知识治理动作，仅 ADMIN / EXPERT / REVIEWER 可见）。
_ROLE_VISIBLE_SOURCES: dict[RoleKind, set[str]] = {
    RoleKind.ADMIN: {
        "project_analytics",
        "workflow_analytics",
        "ai_usage_analytics",
        "operation_risk",
        "knowledge_view",
        "knowledge_manage",
    },
    RoleKind.DESIGNER: {
        "project_analytics",
        "workflow_analytics",
        "ai_usage_analytics",
        "knowledge_view",
    },
    RoleKind.ENGINEER: {
        "project_analytics",
        "workflow_analytics",
        "ai_usage_analytics",
        "knowledge_view",
    },
    RoleKind.EXPERT: {
        "project_analytics",
        "ai_usage_analytics",
        "knowledge_view",
        "knowledge_manage",
    },
    RoleKind.REVIEWER: {
        "project_analytics",
        "workflow_analytics",
        "ai_usage_analytics",
        "operation_risk",
        "knowledge_view",
        "knowledge_manage",
    },
}


class AnalyticsVisibilityPolicy:
    """驾驶舱可见性策略（任务4）。

    按角色决定哪些事实组件可见；``Dashboard.visibility`` 与角色策略叠加生效。
    **默认拒绝**：角色未显式允许的数据源不可见。
    """

    def __init__(self, org_id: str) -> None:
        self._org_id = org_id

    def is_source_permitted(self, role: RoleKind, source: str) -> bool:
        """某角色是否可见某数据源（空 source 视为通用组件，对全部角色可见）。"""
        if not source:
            return True
        return source in _ROLE_VISIBLE_SOURCES.get(role, set())

    def can_view_dashboard(
        self,
        role: RoleKind,
        dashboard: Dashboard,
        viewer_id: str,
    ) -> bool:
        """校验查看者是否可见该驾驶舱整体（先过 visibility 门槛）。"""
        vis = (dashboard.visibility or "private").strip()
        if vis == "private":
            return viewer_id == dashboard.owner_id
        if vis.startswith("role:"):
            want = vis.split(":", 1)[1].strip()
            return role.value == want
        if vis == "org":
            return True
        # 未知可见性声明 → 默认拒绝（fail-closed）。
        return False

    def visible_widgets(
        self,
        role: RoleKind,
        dashboard: Dashboard,
        viewer_id: str,
    ) -> list[DashboardWidget]:
        """返回该角色在该驾驶舱下可见的事实组件（叠加 visibility + 角色数据源策略）。"""
        if not self.can_view_dashboard(role, dashboard, viewer_id):
            return []
        return [
            w for w in dashboard.widgets
            if self.is_source_permitted(role, w.source)
        ]

    def filter_dashboard(
        self,
        role: RoleKind,
        dashboard: Dashboard,
        viewer_id: str,
    ) -> Dashboard:
        """返回仅含「可见事实组件」的驾驶舱副本（不修改原对象）。"""
        widgets = self.visible_widgets(role, dashboard, viewer_id)
        return replace(dashboard, widgets=list(widgets))


__all__ = ["AnalyticsVisibilityPolicy", "_ROLE_VISIBLE_SOURCES"]
