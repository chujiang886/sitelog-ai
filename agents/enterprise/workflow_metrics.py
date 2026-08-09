"""Enterprise Operation Layer —— 流程统计（任务5，Phase 3.8.3）。

新增：``WorkflowMetrics``，记录/汇总 duration / stage_time / completion_rate。

隔离与红线约束（fail-closed，复用 3.8.0~3.8.2 基座）：
- 所有统计按 ``org_id`` 作用域过滤；跨域访问抛 ``EnterpriseIsolationError``。
- ``WorkflowMetricsService`` 构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
- 本模块不持有批准/报价/审批方法（红线②/③/④）；统计仅为如实汇总，不含任何审批结论
  或工程参数（红线⑥）。
- 可选联动 ``AuditService.record_workflow_event`` 如实标注动作发起方（actor 真实）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agents.enterprise.audit import AuditService
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    safety_invariants_ok,
)


@dataclass
class WorkflowMetrics:
    """流程统计（任务5）。

    记录 duration（总耗时）/ stage_time（各阶段耗时映射）/ completion_rate（完成率 0~1）。
    仅为如实汇总，不携带审批结论或工程参数。
    """

    metrics_id: str
    org_id: str
    template_id: str = ""
    workflow_id: str = ""
    duration: float = 0.0                       # 总耗时（秒/小时，按接入方约定）
    stage_time: dict = field(default_factory=dict)  # {stage_name: 耗时}
    completion_rate: float = 0.0                # 0.0 ~ 1.0
    sample_size: int = 0                        # 参与统计的流程实例数
    computed_at: str = ""


class WorkflowMetricsService:
    """流程统计服务（任务5）。

    仅做指标登记与汇总；跨域访问抛 ``EnterpriseIsolationError``；
    写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
    本服务**不**持有任何 approve / engineering_approved / quote / pricing / sign /
    authorize 方法（红线②/③/④）。
    """

    def __init__(self, org_id: str, audit: "AuditService | None" = None) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "WorkflowMetricsService（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._metrics: dict[str, WorkflowMetrics] = {}

    def record_metrics(
        self,
        *,
        metrics_id: str,
        template_id: str = "",
        workflow_id: str = "",
        duration: float = 0.0,
        stage_time: dict | None = None,
        completion_rate: float = 0.0,
        sample_size: int = 0,
        computed_at: str = "",
        computed_by: str = "",
    ) -> WorkflowMetrics:
        """登记一条流程统计（如实汇总，不审批、不含工程参数；红线⑥）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下登记流程统计（红线①/⑤）"
            )
        # completion_rate 钳制在 [0, 1]，防止越界（仅为数据规整，非审批）。
        rate = max(0.0, min(1.0, float(completion_rate)))
        m = WorkflowMetrics(
            metrics_id=metrics_id,
            org_id=self._org_id,
            template_id=template_id,
            workflow_id=workflow_id,
            duration=float(duration),
            stage_time=dict(stage_time or {}),
            completion_rate=rate,
            sample_size=int(sample_size),
            computed_at=computed_at,
        )
        self._metrics[metrics_id] = m
        if self._audit is not None:
            self._audit.record_workflow_event(
                record_id=f"metrics-{metrics_id}",
                actor_id=computed_by or "system",
                action="record_workflow_metrics",
                target=(workflow_id or template_id),
                detail=(
                    f"duration={m.duration};completion_rate={m.completion_rate};"
                    f"sample_size={m.sample_size}"
                ),
                ts=computed_at,
            )
        return m

    def aggregate(
        self,
        *,
        metrics_id: str,
        template_id: str = "",
        records: list[WorkflowMetrics] | None = None,
    ) -> WorkflowMetrics:
        """对一组指标做聚合（均值 duration / completion_rate，stage_time 求和）。

        ``records`` 为空时按 template_id 自动聚合当前组织内已登记指标。返回汇总的
        ``WorkflowMetrics``（仅统计值，不含审批语义）。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下聚合流程统计（红线①/⑤）"
            )
        recs = list(records or [])
        if not recs and template_id:
            recs = [
                m for m in self._metrics.values()
                if m.org_id == self._org_id and m.template_id == template_id
            ]
        recs = [r for r in recs if r.org_id == self._org_id]
        n = len(recs)
        if n == 0:
            agg = WorkflowMetrics(
                metrics_id=metrics_id,
                org_id=self._org_id,
                template_id=template_id,
                duration=0.0,
                stage_time={},
                completion_rate=0.0,
                sample_size=0,
            )
            self._metrics[metrics_id] = agg
            return agg
        dur = sum(r.duration for r in recs) / n
        rate = sum(r.completion_rate for r in recs) / n
        stage_sum: dict = {}
        for r in recs:
            for k, v in r.stage_time.items():
                stage_sum[k] = stage_sum.get(k, 0.0) + float(v)
        agg = WorkflowMetrics(
            metrics_id=metrics_id,
            org_id=self._org_id,
            template_id=template_id,
            duration=dur,
            stage_time=stage_sum,
            completion_rate=max(0.0, min(1.0, rate)),
            sample_size=n,
        )
        self._metrics[metrics_id] = agg
        if self._audit is not None:
            self._audit.record_workflow_event(
                record_id=f"metrics-agg-{metrics_id}",
                actor_id="system",
                action="aggregate_workflow_metrics",
                target=template_id,
                detail=f"sample_size={n};duration={dur};completion_rate={agg.completion_rate}",
            )
        return agg

    def get(self, *, metrics_id: str) -> WorkflowMetrics:
        """按组织作用域读取统计（跨域访问抛隔离错误）。"""
        return self._get_scoped(metrics_id)

    def list_metrics(self, *, template_id: str = "") -> list[WorkflowMetrics]:
        """列出当前组织下统计（可按 template 过滤）。"""
        out = [m for m in self._metrics.values() if m.org_id == self._org_id]
        if template_id:
            out = [m for m in out if m.template_id == template_id]
        return out

    def _get_scoped(self, metrics_id: str) -> WorkflowMetrics:
        from agents.enterprise.organization import EnterpriseIsolationError

        m = self._metrics.get(metrics_id)
        if m is None:
            raise EnterpriseIsolationError(f"流程统计 {metrics_id!r} 不存在")
        if m.org_id != self._org_id:
            raise EnterpriseIsolationError(
                f"流程统计 {metrics_id!r} 归属组织 {m.org_id!r} 与当前组织 "
                f"{self._org_id!r} 不一致，禁止跨域访问"
            )
        return m


__all__ = ["WorkflowMetrics", "WorkflowMetricsService"]
