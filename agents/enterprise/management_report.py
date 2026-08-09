"""Enterprise Data Intelligence & Decision Support Layer —— 管理报告（任务4，Phase 3.8.6）。

新增：
- ``ManagementReport``：事实型管理报告（``report_id`` / ``org_id`` / ``period`` / ``facts`` /
  ``trends`` / ``risks`` / ``sources`` / ``created_at`` / ``source_trace``）。
  **禁止**承载经营建议 / 管理决策 / 执行方案（红线③/⑥：AI 只汇编事实，不替管理做决策）。
- ``ManagementReportService``：``generate_report`` 把已有的事实型洞察 / 趋势 / 风险 / 异常**汇编**
  为一份管理报告；所有数字必须可溯源（``SourceTrace`` 聚合校验，任务5）。

红线（fail-closed，复用 3.8.0~3.8.5 基座 + 3.8.6 语义升级）：
- 构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
- 不持有 ``approve`` / ``engineering_approved`` / ``quote`` / ``pricing`` / ``sign`` /
  ``authorize`` / ``record_human_approval``。
- 额外拦截经营决策 / 建议入口（``make_management_decision`` / ``recommend_management_action`` /
  ``optimize_business_strategy`` / ``execute_strategy`` / ``auto_business_decision`` /
  ``decide_operation`` / ``auto_decision`` / ``recommend`` / ``decide``）。
- 任何数字必须可溯源（``SourceTrace`` 聚合校验），**禁止 AI 创造数据**（任务5）。
- 可选联动 ``AuditService.record_report_generation`` 如实标注生成方 actor（AI 生成记 AI，红线⑥）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agents.enterprise.audit import AuditService
from agents.enterprise.dashboard_visibility import AnalyticsVisibilityPolicy
from agents.enterprise.data_insight import DataInsight, SourceTrace
from agents.enterprise.anomaly_detection import AnomalyCandidate
from agents.enterprise.identity import IdentityService, RoleKind
from agents.enterprise.operation_risk import RiskCandidate
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)
from agents.enterprise.trend_analysis import TrendInsight


def _merge_trace(traces: list[SourceTrace]) -> SourceTrace:
    """聚合多个 SourceTrace 为单一溯源链（只读合并，不改动输入）。"""
    merged = SourceTrace()
    for t in traces:
        if t is None:
            continue
        merged.source_metric = merged.source_metric + list(t.source_metric)
        merged.source_workflow = merged.source_workflow + list(t.source_workflow)
        merged.source_event = merged.source_event + list(t.source_event)
        merged.source_dashboard = merged.source_dashboard + list(t.source_dashboard)
        merged.raw_refs = merged.raw_refs + list(t.raw_refs)
    # 去重，保留顺序
    merged.source_metric = list(dict.fromkeys(merged.source_metric))
    merged.source_workflow = list(dict.fromkeys(merged.source_workflow))
    merged.source_event = list(dict.fromkeys(merged.source_event))
    merged.source_dashboard = list(dict.fromkeys(merged.source_dashboard))
    merged.raw_refs = list(dict.fromkeys(merged.raw_refs))
    return merged


@dataclass
class ManagementReport:
    """事实型管理报告（任务4）。

    只汇编 facts / trends / risks / sources（全部事实型且可溯源），**不**含任何经营建议 /
    管理决策 / 执行方案（红线③/⑥）。
    """

    report_id: str
    org_id: str
    period: str = ""                      # 报告周期（如 2026-Q3 / 2026-08）
    facts: list = field(default_factory=list)    # 汇编的事实 id（指标/洞察）
    trends: list = field(default_factory=list)   # 汇编的趋势 id
    risks: list = field(default_factory=list)    # 汇编的风险/异常 id
    sources: list = field(default_factory=list)  # 数据源 tag 列表
    created_at: str = ""
    source_trace: "SourceTrace | None" = None

    def __post_init__(self) -> None:
        # 任务5：来源不可追溯 → 禁止生成报告（AI 不得创造无来源数据）。
        if self.source_trace is None or not self.source_trace.is_traceable:
            raise EnterpriseRedLineViolationError(
                f"ManagementReport {self.report_id!r} 来源不可追溯"
                f"（source_trace 缺失或 is_traceable=False）：禁止生成 AI 创造的"
                f"无源报告（任务5）"
            )


class ManagementReportService(_RedLineForbiddenMixin):
    """管理报告服务（任务4）。

    仅把已有的事实型洞察 / 趋势 / 风险 / 异常**汇编**为管理报告；跨域访问抛隔离错误；
    写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
    本服务**不**持有任何 approve / engineering_approved / quote / pricing / sign /
    authorize / record_human_approval / make_management_decision 等方法（红线②/③/④/⑥）。
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
        "make_management_decision",
        "recommend_management_action",
        "optimize_business_strategy",
        "execute_strategy",
        "auto_business_decision",
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
                "ManagementReportService（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._identity = identity
        self._visibility = visibility

    def generate_report(
        self,
        *,
        report_id: str,
        period: str = "",
        insights: "list[DataInsight] | None" = None,
        trends: "list[TrendInsight] | None" = None,
        anomalies: "list[AnomalyCandidate] | None" = None,
        risks: "list[RiskCandidate] | None" = None,
        created_at: str = "",
        actor_id: str = "ai",
        actor_kind: "str | None" = None,
    ) -> ManagementReport:
        """汇编事实型管理报告（**仅汇总事实**，红线③/⑥）。

        所有输入必须归属当前组织；其 ``source_trace`` 被聚合为报告的统一溯源链，
        若聚合后不可溯源则抛红线违例（任务5：禁 AI 创造无源报告）。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下生成管理报告（红线①/⑤）"
            )
        insights = insights or []
        trends = trends or []
        anomalies = anomalies or []
        risks = risks or []

        from agents.enterprise.organization import EnterpriseIsolationError

        all_inputs: list = list(insights) + list(trends) + list(anomalies) + list(risks)
        if not all_inputs:
            raise EnterpriseRedLineViolationError(
                "generate_report 至少需要一条事实型输入（洞察/趋势/异常/风险），"
                "禁止生成空的无源报告（任务5）"
            )
        for obj in all_inputs:
            if getattr(obj, "org_id", None) != self._org_id:
                raise EnterpriseIsolationError(
                    f"报告输入归属组织 {getattr(obj, 'org_id', None)!r} 与当前组织 "
                    f"{self._org_id!r} 不一致，禁止跨域汇编"
                )

        trace = _merge_trace([getattr(o, "source_trace", None) for o in all_inputs])
        if not trace.is_traceable:
            raise EnterpriseRedLineViolationError(
                "generate_report 聚合后的溯源链不可追溯：禁止生成 AI 创造的无源报告（任务5）"
            )

        fact_ids = [i.insight_id for i in insights]
        trend_ids = [t.trend_id for t in trends]
        risk_ids = [c.anomaly_id for c in anomalies] + [r.risk_id for r in risks]
        source_tags = list(dict.fromkeys(
            [i.source for i in insights if i.source]
            + [t.source for t in trends if t.source]
            + [c.source for c in anomalies if c.source]
            + [r.risk_type for r in risks if r.risk_type]
        ))

        report = ManagementReport(
            report_id=report_id,
            org_id=self._org_id,
            period=period,
            facts=fact_ids,
            trends=trend_ids,
            risks=risk_ids,
            sources=source_tags,
            created_at=created_at,
            source_trace=trace,
        )
        if self._audit is not None:
            self._audit.record_report_generation(
                record_id=f"report-{report_id}",
                actor_id=actor_id,
                action="generate_management_report",
                target=report_id,
                detail=(
                    f"period={period};facts={len(fact_ids)};trends={len(trend_ids)};"
                    f"risks={len(risk_ids)};trace={trace.summary()}"
                ),
                ts=created_at,
                actor_kind=actor_kind,
            )
        return report


__all__ = ["ManagementReport", "ManagementReportService", "_merge_trace"]
