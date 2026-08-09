"""Enterprise Analytics & Operation Intelligence Layer —— 运营指标模型（任务1，Phase 3.8.4）。

新增：``OperationMetric``，只记录事实（metric_id / org_id / metric_type / value / period / source）。
``OperationMetricType`` 为**中性、事实型**指标分类（计数/求和/比率/时长/量值），不含任何
评价性/决策性类型。

红线约束（fail-closed，复用 3.8.0~3.8.3 基座 + 3.8.4 语义升级）：
- 所有指标按 ``org_id`` 作用域过滤；跨域访问抛 ``EnterpriseIsolationError``。
- ``OperationMetricService`` 构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
- 本模块不持有批准/报价/审批/记录为人工方法（红线②/③/④/⑥）。
- **只记录事实**：不输出经营决策、不评价工程质量、不代管理做判断（红线③/⑥）。
- 可选联动 ``AuditService`` 如实标注采集方 actor（AI 采集记 AI，人工登记记 USER）。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from agents.enterprise.audit import AuditService
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)


class OperationMetricType(str, Enum):
    """事实型指标分类（中性，不承载评价/决策语义）。"""

    COUNT = "count"          # 计数
    SUM = "sum"              # 求和
    AVERAGE = "average"      # 均值
    RATE = "rate"            # 比率（0~1 或百分化，按接入方约定）
    RATIO = "ratio"          # 比例
    DURATION = "duration"    # 时长（秒/小时，按接入方约定）
    GAUGE = "gauge"          # 量值快照
    DELTA = "delta"          # 增量


@dataclass
class OperationMetric:
    """运营指标（任务1）。

    只记录事实：metric_id / org_id / metric_type / value / period / source。
    不承载评价/决策结论，红线③/⑥ 要求 AI 不代管理做判断。
    """

    metric_id: str
    org_id: str
    metric_type: "OperationMetricType | str"
    value: float
    period: str = ""              # 统计周期（如 2026-Q3 / 2026-08 / week-32）
    source: str = ""              # 数据来源（project / workflow / ai_usage / manual ...）
    recorded_at: str = ""
    recorded_by: str = ""


class OperationMetricService(_RedLineForbiddenMixin):
    """运营指标服务（任务1）。

    仅登记/读取事实型指标；跨域访问抛 ``EnterpriseIsolationError``；
    写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
    本服务**不**持有任何 approve / engineering_approved / quote / pricing / sign /
    authorize / record_human_approval 方法（红线②/③/④/⑥）。
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
    )

    def __init__(self, org_id: str, audit: "AuditService | None" = None) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "OperationMetricService（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._metrics: dict[str, OperationMetric] = {}

    def create_metric(
        self,
        *,
        metric_id: str,
        metric_type: "OperationMetricType | str",
        value: float,
        period: str = "",
        source: str = "",
        recorded_at: str = "",
        recorded_by: str = "",
        actor_kind: "str | None" = None,
    ) -> OperationMetric:
        """登记一条事实型指标（只记录事实，不评价、不决策；红线③/⑥）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下登记运营指标（红线①/⑤）"
            )
        m = OperationMetric(
            metric_id=metric_id,
            org_id=self._org_id,
            metric_type=metric_type,
            value=float(value),
            period=period,
            source=source,
            recorded_at=recorded_at,
            recorded_by=recorded_by,
        )
        self._metrics[metric_id] = m
        if self._audit is not None:
            # 如实标注采集方：默认 AI（由 AI 采集指标时），可显式传 actor_kind='user'。
            from agents.enterprise.audit import AuditActorKind

            kind = AuditActorKind(actor_kind) if actor_kind else AuditActorKind.AI
            if kind == AuditActorKind.USER:
                self._audit.record_user_action(
                    record_id=f"metric-{metric_id}",
                    actor_id=recorded_by or "unknown",
                    action="create_operation_metric",
                    target=metric_id,
                    detail=f"type={m.metric_type};value={m.value};period={m.period}",
                    ts=recorded_at,
                )
            else:
                self._audit.record_ai_action(
                    record_id=f"metric-{metric_id}",
                    actor_id=recorded_by or "ai",
                    action="create_operation_metric",
                    target=metric_id,
                    detail=f"type={m.metric_type};value={m.value};period={m.period}",
                    ts=recorded_at,
                )
        return m

    def get(self, *, metric_id: str) -> OperationMetric:
        """按组织作用域读取指标（跨域访问抛隔离错误）。"""
        return self._get_scoped(metric_id)

    def list_metrics(
        self,
        *,
        metric_type: "OperationMetricType | str | None" = None,
        period: str = "",
    ) -> list[OperationMetric]:
        """列出当前组织下指标（可按 metric_type / period 过滤）。"""
        out = [m for m in self._metrics.values() if m.org_id == self._org_id]
        if metric_type is not None:
            want = metric_type.value if isinstance(metric_type, OperationMetricType) else metric_type
            out = [
                m for m in out
                if (m.metric_type.value if isinstance(m.metric_type, OperationMetricType) else m.metric_type) == want
            ]
        if period:
            out = [m for m in out if m.period == period]
        return out

    def _get_scoped(self, metric_id: str) -> OperationMetric:
        from agents.enterprise.organization import EnterpriseIsolationError

        m = self._metrics.get(metric_id)
        if m is None:
            raise EnterpriseIsolationError(f"运营指标 {metric_id!r} 不存在")
        if m.org_id != self._org_id:
            raise EnterpriseIsolationError(
                f"运营指标 {metric_id!r} 归属组织 {m.org_id!r} 与当前组织 "
                f"{self._org_id!r} 不一致，禁止跨域访问"
            )
        return m


__all__ = ["OperationMetricType", "OperationMetric", "OperationMetricService"]
