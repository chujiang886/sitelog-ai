"""Enterprise Operation Layer —— SLA 管理（任务4，Phase 3.8.3）。

新增：``WorkflowSLA``，记录 deadline / warning / status。

隔离与红线约束（fail-closed，复用 3.8.0~3.8.2 基座）：
- 所有 SLA 按 ``org_id`` 作用域过滤；跨域访问抛 ``EnterpriseIsolationError``。
- ``WorkflowSLAService`` 构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
- 本模块不持有批准/报价/审批方法（红线②/③/④）；SLA 的 status 为按时间计算的登记值，
  不含任何审批结论（红线⑥）。
- 可选联动 ``AuditService.record_workflow_event`` 如实标注动作发起方（actor 真实）。

状态计算（纯函数，无副作用、无审批语义）：
- ``status`` 由 ``_compute_status(deadline, warning, now)`` 依据当前时间推导：
  ``OVERDUE``（超过 deadline）/ ``WARNING``（超过 warning 但未到 deadline）/
  ``ON_TRACK``（均在期限内）。status **不**因任何自动逻辑变为 approved。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from agents.enterprise.audit import AuditService
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    safety_invariants_ok,
)


class WorkflowSLAStatus(str, Enum):
    """SLA 状态（按时间推导，不含审批语义）。"""

    ON_TRACK = "on_track"
    WARNING = "warning"
    OVERDUE = "overdue"


@dataclass
class WorkflowSLA:
    """工作流 SLA（任务4）。

    记录 deadline / warning / status。status 为按当前时间推导的登记值，不含审批结论。
    """

    sla_id: str
    org_id: str
    template_id: str = ""            # 关联模板（可选）
    workflow_id: str = ""            # 关联具体流程实例（可选）
    deadline: str = ""               # 截止时间（ISO 字符串）
    warning: str = ""                # 预警时间（ISO 字符串）
    status: WorkflowSLAStatus = WorkflowSLAStatus.ON_TRACK
    created_by: str = ""
    created_at: str = ""


def _iso_lt(a: str, b: str) -> bool:
    """两个 ISO 时间字符串比较（a < b）；空串视为最小。"""
    if not a:
        return True
    if not b:
        return False
    return a < b


def compute_sla_status(deadline: str, warning: str, now: str) -> WorkflowSLAStatus:
    """纯函数：依据 deadline / warning / now 推导 SLA 状态（无副作用、无审批语义）。

    warning 是 deadline 之前的预警，仅当 deadline 存在时才有意义：
    - deadline 存在且 now >= deadline → OVERDUE；
    - deadline 存在且 warning 存在且 now >= warning → WARNING；
    - 其余（含无 deadline 的退化配置）→ ON_TRACK。
    """
    if deadline and not _iso_lt(now, deadline):
        return WorkflowSLAStatus.OVERDUE
    if deadline and warning and not _iso_lt(now, warning):
        return WorkflowSLAStatus.WARNING
    return WorkflowSLAStatus.ON_TRACK


class WorkflowSLAService:
    """SLA 服务（任务4）。

    仅做 SLA 登记与状态计算；跨域访问抛 ``EnterpriseIsolationError``；
    写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
    本服务**不**持有任何 approve / engineering_approved / quote / pricing / sign /
    authorize 方法（红线②/③/④）。
    """

    def __init__(self, org_id: str, audit: "AuditService | None" = None) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "WorkflowSLAService（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._slas: dict[str, WorkflowSLA] = {}

    def create_sla(
        self,
        *,
        sla_id: str,
        deadline: str,
        warning: str = "",
        template_id: str = "",
        workflow_id: str = "",
        created_by: str = "",
        created_at: str = "",
    ) -> WorkflowSLA:
        """在组织内登记 SLA（仅登记 deadline / warning，status 初始 on_track）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下登记 SLA（红线①/⑤）"
            )
        sla = WorkflowSLA(
            sla_id=sla_id,
            org_id=self._org_id,
            template_id=template_id,
            workflow_id=workflow_id,
            deadline=deadline,
            warning=warning,
            status=WorkflowSLAStatus.ON_TRACK,
            created_by=created_by,
            created_at=created_at,
        )
        self._slas[sla_id] = sla
        if self._audit is not None:
            self._audit.record_workflow_event(
                record_id=f"sla-create-{sla_id}",
                actor_id=created_by or "system",
                action="create_workflow_sla",
                target=(workflow_id or template_id),
                detail=f"deadline={deadline};warning={warning}",
                ts=created_at,
            )
        return sla

    def refresh_status(self, *, sla_id: str, now: str) -> WorkflowSLA:
        """按当前时间重算 SLA 状态（纯登记，不审批）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下刷新 SLA 状态（红线①/⑤）"
            )
        sla = self._get_scoped(sla_id)
        sla.status = compute_sla_status(sla.deadline, sla.warning, now)
        return sla

    def get(self, *, sla_id: str) -> WorkflowSLA:
        """按组织作用域读取 SLA（跨域访问抛隔离错误）。"""
        return self._get_scoped(sla_id)

    def list_slas(self, *, workflow_id: str = "", status: "WorkflowSLAStatus | str | None" = None) -> list[
        WorkflowSLA
    ]:
        """列出当前组织下 SLA（可按 workflow / status 过滤）。"""
        out = [s for s in self._slas.values() if s.org_id == self._org_id]
        if workflow_id:
            out = [s for s in out if s.workflow_id == workflow_id]
        if status is not None:
            want = status if isinstance(status, WorkflowSLAStatus) else WorkflowSLAStatus(status)
            out = [s for s in out if s.status == want]
        return out

    def _get_scoped(self, sla_id: str) -> WorkflowSLA:
        from agents.enterprise.organization import EnterpriseIsolationError

        sla = self._slas.get(sla_id)
        if sla is None:
            raise EnterpriseIsolationError(f"工作流 SLA {sla_id!r} 不存在")
        if sla.org_id != self._org_id:
            raise EnterpriseIsolationError(
                f"工作流 SLA {sla_id!r} 归属组织 {sla.org_id!r} 与当前组织 "
                f"{self._org_id!r} 不一致，禁止跨域访问"
            )
        return sla


__all__ = [
    "WorkflowSLAStatus",
    "WorkflowSLA",
    "compute_sla_status",
    "WorkflowSLAService",
]
