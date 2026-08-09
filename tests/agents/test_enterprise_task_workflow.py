"""Enterprise Operation Layer —— 测试：任务工作流（任务4，Phase 3.8.2）。

覆盖：
- 状态机 created -> assigned -> processing -> waiting_review -> completed。
- 非法跃迁被拒（EnterpriseRedLineViolationError）。
- 人工审核节点必须 human 驱动：record_review_result 须传 reviewer_id（红线⑥）：
  不传 / 空 → 拒；approved=True -> completed，approved=False -> processing（打回）。
- 不提供 approve 方法（mixin 拦截 approve / engineering_approved / sign / authorize）。
- 审核结论如实登记，actor_kind=USER（actor 真实，红线⑥）。
- TaskWorkflowService 构造 fail-closed（红线①/⑤）。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import AuditActionCategory, AuditActorKind
from agents.enterprise.red_line import EnterpriseRedLineViolationError
from agents.enterprise.task_workflow import (
    TaskWorkflow,
    TaskWorkflowService,
    TaskWorkflowStatus,
)


def _build_to_review(svc: TaskWorkflowService, wf_id: str = "W1") -> None:
    svc.create_workflow(workflow_id=wf_id, task_id="T1", created_at="t0")
    svc.assign(workflow_id=wf_id, assignee_id="u-ops")
    svc.start_processing(workflow_id=wf_id)
    svc.submit_for_review(workflow_id=wf_id, submitted_by="u-ops")


def test_state_machine_happy_path() -> None:
    svc = TaskWorkflowService(org_id="org-1")
    _build_to_review(svc)
    assert svc.get(workflow_id="W1").status == TaskWorkflowStatus.WAITING_REVIEW
    svc.record_review_result(workflow_id="W1", reviewer_id="u-reviewer", approved=True,
                             review_note="ok", ts="t1")
    wf = svc.get(workflow_id="W1")
    assert wf.status == TaskWorkflowStatus.COMPLETED
    assert wf.reviewer_id == "u-reviewer"
    assert wf.review_result == "approved"


def test_rejected_review_returns_to_processing() -> None:
    svc = TaskWorkflowService(org_id="org-1")
    _build_to_review(svc)
    svc.record_review_result(workflow_id="W1", reviewer_id="u-reviewer", approved=False,
                             review_note="需修改", ts="t1")
    wf = svc.get(workflow_id="W1")
    assert wf.status == TaskWorkflowStatus.PROCESSING
    assert wf.review_result == "rejected"
    # 可再次提交并复核通过
    svc.submit_for_review(workflow_id="W1", submitted_by="u-ops")
    svc.record_review_result(workflow_id="W1", reviewer_id="u-reviewer", approved=True)
    assert svc.get(workflow_id="W1").status == TaskWorkflowStatus.COMPLETED


def test_illegal_transition_rejected() -> None:
    svc = TaskWorkflowService(org_id="org-1")
    svc.create_workflow(workflow_id="W1", task_id="T1")
    # created 不能直接到 completed
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.record_review_result(workflow_id="W1", reviewer_id="u-reviewer", approved=True)


def test_review_result_requires_human_reviewer_red_line_6() -> None:
    svc = TaskWorkflowService(org_id="org-1")
    _build_to_review(svc)
    # 不传 reviewer_id → 禁止匿名/系统代审
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.record_review_result(workflow_id="W1", reviewer_id="", approved=True)


def test_approve_method_is_forbidden() -> None:
    svc = TaskWorkflowService(org_id="org-1")
    for name in ("approve", "engineering_approved", "sign", "authorize", "auto_approve"):
        with pytest.raises(EnterpriseRedLineViolationError):
            getattr(svc, name)()  # type: ignore[attr-defined]


def test_review_actor_recorded_as_user() -> None:
    from agents.enterprise.audit import AuditService

    audit = AuditService(org_id="org-1")
    svc = TaskWorkflowService(org_id="org-1", audit=audit)
    _build_to_review(svc)
    svc.record_review_result(workflow_id="W1", reviewer_id="u-reviewer", approved=True, ts="t1")
    collab = audit.query(category=AuditActionCategory.COLLABORATION)
    review_recs = [r for r in collab if r.action == "record_review_result"]
    assert len(review_recs) == 1
    assert review_recs[0].actor_id == "u-reviewer"
    assert review_recs[0].actor_kind == AuditActorKind.USER


def test_service_construction_fail_closed(monkeypatch) -> None:
    from agents.enterprise.red_line import safety_invariants_ok

    monkeypatch.setattr("agents.enterprise.red_line.load_engineering_enabled", lambda: True)
    assert safety_invariants_ok() is False
    with pytest.raises(EnterpriseRedLineViolationError):
        TaskWorkflowService(org_id="org-1")
