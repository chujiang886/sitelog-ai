"""Enterprise Data Intelligence & Decision Support Layer —— 趋势分析（任务2，Phase 3.8.6）。

新增：
- ``TrendInsight``：事实型趋势洞察（``trend_id`` / ``org_id`` / ``metric_source`` / ``period`` /
  ``change_pattern`` / ``confidence`` / ``requires_human_review`` / ``source_trace`` / ``source``）。
  只**描述**变化（上升/下降/平稳/波动），**禁止**自动优化/经营建议（红线③/⑥）。
- ``TrendAnalyzer``：``time_series_analysis`` / ``detect_change`` / ``compare_period``；只描述变化，
  不提供任何 optimize / improve / auto_fix 入口。

红线（fail-closed，复用 3.8.0~3.8.5 基座 + 3.8.6 语义升级）：
- 构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
- ``TrendInsight.requires_human_review`` 恒为 True（AI 不代管理判断，红线③/⑥）。
- 不持有 ``approve`` / ``engineering_approved`` / ``quote`` / ``pricing`` / ``sign`` /
  ``authorize`` / ``record_human_approval``。
- 额外拦截自动经营决策 / 自动优化入口（``auto_business_decision`` / ``make_management_decision`` /
  ``optimize_business_strategy`` / ``execute_strategy`` / ``recommend_management_action`` /
  ``auto_decide`` / ``recommend`` / ``decide`` / ``optimize`` / ``improve``）。
- 任何数字必须可溯源（``SourceTrace`` 校验），**禁止 AI 创造数据**（任务5）。
- 可选联动 ``AuditService.record_trend_analysis`` 如实标注分析方 actor（AI 生成记 AI，红线⑥）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agents.enterprise.audit import AuditService
from agents.enterprise.dashboard_visibility import AnalyticsVisibilityPolicy
from agents.enterprise.data_insight import SourceTrace
from agents.enterprise.identity import IdentityService, RoleKind
from agents.enterprise.operation_metric import OperationMetric
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)


@dataclass
class TrendInsight:
    """事实型趋势洞察（任务2）。

    只描述变化（change_pattern），**不**承载任何优化/经营建议语义。
    所有指标均来自可溯源事实（``source_trace`` 必须 ``is_traceable``）。
    """

    trend_id: str
    org_id: str
    metric_source: str = ""             # 趋势所基于的指标说明（如「项目完成率 COUNT 指标」）
    period: str = ""                    # 统计周期（如 2026-Q3 / week-32）
    change_pattern: str = ""            # 变化模式（仅描述：上升/下降/平稳/波动/突变）
    confidence: float = 0.0             # 置信度（0~1，基于事实数据点推导）
    requires_human_review: bool = True  # 恒为 True：AI 不代管理判断（红线③/⑥）
    created_at: str = ""
    source_trace: "SourceTrace | None" = None
    source: str = ""                    # 数据源 tag（project_analytics / workflow_analytics / ...）

    def __post_init__(self) -> None:
        # 红线③/⑥：任何 AI 趋势洞察都强制要求人工复核，AI 不代管理做判断。
        self.requires_human_review = True
        # 任务5：来源不可追溯 → 禁止登记（AI 不得创造无来源数据）。
        if self.source_trace is None or not self.source_trace.is_traceable:
            raise EnterpriseRedLineViolationError(
                f"TrendInsight {self.trend_id!r} 来源不可追溯"
                f"（source_trace 缺失或 is_traceable=False）：禁止登记 AI 创造的无源数据（任务5）"
            )


class TrendAnalyzer(_RedLineForbiddenMixin):
    """趋势分析器（任务2）。

    仅基于事实型指标描述变化趋势；跨域访问抛 ``EnterpriseIsolationError``；
    写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
    本服务**不**持有任何 approve / engineering_approved / quote / pricing / sign /
    authorize / record_human_approval / optimize / improve 等方法（红线②/③/④/⑥）。
    """

    _FORBIDDEN = (
        "approve",
        "engineering_approved",
        "quote",
        "pricing",
        "sign",
        "authorize",
        "record_human_approval",
        # 3.8.6 语义升级：禁止自动经营决策 / 自动优化 / AI 代管理责任
        "auto_business_decision",
        "make_management_decision",
        "optimize_business_strategy",
        "execute_strategy",
        "recommend_management_action",
        "auto_decide",
        "recommend",
        "decide",
        "optimize",
        "improve",
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
                "TrendAnalyzer（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._identity = identity
        self._visibility = visibility

    def _derive_trace_from_metrics(self, metrics: list[OperationMetric]) -> SourceTrace:
        """从事实型指标列表推导 SourceTrace（跨域访问抛隔离错误）。"""
        from agents.enterprise.organization import EnterpriseIsolationError

        mids: list[str] = []
        for m in metrics:
            if m.org_id != self._org_id:
                raise EnterpriseIsolationError(
                    f"指标 {m.metric_id!r} 归属组织 {m.org_id!r} 与当前组织 "
                    f"{self._org_id!r} 不一致，禁止跨域分析"
                )
            mids.append(m.metric_id)
        return SourceTrace(source_metric=mids)

    @staticmethod
    def _describe_direction(values: list[float]) -> "tuple[str, float]":
        """纯描述：判断变化模式与相对幅度（不评价、不优化）。"""
        if len(values) < 2:
            return "insufficient_data", 0.0
        first, last = values[0], values[-1]
        if first == 0:
            if last == 0:
                return "stable", 0.0
            return "increase", 1.0
        delta = (last - first) / abs(first)
        if abs(delta) < 0.05:
            return "stable", round(delta, 4)
        if delta > 0:
            return "increase", round(delta, 4)
        return "decrease", round(delta, 4)

    def time_series_analysis(
        self,
        *,
        trend_id: str,
        metrics: list[OperationMetric],
        period: str = "",
        created_at: str = "",
        source: str = "",
        actor_id: str = "ai",
        actor_kind: "str | None" = None,
    ) -> TrendInsight:
        """对一串事实型指标做时间序列分析（**仅描述**变化，红线③/⑥）。

        输入必须为可溯源的 ``OperationMetric`` 列表；自动构建 SourceTrace（指向指标 id）。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下分析趋势（红线①/⑤）"
            )
        if not metrics:
            raise EnterpriseRedLineViolationError(
                "time_series_analysis 需要至少一条事实型指标（禁 AI 创造无源数据，任务5）"
            )
        trace = self._derive_trace_from_metrics(metrics)
        values = [float(m.value) for m in metrics]
        direction, delta = self._describe_direction(values)
        # 置信度：数据点越多、方向越一致，置信度越高（纯事实推导，不编造）。
        n = len(values)
        consistency = 1.0 if n <= 1 else (
            1.0 if all((values[i] - values[i - 1]) * (values[1] - values[0]) >= 0
                       for i in range(2, n)) else 0.7
        )
        confidence = round(min(1.0, n / 10.0) * consistency, 4)
        pattern = f"{direction};delta={delta};points={n}"
        metric_source = metrics[0].source or "operation_metric"
        ins = TrendInsight(
            trend_id=trend_id,
            org_id=self._org_id,
            metric_source=metric_source,
            period=period,
            change_pattern=pattern,
            confidence=confidence,
            created_at=created_at,
            source_trace=trace,
            source=source or metric_source,
        )
        if self._audit is not None:
            self._audit.record_trend_analysis(
                record_id=f"trend-{trend_id}",
                actor_id=actor_id,
                action="trend_analysis",
                target=trend_id,
                detail=f"pattern={pattern};confidence={confidence};trace={trace.summary()}",
                ts=created_at,
                actor_kind=actor_kind,
            )
        return ins

    def detect_change(
        self,
        *,
        trend_id: str,
        series: list[float],
        source_trace: SourceTrace,
        period: str = "",
        threshold: float = 0.1,
        created_at: str = "",
        source: str = "",
        actor_id: str = "ai",
        actor_kind: "str | None" = None,
    ) -> TrendInsight:
        """检测序列中的显著变化点（**仅描述**变化幅度，红线③/⑥）。

        ``source_trace`` 必须可溯源（调用方负责传入真实数据来源，禁 AI 创造数据）。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下检测变化（红线①/⑤）"
            )
        if source_trace is None or not source_trace.is_traceable:
            raise EnterpriseRedLineViolationError(
                "detect_change 需要可溯源的 source_trace（任务5，禁 AI 创造无源数据）"
            )
        if len(series) < 2:
            raise EnterpriseRedLineViolationError(
                "detect_change 需要至少两个数据点（禁 AI 创造无源数据，任务5）"
            )
        # 纯描述：找最大相邻变化，标注是否超过阈值（不评价、不处置）。
        max_delta = 0.0
        max_idx = 0
        for i in range(1, len(series)):
            d = abs(series[i] - series[i - 1])
            if d > max_delta:
                max_delta = d
                max_idx = i
        changed = max_delta >= threshold
        direction = "increase" if series[max_idx] >= series[max_idx - 1] else "decrease"
        pattern = (
            f"change_point@{max_idx}:{direction};magnitude={round(max_delta, 4)};"
            f"threshold={threshold};exceeded={changed}"
        )
        confidence = round(min(1.0, max_delta / max(threshold, 1e-9)), 4)
        ins = TrendInsight(
            trend_id=trend_id,
            org_id=self._org_id,
            metric_source=source or source_trace.summary(),
            period=period,
            change_pattern=pattern,
            confidence=confidence,
            created_at=created_at,
            source_trace=source_trace,
            source=source,
        )
        if self._audit is not None:
            self._audit.record_trend_analysis(
                record_id=f"trend-{trend_id}",
                actor_id=actor_id,
                action="detect_change",
                target=trend_id,
                detail=f"pattern={pattern};confidence={confidence};trace={source_trace.summary()}",
                ts=created_at,
                actor_kind=actor_kind,
            )
        return ins

    def compare_period(
        self,
        *,
        trend_id: str,
        current: list[float],
        previous: list[float],
        source_trace: SourceTrace,
        period: str = "",
        created_at: str = "",
        source: str = "",
        actor_id: str = "ai",
        actor_kind: "str | None" = None,
    ) -> TrendInsight:
        """对比两个周期的事实数据（**仅描述**环比变化，红线③/⑥）。

        ``source_trace`` 必须可溯源（调用方负责传入真实数据来源，禁 AI 创造数据）。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下对比周期（红线①/⑤）"
            )
        if source_trace is None or not source_trace.is_traceable:
            raise EnterpriseRedLineViolationError(
                "compare_period 需要可溯源的 source_trace（任务5，禁 AI 创造无源数据）"
            )
        cur = sum(current) / len(current) if current else 0.0
        prev = sum(previous) / len(previous) if previous else 0.0
        if prev == 0:
            delta = 1.0 if cur > 0 else 0.0
        else:
            delta = (cur - prev) / abs(prev)
        direction = "stable" if abs(delta) < 0.05 else ("increase" if delta > 0 else "decrease")
        pattern = (
            f"period_over_period:{direction};prev_avg={round(prev, 4)};"
            f"cur_avg={round(cur, 4)};delta={round(delta, 4)}"
        )
        confidence = round(min(1.0, (len(current) + len(previous)) / 10.0), 4)
        ins = TrendInsight(
            trend_id=trend_id,
            org_id=self._org_id,
            metric_source=source or source_trace.summary(),
            period=period,
            change_pattern=pattern,
            confidence=confidence,
            created_at=created_at,
            source_trace=source_trace,
            source=source,
        )
        if self._audit is not None:
            self._audit.record_trend_analysis(
                record_id=f"trend-{trend_id}",
                actor_id=actor_id,
                action="compare_period",
                target=trend_id,
                detail=f"pattern={pattern};confidence={confidence};trace={source_trace.summary()}",
                ts=created_at,
                actor_kind=actor_kind,
            )
        return ins


__all__ = ["TrendInsight", "TrendAnalyzer"]
