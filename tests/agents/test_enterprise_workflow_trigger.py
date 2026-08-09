"""Enterprise Operation Layer —— 测试：自动触发规则（任务3，Phase 3.8.3）。

覆盖（最高红线③：只触发流程，不触发审批）：
- 三类事件类型（project_created / file_uploaded / task_completed）均可注册与匹配。
- evaluate 只读匹配，不执行写动作。
- fire 仅登记 pending 触发事件 + 如实写审计（WORKFLOW_EVENT），**不**代审批/确认/签署。
- 触发事件 status 恒为 pending，系统**不**提供任何 approve / confirm / auto_approve /
  trigger_approval / request_approval 入口（结构上被 mixin 拦截，红线③）。
- 跨域访问抛 EnterpriseIsolationError。
- WorkflowTriggerService 构造 fail-closed（红线①/⑤）。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import AuditActionCategory, AuditActorKind
from agents.enterprise.organization import EnterpriseIsolationError
from agents.enterprise.red_line import EnterpriseRedLineViolationError
from agents.enterprise.workflow_trigger import (
    WorkflowTriggerEvent,
    WorkflowTriggerRule,
    WorkflowTriggerService,
    WorkflowTriggerEventType,
)


def _register_three(svc: WorkflowTriggerService) -> None:
    svc.register_rule(rule_id="R-P", template_id="T-P", event_type=WorkflowTriggerEventType.PROJECT_CREATED)
    svc.register_rule(rule_id="R-F", template_id="T-F", event_type=WorkflowTriggerEventType.FILE_UPLOADED)
    svc.register_rule(rule_id="R-T", template_id="T-T", event_type=WorkflowTriggerEventType.TASK_COMPLETED)


def test_register_and_evaluate_event_types() -> None:
    svc = WorkflowTriggerService(org_id="org-1")
    _register_three(svc)
    matched = svc.evaluate(event_type=WorkflowTriggerEventType.PROJECT_CREATED)
    assert [r.rule_id for r in matched] == ["R-P"]
    assert svc.evaluate(event_type="file_uploaded")[0].rule_id == "R-F"
    assert svc.evaluate(event_type="task_completed")[0].rule_id == "R-T"


def test_fire_only_triggers_pending_workflow_not_approval() -> None:
    svc = WorkflowTriggerService(org_id="org-1")
    _register_three(svc)
    events = svc.fire(event_type=WorkflowTriggerEventType.PROJECT_CREATED, event_id="E1", fired_at="t0")
    assert len(events) == 1
    ev = events[0]
    assert isinstance(ev, WorkflowTriggerEvent)
    assert ev.template_id == "T-P"
    assert ev.event_type == WorkflowTriggerEventType.PROJECT_CREATED
    # 红线③：触发事件状态恒为 pending，绝不自动审批
    assert ev.status == "pending"
    # 事件可被列出，且全部 pending
    listed = svc.list_events()
    assert all(e.status == "pending" for e in listed)


def test_fire_records_audit_as_workflow_event_not_human_approval() -> None:
    from agents.enterprise.audit import AuditService

    audit = AuditService(org_id="org-1")
    svc = WorkflowTriggerService(org_id="org-1", audit=audit)
    _register_three(svc)
    svc.fire(event_type=WorkflowTriggerEventType.TASK_COMPLETED, event_id="E1", fired_at="t0")
    recs = audit.query(category=AuditActionCategory.WORKFLOW_EVENT)
    fire_recs = [r for r in recs if r.action == "workflow_triggered_pending"]
    assert len(fire_recs) == 1
    # actor_kind 必须是 SYSTEM（自动化触发），绝不是 human approval
    assert fire_recs[0].actor_kind == AuditActorKind.SYSTEM
    assert "pending" in fire_recs[0].detail


def test_disabled_rule_not_fired() -> None:
    svc = WorkflowTriggerService(org_id="org-1")
    svc.register_rule(
        rule_id="R-X", template_id="T-X", event_type=WorkflowTriggerEventType.PROJECT_CREATED,
        enabled=False,
    )
    assert svc.fire(event_type=WorkflowTriggerEventType.PROJECT_CREATED, event_id="E1") == []


def test_forbidden_approval_methods_blocked_red_line_3() -> None:
    svc = WorkflowTriggerService(org_id="org-1")
    _register_three(svc)
    svc.fire(event_type=WorkflowTriggerEventType.PROJECT_CREATED, event_id="E1")
    # 红线③：以下方法在结构上不可达（触发流程绝不触发审批）
    for name in (
        "approve", "engineering_approved", "sign", "authorize",
        "auto_approve", "auto_sign_off", "confirm", "trigger_approval",
        "request_approval",
    ):
        with pytest.raises(EnterpriseRedLineViolationError):
            getattr(svc, name)()  # type: ignore[attr-defined]


def test_cross_org_access_isolated() -> None:
    s1 = WorkflowTriggerService(org_id="org-1")
    s2 = WorkflowTriggerService(org_id="org-2")
    s1.register_rule(rule_id="R-1", template_id="T-1", event_type=WorkflowTriggerEventType.PROJECT_CREATED)
    with pytest.raises(EnterpriseIsolationError):
        s2.get_rule(rule_id="R-1")
    assert s2.list_rules() == []


def test_service_construction_fail_closed(monkeypatch) -> None:
    from agents.enterprise.red_line import safety_invariants_ok

    monkeypatch.setattr("agents.enterprise.red_line.load_engineering_enabled", lambda: True)
    assert safety_invariants_ok() is False
    with pytest.raises(EnterpriseRedLineViolationError):
        WorkflowTriggerService(org_id="org-1")
