"""Enterprise Operation Layer —— 工作流模板（任务1，Phase 3.8.3）。

新增：``WorkflowTemplate``，支持门窗设计流程 / 售后流程 / 项目流程。

字段严格对应指令：template_id / name / type / stages / version / status / created_by，
并要求组织隔离（org_id）。

隔离与红线约束（fail-closed，复用 3.8.0~3.8.2 基座）：
- 所有模板按 ``org_id`` 作用域过滤；跨域访问抛 ``EnterpriseIsolationError``。
- ``WorkflowTemplateService`` 构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
- 本模块不持有批准/报价/审批方法（红线②/③/④）；模板只做登记，不代替人工决策（红线⑥）。
- 可选联动 ``AuditService.record_workflow_event`` 如实标注动作发起方（actor 真实）。

注意：``stages`` 仅描述流程阶段定义（如 ["需求确认","方案设计","审核","交付"]），
**不**包含任何审批结论或工程参数；审批节点须由真实人工驱动（见 task_workflow.py）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from agents.enterprise.audit import AuditService
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    safety_invariants_ok,
)


class WorkflowTemplateType(str, Enum):
    """工作流模板类型（门窗设计 / 售后 / 项目）。"""

    DOOR_WINDOW_DESIGN = "door_window_design"
    AFTER_SALES = "after_sales"
    PROJECT = "project"


class WorkflowTemplateStatus(str, Enum):
    """工作流模板状态。"""

    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


@dataclass
class WorkflowTemplate:
    """工作流模板（任务1）。

    字段严格对应指令：template_id / name / type / stages / version / status / created_by。
    并要求组织隔离（org_id）。

    ``stages`` 仅描述流程阶段定义（有序列表），例如：
    ["需求确认", "方案设计", "人工审核", "交付"]；
    模板本身**不**携带任何审批结论或工程参数。
    """

    template_id: str
    org_id: str
    name: str
    type: WorkflowTemplateType
    stages: list = field(default_factory=list)
    version: str = "1.0.0"
    status: WorkflowTemplateStatus = WorkflowTemplateStatus.DRAFT
    created_by: str = ""
    created_at: str = ""


class WorkflowTemplateService:
    """工作流模板服务（任务1）。

    仅做模板登记与读取；跨域访问抛 ``EnterpriseIsolationError``；
    写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
    本服务**不**持有任何 approve / engineering_approved / quote / pricing / sign /
    authorize 方法（红线②/③/④），模板的生效与否由真实人工在外部决定。
    """

    def __init__(self, org_id: str, audit: "AuditService | None" = None) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "WorkflowTemplateService（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._templates: dict[str, WorkflowTemplate] = {}

    def create_template(
        self,
        *,
        template_id: str,
        name: str,
        type: "WorkflowTemplateType | str",
        stages: list | None = None,
        version: str = "1.0.0",
        status: "WorkflowTemplateStatus | str" = WorkflowTemplateStatus.DRAFT,
        created_by: str = "",
        created_at: str = "",
    ) -> WorkflowTemplate:
        """在组织内创建（登记）工作流模板（仅登记；creator 为真实发起方）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下创建工作流模板（红线①/⑤）"
            )
        tpl_type = type if isinstance(type, WorkflowTemplateType) else WorkflowTemplateType(type)
        tpl_status = (
            status if isinstance(status, WorkflowTemplateStatus) else WorkflowTemplateStatus(status)
        )
        tpl = WorkflowTemplate(
            template_id=template_id,
            org_id=self._org_id,
            name=name,
            type=tpl_type,
            stages=list(stages or []),
            version=version,
            status=tpl_status,
            created_by=created_by,
            created_at=created_at,
        )
        self._templates[template_id] = tpl
        if self._audit is not None:
            self._audit.record_workflow_event(
                record_id=f"tpl-create-{template_id}",
                actor_id=created_by or "system",
                action="create_workflow_template",
                target=template_id,
                detail=f"type={tpl_type.value};version={version};status={tpl_status.value}",
                ts=created_at,
            )
        return tpl

    def update_status(
        self,
        *,
        template_id: str,
        status: "WorkflowTemplateStatus | str",
        updated_by: str = "",
        ts: str = "",
    ) -> WorkflowTemplate:
        """更新模板状态（仅登记流转，不代替人工决策；红线⑥）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下变更模板状态（红线①/⑤）"
            )
        tpl = self._get_scoped(template_id)
        new_status = (
            status if isinstance(status, WorkflowTemplateStatus) else WorkflowTemplateStatus(status)
        )
        tpl.status = new_status
        if self._audit is not None:
            self._audit.record_workflow_event(
                record_id=f"tpl-status-{template_id}-{new_status.value}",
                actor_id=updated_by or "system",
                action="update_workflow_template_status",
                target=template_id,
                detail=f"status={new_status.value}",
                ts=ts,
            )
        return tpl

    def get(self, *, template_id: str) -> WorkflowTemplate:
        """按组织作用域读取模板（跨域访问抛隔离错误）。"""
        return self._get_scoped(template_id)

    def list_templates(
        self,
        *,
        type: "WorkflowTemplateType | str | None" = None,
        status: "WorkflowTemplateStatus | str | None" = None,
    ) -> list[WorkflowTemplate]:
        """列出当前组织下模板（可按 type / status 过滤）。"""
        out = [t for t in self._templates.values() if t.org_id == self._org_id]
        if type is not None:
            want = type if isinstance(type, WorkflowTemplateType) else WorkflowTemplateType(type)
            out = [t for t in out if t.type == want]
        if status is not None:
            want = (
                status
                if isinstance(status, WorkflowTemplateStatus)
                else WorkflowTemplateStatus(status)
            )
            out = [t for t in out if t.status == want]
        return out

    def _get_scoped(self, template_id: str) -> WorkflowTemplate:
        from agents.enterprise.organization import EnterpriseIsolationError

        tpl = self._templates.get(template_id)
        if tpl is None:
            raise EnterpriseIsolationError(f"工作流模板 {template_id!r} 不存在")
        if tpl.org_id != self._org_id:
            raise EnterpriseIsolationError(
                f"工作流模板 {template_id!r} 归属组织 {tpl.org_id!r} 与当前组织 "
                f"{self._org_id!r} 不一致，禁止跨域访问"
            )
        return tpl


__all__ = [
    "WorkflowTemplateType",
    "WorkflowTemplateStatus",
    "WorkflowTemplate",
    "WorkflowTemplateService",
]
