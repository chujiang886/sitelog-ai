"""Enterprise Operation Layer —— 测试3：项目管理模型（任务3，Phase 3.8.0）。

覆盖：
- Project 以字符串外键关联 Customer / Files / Workflow / Solution（零耦合）。
- attach_file / link_workflow / link_solution。
- 跨域访问（get）与未知 id 抛 EnterpriseIsolationError。
- list_projects 按 org_id 作用域过滤。
"""

from __future__ import annotations

import pytest

from agents.enterprise.organization import EnterpriseIsolationError
from agents.enterprise.project import Project, ProjectService


def test_create_project_with_customer_fk() -> None:
    svc = ProjectService(org_id="org-1")
    p = svc.create_project(project_id="p1", name="Villa", customer_id="cust-1")
    assert p.org_id == "org-1"
    assert p.customer_id == "cust-1"
    assert p.status == "draft"


def test_attach_file_and_link_workflow_solution() -> None:
    svc = ProjectService(org_id="org-1")
    svc.create_project(project_id="p1", name="Villa")
    svc.attach_file(project_id="p1", file_id="f1")
    svc.attach_file(project_id="p1", file_id="f2")
    svc.link_workflow(project_id="p1", workflow_id="WF-1")
    svc.link_solution(project_id="p1", solution_id="SOL-1")
    p = svc.get(project_id="p1")
    assert p.file_ids == ["f1", "f2"]
    assert p.workflow_id == "WF-1"
    assert p.solution_id == "SOL-1"


def test_attach_file_is_idempotent() -> None:
    svc = ProjectService(org_id="org-1")
    svc.create_project(project_id="p1", name="Villa")
    svc.attach_file(project_id="p1", file_id="f1")
    svc.attach_file(project_id="p1", file_id="f1")
    assert svc.get(project_id="p1").file_ids == ["f1"]


def test_list_projects_scoped_to_org() -> None:
    svc = ProjectService(org_id="org-1")
    svc.create_project(project_id="p1", name="A")
    # 注入一个其它 org 的项目以验证作用域过滤
    svc._projects["pX"] = Project(project_id="pX", org_id="org-2", name="B")
    names = {p.name for p in svc.list_projects()}
    assert names == {"A"}


def test_get_cross_org_raises_isolation() -> None:
    svc = ProjectService(org_id="org-1")
    svc._projects["pX"] = Project(project_id="pX", org_id="org-2", name="B")
    with pytest.raises(EnterpriseIsolationError):
        svc.get(project_id="pX")


def test_get_unknown_raises_isolation() -> None:
    svc = ProjectService(org_id="org-1")
    with pytest.raises(EnterpriseIsolationError):
        svc.get(project_id="nope")
