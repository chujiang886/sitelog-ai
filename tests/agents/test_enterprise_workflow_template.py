"""Enterprise Operation Layer —— 测试：工作流模板（任务1，Phase 3.8.3）。

覆盖：
- 三类模板类型（门窗设计 / 售后 / 项目）均可创建。
- 字段严格对应指令：template_id / name / type / stages / version / status / created_by（+ org_id）。
- 状态流转仅登记，不代替人工决策。
- 跨域访问抛 EnterpriseIsolationError。
- WorkflowTemplateService 构造 fail-closed（红线①/⑤）。
- 不持有 approve / engineering_approved / quote / pricing / sign / authorize（红线②/③/④）。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import AuditActionCategory, AuditActorKind
from agents.enterprise.organization import EnterpriseIsolationError
from agents.enterprise.red_line import EnterpriseRedLineViolationError
from agents.enterprise.workflow_template import (
    WorkflowTemplate,
    WorkflowTemplateService,
    WorkflowTemplateStatus,
    WorkflowTemplateType,
)


def test_create_door_window_design_template() -> None:
    svc = WorkflowTemplateService(org_id="org-1")
    tpl = svc.create_template(
        template_id="T-DW-1",
        name="门窗设计流程",
        type=WorkflowTemplateType.DOOR_WINDOW_DESIGN,
        stages=["需求确认", "方案设计", "人工审核", "交付"],
        version="1.0.0",
        created_by="u-arch",
        created_at="t0",
    )
    assert isinstance(tpl, WorkflowTemplate)
    assert tpl.template_id == "T-DW-1"
    assert tpl.name == "门窗设计流程"
    assert tpl.type == WorkflowTemplateType.DOOR_WINDOW_DESIGN
    assert tpl.stages == ["需求确认", "方案设计", "人工审核", "交付"]
    assert tpl.version == "1.0.0"
    assert tpl.status == WorkflowTemplateStatus.DRAFT
    assert tpl.created_by == "u-arch"
    assert tpl.org_id == "org-1"


def test_create_after_sales_and_project_templates() -> None:
    svc = WorkflowTemplateService(org_id="org-1")
    after = svc.create_template(
        template_id="T-AS-1", name="售后流程", type=WorkflowTemplateType.AFTER_SALES,
    )
    proj = svc.create_template(
        template_id="T-PR-1", name="项目流程", type=WorkflowTemplateType.PROJECT,
    )
    assert after.type == WorkflowTemplateType.AFTER_SALES
    assert proj.type == WorkflowTemplateType.PROJECT


def test_type_accepts_string() -> None:
    svc = WorkflowTemplateService(org_id="org-1")
    tpl = svc.create_template(
        template_id="T-1", name="x", type="project",
    )
    assert tpl.type == WorkflowTemplateType.PROJECT


def test_status_transition_is_registration_only() -> None:
    svc = WorkflowTemplateService(org_id="org-1")
    svc.create_template(template_id="T-1", name="x", type=WorkflowTemplateType.PROJECT)
    svc.update_status(
        template_id="T-1", status=WorkflowTemplateStatus.ACTIVE, updated_by="u-owner", ts="t1",
    )
    assert svc.get(template_id="T-1").status == WorkflowTemplateStatus.ACTIVE
    # 可归档
    svc.update_status(template_id="T-1", status="archived")
    assert svc.get(template_id="T-1").status == WorkflowTemplateStatus.ARCHIVED


def test_list_templates_with_filters() -> None:
    svc = WorkflowTemplateService(org_id="org-1")
    svc.create_template(template_id="A", name="a", type=WorkflowTemplateType.PROJECT)
    svc.create_template(template_id="B", name="b", type=WorkflowTemplateType.AFTER_SALES)
    assert len(svc.list_templates()) == 2
    assert len(svc.list_templates(type=WorkflowTemplateType.PROJECT)) == 1
    assert len(svc.list_templates(status=WorkflowTemplateStatus.DRAFT)) == 2


def test_cross_org_access_isolated() -> None:
    svc1 = WorkflowTemplateService(org_id="org-1")
    svc2 = WorkflowTemplateService(org_id="org-2")
    svc1.create_template(template_id="T-1", name="x", type=WorkflowTemplateType.PROJECT)
    with pytest.raises(EnterpriseIsolationError):
        svc2.get(template_id="T-1")
    # 列表不泄漏跨域数据
    assert svc2.list_templates() == []


def test_audit_records_workflow_event() -> None:
    from agents.enterprise.audit import AuditService

    audit = AuditService(org_id="org-1")
    svc = WorkflowTemplateService(org_id="org-1", audit=audit)
    svc.create_template(template_id="T-1", name="x", type=WorkflowTemplateType.PROJECT, created_by="u1")
    recs = audit.query(category=AuditActionCategory.WORKFLOW_EVENT)
    assert any(r.action == "create_workflow_template" for r in recs)


def test_service_construction_fail_closed(monkeypatch) -> None:
    from agents.enterprise.red_line import safety_invariants_ok

    monkeypatch.setattr("agents.enterprise.red_line.load_engineering_enabled", lambda: True)
    assert safety_invariants_ok() is False
    with pytest.raises(EnterpriseRedLineViolationError):
        WorkflowTemplateService(org_id="org-1")


def test_no_forbidden_methods() -> None:
    svc = WorkflowTemplateService(org_id="org-1")
    for name in ("approve", "engineering_approved", "quote", "pricing", "sign", "authorize"):
        assert not hasattr(svc, name) or name in (
            # 允许 dataclass/enum 等无关属性；本服务不定义这些动作
            "_FORBIDDEN",
        )
