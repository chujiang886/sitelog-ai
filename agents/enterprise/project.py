"""Enterprise Operation Layer —— 项目管理模型（任务3，Phase 3.8.0）。

新增：``Project``，关联 ``Customer`` / ``Files`` / ``Workflow`` / ``Solution``。

隔离与耦合约束：
- 关联以**字符串外键**引用（``customer_id`` / ``file_ids`` / ``workflow_id`` /
  ``solution_id``），**绝不**反向依赖 engineering 模块内部类型，保持零耦合。
- 所有资源按 ``org_id`` 作用域过滤；跨域访问由 ``OrganizationService.assert_same_org``
  在调用层统一拦截。
- ``ProjectService`` 构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
- 本模块不持有批准/报价方法（红线②/③/④）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    safety_invariants_ok,
)


@dataclass
class Project:
    """项目：企业运营层聚合根（任务3）。

    以字符串外键关联客户/文件/工作流/方案，避免耦合工程内部类型。
    """

    project_id: str
    org_id: str
    name: str
    customer_id: str = ""           # 字符串外键 → 客户域
    file_ids: list = field(default_factory=list)   # 字符串外键列表 → FileAsset
    workflow_id: str = ""            # 字符串外键 → 工作流（如 WF-xxxx）
    solution_id: str = ""            # 字符串外键 → 方案（如 SOL-xxxx）
    status: str = "draft"            # draft / active / archived


class ProjectService:
    """项目服务（任务3）。"""

    def __init__(self, org_id: str) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 ProjectService（红线①/⑤）"
            )
        self._org_id = org_id
        self._projects: dict[str, Project] = {}

    def create_project(
        self,
        *,
        project_id: str,
        name: str,
        customer_id: str = "",
    ) -> Project:
        """在组织内创建项目（仅登记，关联以字符串外键填充）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下创建项目（红线①/⑤）"
            )
        project = Project(
            project_id=project_id,
            org_id=self._org_id,
            name=name,
            customer_id=customer_id,
        )
        self._projects[project_id] = project
        return project

    def attach_file(self, *, project_id: str, file_id: str) -> Project:
        """为项目附加文件（字符串外键；跨域访问抛隔离错误）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下附加文件（红线①/⑤）"
            )
        project = self._get_scoped(project_id)
        if file_id not in project.file_ids:
            project.file_ids.append(file_id)
        return project

    def link_workflow(self, *, project_id: str, workflow_id: str) -> Project:
        """关联工作流（字符串外键）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下关联工作流（红线①/⑤）"
            )
        project = self._get_scoped(project_id)
        project.workflow_id = workflow_id
        return project

    def link_solution(self, *, project_id: str, solution_id: str) -> Project:
        """关联方案（字符串外键）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下关联方案（红线①/⑤）"
            )
        project = self._get_scoped(project_id)
        project.solution_id = solution_id
        return project

    def get(self, *, project_id: str) -> Project:
        """按组织作用域读取项目（跨域访问抛隔离错误）。"""
        return self._get_scoped(project_id)

    def list_projects(self) -> list[Project]:
        """列出当前组织下全部项目（作用域过滤）。"""
        return [p for p in self._projects.values() if p.org_id == self._org_id]

    def _get_scoped(self, project_id: str) -> Project:
        from agents.enterprise.organization import EnterpriseIsolationError

        project = self._projects.get(project_id)
        if project is None:
            raise EnterpriseIsolationError(f"项目 {project_id!r} 不存在")
        if project.org_id != self._org_id:
            raise EnterpriseIsolationError(
                f"项目 {project_id!r} 归属组织 {project.org_id!r} 与当前组织 "
                f"{self._org_id!r} 不一致，禁止跨域访问"
            )
        return project


__all__ = ["Project", "ProjectService"]
