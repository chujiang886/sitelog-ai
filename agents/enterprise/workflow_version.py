"""Enterprise Operation Layer —— 流程版本管理（任务2，Phase 3.8.3）。

新增：``WorkflowVersion``，关联 ``WorkflowTemplate``，支持版本 / 变更记录 / 生效状态。

隔离与红线约束（fail-closed，复用 3.8.0~3.8.2 基座）：
- 所有版本按 ``org_id`` 作用域过滤；跨域访问抛 ``EnterpriseIsolationError``。
- ``WorkflowVersionService`` 构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
- 本模块不持有批准/报价/审批方法（红线②/③/④）；版本生效与否由真实人工在外部决定（红线⑥）。
- 可选联动 ``AuditService.record_workflow_event`` 如实标注动作发起方（actor 真实）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from agents.enterprise.audit import AuditService
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    safety_invariants_ok,
)


class WorkflowVersionEffectiveStatus(str, Enum):
    """版本生效状态。

    DRAFT：草稿；EFFECTIVE：生效中（由真实人工置位）；SUPERSEDED：已被新版本取代；
    RETIRED：已停用。所有状态仅为登记，系统**不**自动批准任何工程参数。
    """

    DRAFT = "draft"
    EFFECTIVE = "effective"
    SUPERSEDED = "superseded"
    RETIRED = "retired"


@dataclass
class WorkflowVersion:
    """流程版本（任务2）。

    关联模板（template_id）；记录版本号、变更记录与生效状态。仅元数据，不携带审批结论。
    """

    version_id: str
    org_id: str
    template_id: str
    version: str
    change_log: str = ""
    effective_status: WorkflowVersionEffectiveStatus = WorkflowVersionEffectiveStatus.DRAFT
    created_by: str = ""
    created_at: str = ""


class WorkflowVersionService:
    """流程版本服务（任务2）。

    仅做版本登记与读取；跨域访问抛 ``EnterpriseIsolationError``；
    写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
    本服务**不**持有任何 approve / engineering_approved / quote / pricing / sign /
    authorize 方法（红线②/③/④）；版本生效状态由真实人工在外部决定（红线⑥）。
    """

    def __init__(self, org_id: str, audit: "AuditService | None" = None) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "WorkflowVersionService（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._versions: dict[str, WorkflowVersion] = {}

    def create_version(
        self,
        *,
        version_id: str,
        template_id: str,
        version: str,
        change_log: str = "",
        effective_status: "WorkflowVersionEffectiveStatus | str" = (
            WorkflowVersionEffectiveStatus.DRAFT
        ),
        created_by: str = "",
        created_at: str = "",
    ) -> WorkflowVersion:
        """在组织内登记一个模板版本（仅登记；creator 为真实发起方）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下登记流程版本（红线①/⑤）"
            )
        eff = (
            effective_status
            if isinstance(effective_status, WorkflowVersionEffectiveStatus)
            else WorkflowVersionEffectiveStatus(effective_status)
        )
        ver = WorkflowVersion(
            version_id=version_id,
            org_id=self._org_id,
            template_id=template_id,
            version=version,
            change_log=change_log,
            effective_status=eff,
            created_by=created_by,
            created_at=created_at,
        )
        self._versions[version_id] = ver
        if self._audit is not None:
            self._audit.record_workflow_event(
                record_id=f"ver-create-{version_id}",
                actor_id=created_by or "system",
                action="create_workflow_version",
                target=template_id,
                detail=f"version={version};effective={eff.value}",
                ts=created_at,
            )
        return ver

    def set_effective_status(
        self,
        *,
        version_id: str,
        effective_status: "WorkflowVersionEffectiveStatus | str",
        updated_by: str = "",
        ts: str = "",
    ) -> WorkflowVersion:
        """更新版本生效状态（仅登记流转，不代替人工决策；红线⑥）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下变更版本生效状态（红线①/⑤）"
            )
        ver = self._get_scoped(version_id)
        eff = (
            effective_status
            if isinstance(effective_status, WorkflowVersionEffectiveStatus)
            else WorkflowVersionEffectiveStatus(effective_status)
        )
        ver.effective_status = eff
        if self._audit is not None:
            self._audit.record_workflow_event(
                record_id=f"ver-status-{version_id}-{eff.value}",
                actor_id=updated_by or "system",
                action="set_workflow_version_effective_status",
                target=ver.template_id,
                detail=f"version={ver.version};effective={eff.value}",
                ts=ts,
            )
        return ver

    def get(self, *, version_id: str) -> WorkflowVersion:
        """按组织作用域读取版本（跨域访问抛隔离错误）。"""
        return self._get_scoped(version_id)

    def list_versions(self, *, template_id: str = "") -> list[WorkflowVersion]:
        """列出当前组织下版本（可按 template 过滤）。"""
        out = [v for v in self._versions.values() if v.org_id == self._org_id]
        if template_id:
            out = [v for v in out if v.template_id == template_id]
        return out

    def _get_scoped(self, version_id: str) -> WorkflowVersion:
        from agents.enterprise.organization import EnterpriseIsolationError

        ver = self._versions.get(version_id)
        if ver is None:
            raise EnterpriseIsolationError(f"流程版本 {version_id!r} 不存在")
        if ver.org_id != self._org_id:
            raise EnterpriseIsolationError(
                f"流程版本 {version_id!r} 归属组织 {ver.org_id!r} 与当前组织 "
                f"{self._org_id!r} 不一致，禁止跨域访问"
            )
        return ver


__all__ = [
    "WorkflowVersionEffectiveStatus",
    "WorkflowVersion",
    "WorkflowVersionService",
]
