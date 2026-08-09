"""Enterprise Intelligence Dashboard Layer —— Dashboard 模型与驾驶舱服务（任务1/2，Phase 3.8.5）。

新增：
- ``WidgetType`` / ``DashboardWidget``：指标组件，支持 ``metric`` / ``chart`` / ``table`` /
  ``risk``；**只承载事实型数据**（不含任何评价/决策/建议结论）。
- ``Dashboard``：驾驶舱容器，字段 ``dashboard_id`` / ``org_id`` / ``owner_id`` / ``widgets`` /
  ``visibility`` / ``created_at``。
- ``DashboardService``：驾驶舱的登记/读取/组装/渲染；跨域访问抛 ``EnterpriseIsolationError``；
  写路径断言 ``safety_invariants_ok()``（红线①/⑤）；不持有批准/报价/审批/记录为人工方法
  （红线②/③/④/⑥）；可选联动 ``AuditService`` 如实标注查看/查询/导出方 actor。

红线约束（fail-closed，复用 3.8.0~3.8.4 基座 + 3.8.4 语义升级）：
- 所有驾驶舱按 ``org_id`` 作用域过滤；跨域访问抛隔离错误。
- **只展示事实**：不自动经营决策、不评价工程质量、不代管理做判断（红线③/⑥）。
- ``DashboardWidget.facts`` 在结构上禁止承载决策性/建议性字段
  （decision / recommendation / approval / quote / pricing 命中即抛红线违例）。
- ``visibility`` 仅控制「哪些角色/范围可见」，不承载权限授予语义；真实权限仍由 identity 层校验。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agents.enterprise.audit import AuditService
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)

# widget.facts 中禁止出现的结构性字段（红线③/⑥：驾驶舱只展示事实，不得承载决策/建议）。
_FORBIDDEN_WIDGET_FACT_KEYS = (
    "decision",
    "recommendation",
    "approval",
    "approved",
    "quote",
    "pricing",
    "engineering_approved",
)


class WidgetType(str, Enum):
    """指标组件类型（中性、事实型）。"""

    METRIC = "metric"  # 单一事实指标
    CHART = "chart"    # 事实型图表（如趋势/分布）
    TABLE = "table"    # 事实型表格
    RISK = "risk"      # 风险事实列表（仅列出风险事实，不做判定/处置建议）


@dataclass
class DashboardWidget:
    """指标组件（任务2）。

    只展示事实：``facts`` 为中性键值/列表，不含评价/决策/建议结论。
    ``__post_init__`` 结构性拦截 forbidden 事实键，确保驾驶舱组件不承载决策语义（红线③/⑥）。
    """

    widget_id: str
    widget_type: "WidgetType | str"
    title: str
    facts: dict = field(default_factory=dict)   # 仅事实型数据，不含评价/决策
    source: str = ""          # 数据来源（project_analytics / workflow_analytics / ai_usage / operation_risk ...）
    note: str = ""            # 中性说明（不得含决策/建议语义）

    def __post_init__(self) -> None:
        if not isinstance(self.facts, dict):
            raise EnterpriseRedLineViolationError(
                "DashboardWidget.facts 必须为 dict（仅事实型键值）"
            )
        for key in self.facts:
            if key in _FORBIDDEN_WIDGET_FACT_KEYS:
                raise EnterpriseRedLineViolationError(
                    f"DashboardWidget 禁止承载决策性/建议性事实键 {key!r}："
                    f"驾驶舱只展示事实（红线③/⑥），不得包含 decision/recommendation/"
                    f"approval/quote/pricing 等字段"
                )

    def widget_type_value(self) -> str:
        return self.widget_type.value if isinstance(self.widget_type, WidgetType) else str(self.widget_type)


@dataclass
class Dashboard:
    """驾驶舱（任务1）。

    字段固定为：dashboard_id / org_id / owner_id / widgets / visibility / created_at。
    ``widgets`` 仅收纳事实型 ``DashboardWidget``；``visibility`` 描述可见范围
    （``private`` / ``org`` / ``role:<role_kind>``），不授予任何权限。
    """

    dashboard_id: str
    org_id: str
    owner_id: str
    widgets: list = field(default_factory=list)   # list[DashboardWidget]
    visibility: str = "private"   # private / org / role:<role_kind>
    created_at: str = ""


class DashboardService(_RedLineForbiddenMixin):
    """驾驶舱服务（任务1/2）。

    仅登记/读取/渲染事实型驾驶舱；跨域访问抛 ``EnterpriseIsolationError``；
    写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
    本服务**不**持有任何 approve / engineering_approved / quote / pricing / sign /
    authorize / record_human_approval / auto_business_decision / make_management_decision
    方法（红线②/③/④/⑥）。
    """

    _FORBIDDEN = (
        "approve",
        "engineering_approved",
        "quote",
        "pricing",
        "sign",
        "authorize",
        "record_human_approval",
        # 3.8.4 语义升级：禁止自动经营决策 / AI 代管理责任
        "auto_business_decision",
        "make_management_decision",
        "decide_operation",
        "evaluate_quality",
    )

    def __init__(self, org_id: str, audit: "AuditService | None" = None) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "DashboardService（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._dashboards: dict[str, Dashboard] = {}

    def create_dashboard(
        self,
        *,
        dashboard_id: str,
        owner_id: str,
        visibility: str = "private",
        created_at: str = "",
    ) -> Dashboard:
        """登记一个事实型驾驶舱（只登记元数据，不生成任何决策）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下登记驾驶舱（红线①/⑤）"
            )
        d = Dashboard(
            dashboard_id=dashboard_id,
            org_id=self._org_id,
            owner_id=owner_id,
            widgets=[],
            visibility=visibility,
            created_at=created_at,
        )
        self._dashboards[dashboard_id] = d
        if self._audit is not None:
            self._audit.record_ai_action(
                record_id=f"dash-{dashboard_id}",
                actor_id=owner_id or "ai",
                action="create_dashboard",
                target=dashboard_id,
                detail=f"visibility={visibility}",
                ts=created_at,
            )
        return d

    def add_widget(
        self,
        *,
        dashboard_id: str,
        widget: DashboardWidget,
        actor_id: str = "ai",
        ts: str = "",
    ) -> Dashboard:
        """向驾驶舱追加一个事实型组件（widget.facts 已结构校验）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下编辑驾驶舱（红线①/⑤）"
            )
        d = self._get_scoped(dashboard_id)
        d.widgets.append(widget)
        if self._audit is not None:
            self._audit.record_ai_action(
                record_id=f"dash-{dashboard_id}-w-{widget.widget_id}",
                actor_id=actor_id,
                action="add_dashboard_widget",
                target=dashboard_id,
                detail=f"widget={widget.widget_id};type={widget.widget_type_value()};source={widget.source}",
                ts=ts,
            )
        return d

    def get_dashboard(self, *, dashboard_id: str) -> Dashboard:
        """按组织作用域读取驾驶舱（跨域访问抛隔离错误）。"""
        return self._get_scoped(dashboard_id)

    def list_dashboards(self) -> list[Dashboard]:
        """列出当前组织下驾驶舱。"""
        return [d for d in self._dashboards.values() if d.org_id == self._org_id]

    def remove_widget(self, *, dashboard_id: str, widget_id: str) -> Dashboard:
        """从驾驶舱移除一个组件（写路径断言红线）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下编辑驾驶舱（红线①/⑤）"
            )
        d = self._get_scoped(dashboard_id)
        d.widgets = [w for w in d.widgets if w.widget_id != widget_id]
        return d

    # ---- 驾驶舱动作审计（任务5）：view / query / export，如实标注 actor，绝不伪造人工审批 ----

    def render_dashboard(
        self,
        *,
        dashboard_id: str,
        viewer_id: str,
        actor_kind: "str | None" = None,
        ts: str = "",
    ) -> Dashboard:
        """渲染（查看）驾驶舱；如实记录 dashboard_view（actor 默认 USER）。"""
        d = self._get_scoped(dashboard_id)
        if self._audit is not None:
            self._audit.record_dashboard_view(
                record_id=f"view-{dashboard_id}",
                actor_id=viewer_id,
                target=dashboard_id,
                detail=f"widgets={len(d.widgets)};visibility={d.visibility}",
                ts=ts,
                actor_kind=actor_kind,
            )
        return d

    def run_query(
        self,
        *,
        dashboard_id: str,
        query: str,
        viewer_id: str,
        actor_kind: "str | None" = None,
        ts: str = "",
    ) -> list[DashboardWidget]:
        """在驾驶舱内执行一次事实查询；如实记录 dashboard_query（actor 默认 USER）。"""
        d = self._get_scoped(dashboard_id)
        if self._audit is not None:
            self._audit.record_dashboard_query(
                record_id=f"query-{dashboard_id}",
                actor_id=viewer_id,
                target=dashboard_id,
                detail=f"query={query};matches={len(d.widgets)}",
                ts=ts,
                actor_kind=actor_kind,
            )
        return list(d.widgets)

    def export_dashboard(
        self,
        *,
        dashboard_id: str,
        fmt: str,
        viewer_id: str,
        actor_kind: "str | None" = None,
        ts: str = "",
    ) -> Dashboard:
        """导出驾驶舱；如实记录 dashboard_export（actor 默认 USER）。"""
        d = self._get_scoped(dashboard_id)
        if self._audit is not None:
            self._audit.record_dashboard_export(
                record_id=f"export-{dashboard_id}",
                actor_id=viewer_id,
                target=dashboard_id,
                detail=f"format={fmt};widgets={len(d.widgets)}",
                ts=ts,
                actor_kind=actor_kind,
            )
        return d

    def _get_scoped(self, dashboard_id: str) -> Dashboard:
        from agents.enterprise.organization import EnterpriseIsolationError

        d = self._dashboards.get(dashboard_id)
        if d is None:
            raise EnterpriseIsolationError(f"驾驶舱 {dashboard_id!r} 不存在")
        if d.org_id != self._org_id:
            raise EnterpriseIsolationError(
                f"驾驶舱 {dashboard_id!r} 归属组织 {d.org_id!r} 与当前组织 "
                f"{self._org_id!r} 不一致，禁止跨域访问"
            )
        return d


__all__ = [
    "WidgetType",
    "DashboardWidget",
    "Dashboard",
    "DashboardService",
]
