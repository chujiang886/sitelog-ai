"""Enterprise Data Intelligence & Decision Support Layer —— 异常发现（任务3，Phase 3.8.6）。

新增：
- ``AnomalyCandidate``：事实型异常候选（``anomaly_id`` / ``org_id`` / ``source`` / ``pattern`` /
  ``severity`` / ``evidence`` / ``requires_human_confirmation`` / ``source_trace``）。
  ``requires_human_confirmation`` 恒为 True，**禁止自动处置**（红线③/⑥）。
- ``AnomalyDetector``：输入 ``OperationMetric`` / ``WorkflowAnalytics`` / ``AIUsageAnalytics`` /
  ``Dashboard``，输出 ``AnomalyCandidate``。**禁止**任何 ``resolve`` / ``mitigate`` / ``fix`` /
  ``close`` 处置入口（红线③/⑥：AI 只发现、不处置、不代管理责任）。

红线（fail-closed，复用 3.8.0~3.8.5 基座 + 3.8.6 语义升级）：
- 构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
- ``AnomalyCandidate.requires_human_confirmation`` 恒为 True（必须人工确认）。
- 不持有 ``approve`` / ``engineering_approved`` / ``quote`` / ``pricing`` / ``sign`` /
  ``authorize`` / ``record_human_approval``。
- 额外拦截处置入口（``resolve`` / ``mitigate`` / ``fix`` / ``close`` / ``auto_business_decision`` /
  ``make_management_decision`` / ``recommend_management_action`` / ``optimize_business_strategy``）。
- 任何数字必须可溯源（``SourceTrace`` 校验），**禁止 AI 创造数据**（任务5）。
- 可选联动 ``AuditService.record_anomaly_detection`` 如实标注检测方 actor（AI 生成记 AI，红线⑥）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agents.enterprise.ai_usage_analytics import AIUsageAnalytics
from agents.enterprise.audit import AuditService
from agents.enterprise.dashboard import Dashboard
from agents.enterprise.dashboard_visibility import AnalyticsVisibilityPolicy
from agents.enterprise.data_insight import SourceTrace
from agents.enterprise.identity import IdentityService, RoleKind
from agents.enterprise.operation_metric import OperationMetric
from agents.enterprise.operation_risk import RiskSeverity
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)
from agents.enterprise.workflow_analytics import WorkflowAnalytics


@dataclass
class AnomalyCandidate:
    """事实型异常候选（任务3）。

    由 AI 检测输出，**要求人工确认**（``requires_human_confirmation`` 恒为 True）。
    AI 不代管理做处置（红线③/⑥）：不含任何已处置/已解决状态，且不提供 resolve/fix 入口。
    """

    anomaly_id: str
    org_id: str
    source: str = ""                     # 数据源 tag（project_analytics / workflow_analytics / ...）
    pattern: str = ""                    # 异常模式（仅描述，不评价、不处置）
    severity: RiskSeverity = RiskSeverity.MEDIUM
    evidence: str = ""                   # 触发证据（事实数据）
    requires_human_confirmation: bool = True   # 恒为 True：必须人工确认
    created_at: str = ""
    source_trace: "SourceTrace | None" = None

    def __post_init__(self) -> None:
        # 红线③/⑥：任何异常候选都强制要求人工确认，AI 不代管理做判断/处置。
        self.requires_human_confirmation = True
        # 任务5：来源不可追溯 → 禁止登记（AI 不得创造无来源数据）。
        if self.source_trace is None or not self.source_trace.is_traceable:
            raise EnterpriseRedLineViolationError(
                f"AnomalyCandidate {self.anomaly_id!r} 来源不可追溯"
                f"（source_trace 缺失或 is_traceable=False）：禁止登记 AI 创造的无源数据（任务5）"
            )


class AnomalyDetector(_RedLineForbiddenMixin):
    """异常发现检测器（任务3）。

    基于事实型指标 / 流程分析 / AI 使用分析 / 驾驶舱，输出异常候选，**要求人工确认**；
    **不**代管理做处置（红线③/⑥）。跨域访问抛 ``EnterpriseIsolationError``；
    构造断言 ``safety_invariants_ok()``（红线①/⑤）。
    """

    _FORBIDDEN = (
        "approve",
        "engineering_approved",
        "quote",
        "pricing",
        "sign",
        "authorize",
        "record_human_approval",
        # 3.8.6 语义升级：禁止自动经营决策 / 处置 / AI 代管理责任
        "resolve",
        "mitigate",
        "fix",
        "close",
        "auto_business_decision",
        "make_management_decision",
        "recommend_management_action",
        "optimize_business_strategy",
        "execute_strategy",
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
                "AnomalyDetector（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._identity = identity
        self._visibility = visibility

    def detect_from_metrics(
        self,
        *,
        anomaly_id: str,
        metrics: list[OperationMetric],
        baseline_value: float,
        threshold: float = 0.2,
        created_at: str = "",
        actor_id: str = "ai",
        actor_kind: "str | None" = None,
    ) -> AnomalyCandidate:
        """基于事实型指标偏离基线检测异常（**仅发现**，红线③/⑥）。

        当任一指标偏离基线超过 ``threshold`` 比例时，输出异常候选。指标必须归属当前组织。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下检测异常（红线①/⑤）"
            )
        if not metrics:
            raise EnterpriseRedLineViolationError(
                "detect_from_metrics 需要至少一条事实型指标（禁 AI 创造无源数据，任务5）"
            )
        from agents.enterprise.organization import EnterpriseIsolationError

        mids: list[str] = []
        worst: "OperationMetric | None" = None
        worst_dev = 0.0
        for m in metrics:
            if m.org_id != self._org_id:
                raise EnterpriseIsolationError(
                    f"指标 {m.metric_id!r} 归属组织 {m.org_id!r} 与当前组织 "
                    f"{self._org_id!r} 不一致，禁止跨域检测"
                )
            mids.append(m.metric_id)
            dev = abs(float(m.value) - baseline_value) / max(abs(baseline_value), 1e-9)
            if dev > worst_dev:
                worst_dev = dev
                worst = m
        sev = RiskSeverity.LOW
        if worst_dev >= threshold * 3:
            sev = RiskSeverity.HIGH
        elif worst_dev >= threshold:
            sev = RiskSeverity.MEDIUM
        else:
            sev = RiskSeverity.LOW
        trace = SourceTrace(source_metric=mids)
        pattern = (
            f"metric_deviation;baseline={baseline_value};max_deviation="
            f"{round(worst_dev, 4)};threshold={threshold}"
        )
        evidence = (
            f"metric={worst.metric_id if worst else ''};value="
            f"{worst.value if worst else ''};source={worst.source if worst else ''}"
        )
        cand = AnomalyCandidate(
            anomaly_id=anomaly_id,
            org_id=self._org_id,
            source=worst.source if worst else "operation_metric",
            pattern=pattern,
            severity=sev,
            evidence=evidence,
            created_at=created_at,
            source_trace=trace,
        )
        self._record(cand, actor_id, actor_kind, created_at)
        return cand

    def detect_from_workflow_analytics(
        self,
        *,
        anomaly_id: str,
        analytics: WorkflowAnalytics,
        created_at: str = "",
        actor_id: str = "ai",
        actor_kind: "str | None" = None,
    ) -> AnomalyCandidate:
        """基于流程效率分析检测异常（瓶颈 / SLA 逾期，仅发现，红线③/⑥）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下检测异常（红线①/⑤）"
            )
        if analytics.org_id != self._org_id:
            from agents.enterprise.organization import EnterpriseIsolationError

            raise EnterpriseIsolationError(
                f"流程分析 {analytics.analytics_id!r} 归属组织 {analytics.org_id!r} "
                f"与当前组织 {self._org_id!r} 不一致，禁止跨域检测"
            )
        overdue = analytics.sla_status.get("overdue", 0)
        warning = analytics.sla_status.get("warning", 0)
        sev = RiskSeverity.LOW
        if overdue:
            sev = RiskSeverity.HIGH
        elif warning:
            sev = RiskSeverity.MEDIUM
        trace = SourceTrace(source_workflow=[analytics.analytics_id])
        pattern = (
            f"workflow_bottleneck={analytics.bottleneck or 'none'};"
            f"sla_overdue={overdue};sla_warning={warning}"
        )
        cand = AnomalyCandidate(
            anomaly_id=anomaly_id,
            org_id=self._org_id,
            source="workflow_analytics",
            pattern=pattern,
            severity=sev,
            evidence=analytics.insight or pattern,
            created_at=created_at,
            source_trace=trace,
        )
        self._record(cand, actor_id, actor_kind, created_at)
        return cand

    def detect_from_ai_usage_analytics(
        self,
        *,
        anomaly_id: str,
        analytics: AIUsageAnalytics,
        fail_rate_threshold: float = 0.1,
        created_at: str = "",
        actor_id: str = "ai",
        actor_kind: "str | None" = None,
    ) -> AnomalyCandidate:
        """基于 AI 使用分析检测异常（失败率过高，仅发现，红线③/⑥）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下检测异常（红线①/⑤）"
            )
        if analytics.org_id != self._org_id:
            from agents.enterprise.organization import EnterpriseIsolationError

            raise EnterpriseIsolationError(
                f"AI 使用分析 {analytics.analytics_id!r} 归属组织 {analytics.org_id!r} "
                f"与当前组织 {self._org_id!r} 不一致，禁止跨域检测"
            )
        total = analytics.total_calls
        fail_rate = (analytics.response_fail / total) if total else 0.0
        sev = RiskSeverity.LOW
        if fail_rate >= fail_rate_threshold:
            sev = RiskSeverity.HIGH if fail_rate >= fail_rate_threshold * 3 else RiskSeverity.MEDIUM
        trace = SourceTrace(raw_refs=[analytics.analytics_id])
        pattern = (
            f"ai_usage_fail_rate={round(fail_rate, 4)};"
            f"threshold={fail_rate_threshold};total={total};fail={analytics.response_fail}"
        )
        cand = AnomalyCandidate(
            anomaly_id=anomaly_id,
            org_id=self._org_id,
            source="ai_usage_analytics",
            pattern=pattern,
            severity=sev,
            evidence=f"total_calls={total};fail={analytics.response_fail};ok={analytics.response_ok}",
            created_at=created_at,
            source_trace=trace,
        )
        self._record(cand, actor_id, actor_kind, created_at)
        return cand

    def detect_from_dashboard(
        self,
        *,
        anomaly_id: str,
        dashboard: Dashboard,
        created_at: str = "",
        actor_id: str = "ai",
        actor_kind: "str | None" = None,
    ) -> AnomalyCandidate:
        """基于驾驶舱组件检测异常（扫描 risk 类组件事实，仅发现，红线③/⑥）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下检测异常（红线①/⑤）"
            )
        if dashboard.org_id != self._org_id:
            from agents.enterprise.organization import EnterpriseIsolationError

            raise EnterpriseIsolationError(
                f"驾驶舱 {dashboard.dashboard_id!r} 归属组织 {dashboard.org_id!r} "
                f"与当前组织 {self._org_id!r} 不一致，禁止跨域检测"
            )
        risk_widgets = [w for w in dashboard.widgets if w.widget_type_value() == "risk"]
        sev = RiskSeverity.LOW if risk_widgets else RiskSeverity.LOW
        trace = SourceTrace(source_dashboard=[dashboard.dashboard_id])
        pattern = f"dashboard_risk_widgets={len(risk_widgets)};dashboard={dashboard.dashboard_id}"
        cand = AnomalyCandidate(
            anomaly_id=anomaly_id,
            org_id=self._org_id,
            source="operation_risk",
            pattern=pattern,
            severity=sev,
            evidence=pattern,
            created_at=created_at,
            source_trace=trace,
        )
        self._record(cand, actor_id, actor_kind, created_at)
        return cand

    def _record(
        self,
        cand: AnomalyCandidate,
        actor_id: str,
        actor_kind: "str | None",
        created_at: str,
    ) -> None:
        if self._audit is not None:
            self._audit.record_anomaly_detection(
                record_id=f"anomaly-{cand.anomaly_id}",
                actor_id=actor_id,
                action="detect_anomaly",
                target=cand.anomaly_id,
                detail=(
                    f"severity={cand.severity.value};pattern={cand.pattern};"
                    f"trace={cand.source_trace.summary()}"
                ),
                ts=created_at,
                actor_kind=actor_kind,
            )


__all__ = ["AnomalyCandidate", "AnomalyDetector"]
