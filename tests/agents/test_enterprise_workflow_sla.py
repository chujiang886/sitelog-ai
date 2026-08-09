"""Enterprise Operation Layer —— 测试：SLA 管理（任务4，Phase 3.8.3）。

覆盖：
- SLA 登记（deadline / warning / status）。
- compute_sla_status 纯函数：OVERDUE / WARNING / ON_TRACK（按时间推导，无审批语义）。
- refresh_status 仅登记，不审批。
- 跨域访问抛 EnterpriseIsolationError。
- WorkflowSLAService 构造 fail-closed（红线①/⑤）。
- 不持有 approve / engineering_approved / quote / pricing / sign / authorize（红线②/③/④）。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import AuditActionCategory
from agents.enterprise.organization import EnterpriseIsolationError
from agents.enterprise.red_line import EnterpriseRedLineViolationError
from agents.enterprise.workflow_sla import (
    WorkflowSLA,
    WorkflowSLAService,
    WorkflowSLAStatus,
    compute_sla_status,
)


def test_create_sla() -> None:
    svc = WorkflowSLAService(org_id="org-1")
    sla = svc.create_sla(
        sla_id="S-1", deadline="2026-08-10", warning="2026-08-08",
        template_id="T-1", created_by="u1", created_at="t0",
    )
    assert isinstance(sla, WorkflowSLA)
    assert sla.deadline == "2026-08-10"
    assert sla.warning == "2026-08-08"
    assert sla.status == WorkflowSLAStatus.ON_TRACK
    assert sla.org_id == "org-1"


def test_compute_sla_status_pure_function() -> None:
    # now 在期限内
    assert compute_sla_status("2026-08-10", "2026-08-08", "2026-08-01") == WorkflowSLAStatus.ON_TRACK
    # now 超过 warning 但未到 deadline
    assert compute_sla_status("2026-08-10", "2026-08-08", "2026-08-09") == WorkflowSLAStatus.WARNING
    # now 超过 deadline
    assert compute_sla_status("2026-08-10", "2026-08-08", "2026-08-11") == WorkflowSLAStatus.OVERDUE
    # 无 deadline 视为不逾期
    assert compute_sla_status("", "2026-08-08", "2026-08-11") == WorkflowSLAStatus.ON_TRACK


def test_refresh_status_registration_only() -> None:
    svc = WorkflowSLAService(org_id="org-1")
    svc.create_sla(sla_id="S-1", deadline="2026-08-10", warning="2026-08-08")
    svc.refresh_status(sla_id="S-1", now="2026-08-11")
    assert svc.get(sla_id="S-1").status == WorkflowSLAStatus.OVERDUE
    svc.refresh_status(sla_id="S-1", now="2026-08-09")
    assert svc.get(sla_id="S-1").status == WorkflowSLAStatus.WARNING


def test_list_slas_with_filters() -> None:
    svc = WorkflowSLAService(org_id="org-1")
    svc.create_sla(sla_id="S-1", deadline="2026-08-10", warning="2026-08-08", workflow_id="W-1")
    svc.create_sla(sla_id="S-2", deadline="2026-08-10", warning="2026-08-08", workflow_id="W-2")
    svc.refresh_status(sla_id="S-2", now="2026-08-11")
    assert len(svc.list_slas()) == 2
    assert len(svc.list_slas(workflow_id="W-1")) == 1
    assert len(svc.list_slas(status=WorkflowSLAStatus.OVERDUE)) == 1


def test_cross_org_access_isolated() -> None:
    s1 = WorkflowSLAService(org_id="org-1")
    s2 = WorkflowSLAService(org_id="org-2")
    s1.create_sla(sla_id="S-1", deadline="2026-08-10", warning="2026-08-08")
    with pytest.raises(EnterpriseIsolationError):
        s2.get(sla_id="S-1")
    assert s2.list_slas() == []


def test_audit_records_workflow_event() -> None:
    from agents.enterprise.audit import AuditService

    audit = AuditService(org_id="org-1")
    svc = WorkflowSLAService(org_id="org-1", audit=audit)
    svc.create_sla(sla_id="S-1", deadline="2026-08-10", warning="2026-08-08", created_by="u1")
    recs = audit.query(category=AuditActionCategory.WORKFLOW_EVENT)
    assert any(r.action == "create_workflow_sla" for r in recs)


def test_service_construction_fail_closed(monkeypatch) -> None:
    from agents.enterprise.red_line import safety_invariants_ok

    monkeypatch.setattr("agents.enterprise.red_line.load_engineering_enabled", lambda: True)
    assert safety_invariants_ok() is False
    with pytest.raises(EnterpriseRedLineViolationError):
        WorkflowSLAService(org_id="org-1")
