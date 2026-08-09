"""Enterprise Data Intelligence & Decision Support Layer —— 数据洞察（任务1 + 任务5 SourceTrace，Phase 3.8.6）。

新增：
- ``SourceTrace``：来源追踪（至少含 ``source_metric`` / ``source_workflow`` / ``source_event`` /
  ``source_dashboard`` 之一；任何数字必须可溯源，**禁止 AI 创造无来源数据**）。
- ``DataInsight``：事实型洞察（``insight_id`` / ``org_id`` / ``source_data`` / ``pattern`` /
  ``confidence`` / ``description`` / ``requires_human_review`` / ``created_at`` / ``source_trace`` /
  ``source``）。结构体上**禁止**承载 ``decision`` / ``recommendation`` / ``approval`` / ``action`` /
  ``strategy`` 语义（红线③/⑥：AI 只描述，不决策、不代管理责任）。
- ``DataInsightService``：``create_insight`` / ``get`` / ``list_insights`` / ``query``；组织隔离 +
  审计 + 权限级 source 过滤；**来源不可追溯禁止登记**。

红线（fail-closed，复用 3.8.0~3.8.5 基座 + 3.8.6 语义升级）：
- 构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
- ``DataInsight.requires_human_review`` 恒为 True（AI 不代管理判断，红线③/⑥）。
- 不持有 ``approve`` / ``engineering_approved`` / ``quote`` / ``pricing`` / ``sign`` /
  ``authorize`` / ``record_human_approval``。
- 额外拦截自动经营决策入口（``auto_business_decision`` / ``make_management_decision`` /
  ``recommend_management_action`` / ``optimize_business_strategy`` / ``execute_strategy`` /
  ``decide_operation`` / ``auto_decision`` / ``recommend`` / ``decide``）。
- 任何数字必须可溯源（``SourceTrace.is_traceable`` 校验），**禁止 AI 创造数据**（任务5）。
- 可选联动 ``AuditService.record_data_insight`` 如实标注生成方 actor（AI 生成记 AI，红线⑥）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agents.enterprise.audit import AuditService
from agents.enterprise.identity import IdentityService, RoleKind
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)
from agents.enterprise.dashboard_visibility import AnalyticsVisibilityPolicy


# Insight 模型禁止承载的「决策/建议/批准」语义字段（结构性 fail-closed）。
_FORBIDDEN_INSIGHT_FACT_KEYS = (
    "decision",
    "recommendation",
    "approval",
    "approved",
    "action",
    "strategy",
    "quote",
    "pricing",
    "engineering_approved",
)


@dataclass
class SourceTrace:
    """来源追踪（任务5）。

    任何数字必须可溯源：至少关联一种事实数据源（指标 / 流程分析 / AI 使用事件 / 驾驶舱）。
    ``is_traceable`` 为 False 时，禁止据此生成任何 Insight/Trend/Anomaly/Report。
    """

    source_metric: list = field(default_factory=list)     # 关联的事实指标 id（OperationMetric.metric_id）
    source_workflow: list = field(default_factory=list)   # 关联的流程分析 id（WorkflowAnalytics.analytics_id）
    source_event: list = field(default_factory=list)      # 关联的 AI 使用事件 id（AIUsageEvent.event_id）
    source_dashboard: list = field(default_factory=list)  # 关联的驾驶舱 id（Dashboard.dashboard_id）
    raw_refs: list = field(default_factory=list)          # 原始数据引用（record_id / 文件 / 外部源标识）
    note: str = ""                                        # 中性溯源说明（不得含决策/建议语义）

    @property
    def is_traceable(self) -> bool:
        """是否至少关联了一种事实数据源（或原始引用）。"""
        return bool(
            self.source_metric
            or self.source_workflow
            or self.source_event
            or self.source_dashboard
            or self.raw_refs
        )

    def summary(self) -> str:
        """只读汇总溯源链（不改动任何状态）。"""
        parts = []
        if self.source_metric:
            parts.append(f"metric={','.join(self.source_metric)}")
        if self.source_workflow:
            parts.append(f"workflow={','.join(self.source_workflow)}")
        if self.source_event:
            parts.append(f"event={','.join(self.source_event)}")
        if self.source_dashboard:
            parts.append(f"dashboard={','.join(self.source_dashboard)}")
        if self.raw_refs:
            parts.append(f"raw={','.join(self.raw_refs)}")
        return ";".join(parts) if parts else "untraceable"


@dataclass
class DataInsight:
    """事实型数据洞察（任务1）。

    只描述 pattern / confidence / description，**不**承载任何决策/建议/批准语义。
    所有字段均为事实型，且必须可溯源（``source_trace`` 必须 ``is_traceable``）。
    """

    insight_id: str
    org_id: str
    source_data: str = ""                # 来源数据简述（事实引用，如「2026-Q3 项目完成率指标」）
    pattern: str = ""                    # 发现的模式/规律（仅描述，不评价、不决策）
    confidence: float = 0.0              # 置信度（0~1，基于事实数据推导）
    description: str = ""                # 中性描述（不得含决策/建议）
    requires_human_review: bool = True   # 恒为 True：AI 不代管理判断（红线③/⑥）
    created_at: str = ""
    source_trace: "SourceTrace | None" = None
    source: str = ""                     # 数据源 tag（project_analytics / workflow_analytics /
                                         # ai_usage_analytics / operation_risk ...）

    def __post_init__(self) -> None:
        # 红线③/⑥：任何 AI 数据洞察都强制要求人工复核，AI 不代管理做判断。
        self.requires_human_review = True
        # 任务5：来源不可追溯 → 禁止登记（AI 不得创造无来源数据）。
        if self.source_trace is None or not self.source_trace.is_traceable:
            raise EnterpriseRedLineViolationError(
                f"DataInsight {self.insight_id!r} 来源不可追溯"
                f"（source_trace 缺失或 is_traceable=False）：禁止登记 AI 创造的无源数据（任务5）"
            )


class DataInsightService(_RedLineForbiddenMixin):
    """数据洞察服务（任务1 + 任务5）。

    仅登记/读取事实型数据洞察；跨域访问抛 ``EnterpriseIsolationError``；
    写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
    本服务**不**持有任何 approve / engineering_approved / quote / pricing / sign /
    authorize / record_human_approval / auto_business_decision 等方法（红线②/③/④/⑥）。
    """

    _FORBIDDEN = (
        "approve",
        "engineering_approved",
        "quote",
        "pricing",
        "sign",
        "authorize",
        "record_human_approval",
        # 3.8.6 语义升级：禁止自动经营决策 / 管理建议 / AI 代管理责任
        "auto_business_decision",
        "make_management_decision",
        "recommend_management_action",
        "optimize_business_strategy",
        "execute_strategy",
        "decide_operation",
        "auto_decision",
        "recommend",
        "decide",
    )

    def __init__(
        self,
        org_id: str,
        audit: "AuditService | None" = None,
        identity: "IdentityService | None" = None,
        visibility: "AnalyticsVisibilityPolicy | None" = None,
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "DataInsightService（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._identity = identity
        self._visibility = visibility
        self._insights: dict[str, DataInsight] = {}

    def create_insight(
        self,
        *,
        insight_id: str,
        source_data: str,
        pattern: str,
        confidence: float,
        description: str = "",
        created_at: str = "",
        source_trace: "SourceTrace | None" = None,
        source: str = "",
        actor_id: str = "ai",
        actor_kind: "str | None" = None,
    ) -> DataInsight:
        """登记一条事实型数据洞察（必须先满足来源可溯源，红线③/⑥）。

        ``source_trace`` 必须 ``is_traceable``，否则抛红线违例（任务5：禁 AI 创造无源数据）。
        登记后如实记录 ``record_data_insight``（actor 默认 AI，红线⑥）。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下登记数据洞察（红线①/⑤）"
            )
        # 任务5：结构性强制来源可溯源，先于 Insight 构造。
        if source_trace is None or not source_trace.is_traceable:
            raise EnterpriseRedLineViolationError(
                "创建 DataInsight 失败：source_trace 必须可溯源（任务5，禁 AI 创造无源数据）"
            )
        # 防编造：任何数字（confidence）必须来自可溯源事实，这里仅做范围校验，不编造。
        conf = float(confidence)
        if not (0.0 <= conf <= 1.0):
            conf = max(0.0, min(1.0, conf))
        ins = DataInsight(
            insight_id=insight_id,
            org_id=self._org_id,
            source_data=source_data,
            pattern=pattern,
            confidence=conf,
            description=description,
            created_at=created_at,
            source_trace=source_trace,
            source=source,
        )
        self._insights[insight_id] = ins
        if self._audit is not None:
            self._audit.record_data_insight(
                record_id=f"insight-{insight_id}",
                actor_id=actor_id,
                action="create_data_insight",
                target=insight_id,
                detail=(
                    f"source={source};confidence={ins.confidence};"
                    f"trace={ins.source_trace.summary()}"
                ),
                ts=created_at,
                actor_kind=actor_kind,
            )
        return ins

    def get(self, *, insight_id: str) -> DataInsight:
        """按组织作用域读取洞察（跨域访问抛隔离错误）。"""
        return self._get_scoped(insight_id)

    def list_insights(
        self,
        *,
        source: str = "",
        requires_human_review: "bool | None" = None,
        role: "RoleKind | None" = None,
    ) -> list[DataInsight]:
        """列出当前组织下洞察（可按 source / 是否需人工复核过滤）。

        ``role`` 给定且本服务持有 ``AnalyticsVisibilityPolicy`` 时，按角色级 source 可见性过滤
        （任务6：ADMIN 可见全源，EXPERT 仅 project_analytics+ai_usage_analytics 等）。
        """
        out = [i for i in self._insights.values() if i.org_id == self._org_id]
        if source:
            out = [i for i in out if i.source == source]
        if requires_human_review is not None:
            out = [i for i in out if i.requires_human_review == requires_human_review]
        if role is not None and self._visibility is not None:
            out = [
                i for i in out
                if self._visibility.is_source_permitted(role, i.source)
            ]
        return out

    def query(
        self,
        *,
        source: str = "",
        pattern_contains: str = "",
        role: "RoleKind | None" = None,
    ) -> list[DataInsight]:
        """按条件查询洞察（只读；支持 source / pattern 子串 / 角色可见性过滤）。"""
        out = self.list_insights(source=source, role=role)
        if pattern_contains:
            out = [i for i in out if pattern_contains in (i.pattern or "")]
        return out

    def _get_scoped(self, insight_id: str) -> DataInsight:
        from agents.enterprise.organization import EnterpriseIsolationError

        ins = self._insights.get(insight_id)
        if ins is None:
            raise EnterpriseIsolationError(f"数据洞察 {insight_id!r} 不存在")
        if ins.org_id != self._org_id:
            raise EnterpriseIsolationError(
                f"数据洞察 {insight_id!r} 归属组织 {ins.org_id!r} 与当前组织 "
                f"{self._org_id!r} 不一致，禁止跨域访问"
            )
        return ins


__all__ = ["SourceTrace", "DataInsight", "DataInsightService", "_FORBIDDEN_INSIGHT_FACT_KEYS"]
