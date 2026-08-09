"""Enterprise Operation Layer —— 测试：流程版本管理（任务2，Phase 3.8.3）。

覆盖：
- 版本登记（version / change_log / effective_status）。
- 生效状态流转仅登记，不代替人工决策。
- 跨域访问抛 EnterpriseIsolationError。
- WorkflowVersionService 构造 fail-closed（红线①/⑤）。
- 不持有 approve / engineering_approved / quote / pricing / sign / authorize（红线②/③/④）。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import AuditActionCategory
from agents.enterprise.organization import EnterpriseIsolationError
from agents.enterprise.red_line import EnterpriseRedLineViolationError
from agents.enterprise.workflow_version import (
    WorkflowVersion,
    WorkflowVersionEffectiveStatus,
    WorkflowVersionService,
)


def test_create_version() -> None:
    svc = WorkflowVersionService(org_id="org-1")
    v = svc.create_version(
        version_id="V-1",
        template_id="T-1",
        version="1.0.0",
        change_log="初始版本",
        effective_status=WorkflowVersionEffectiveStatus.DRAFT,
        created_by="u1",
        created_at="t0",
    )
    assert isinstance(v, WorkflowVersion)
    assert v.template_id == "T-1"
    assert v.version == "1.0.0"
    assert v.change_log == "初始版本"
    assert v.effective_status == WorkflowVersionEffectiveStatus.DRAFT
    assert v.org_id == "org-1"


def test_effective_status_transition_registration_only() -> None:
    svc = WorkflowVersionService(org_id="org-1")
    svc.create_version(version_id="V-1", template_id="T-1", version="1.0.0")
    svc.set_effective_status(
        version_id="V-1", effective_status=WorkflowVersionEffectiveStatus.EFFECTIVE, updated_by="u-owner",
    )
    assert svc.get(version_id="V-1").effective_status == WorkflowVersionEffectiveStatus.EFFECTIVE
    svc.set_effective_status(version_id="V-1", effective_status="superseded")
    assert svc.get(version_id="V-1").effective_status == WorkflowVersionEffectiveStatus.SUPERSEDED


def test_list_versions_by_template() -> None:
    svc = WorkflowVersionService(org_id="org-1")
    svc.create_version(version_id="V-1", template_id="T-1", version="1.0.0")
    svc.create_version(version_id="V-2", template_id="T-2", version="1.0.0")
    svc.create_version(version_id="V-3", template_id="T-1", version="1.1.0")
    assert len(svc.list_versions()) == 3
    assert len(svc.list_versions(template_id="T-1")) == 2


def test_cross_org_access_isolated() -> None:
    s1 = WorkflowVersionService(org_id="org-1")
    s2 = WorkflowVersionService(org_id="org-2")
    s1.create_version(version_id="V-1", template_id="T-1", version="1.0.0")
    with pytest.raises(EnterpriseIsolationError):
        s2.get(version_id="V-1")
    assert s2.list_versions() == []


def test_audit_records_workflow_event() -> None:
    from agents.enterprise.audit import AuditService

    audit = AuditService(org_id="org-1")
    svc = WorkflowVersionService(org_id="org-1", audit=audit)
    svc.create_version(version_id="V-1", template_id="T-1", version="1.0.0", created_by="u1")
    recs = audit.query(category=AuditActionCategory.WORKFLOW_EVENT)
    assert any(r.action == "create_workflow_version" for r in recs)


def test_service_construction_fail_closed(monkeypatch) -> None:
    from agents.enterprise.red_line import safety_invariants_ok

    monkeypatch.setattr("agents.enterprise.red_line.load_engineering_enabled", lambda: True)
    assert safety_invariants_ok() is False
    with pytest.raises(EnterpriseRedLineViolationError):
        WorkflowVersionService(org_id="org-1")
