"""Enterprise Knowledge Feedback & Continuous Improvement Layer —— 测试1：用户反馈（任务1，Phase 3.8.7）。

覆盖（FeedbackService）：
- FeedbackRecord / FeedbackStatus 建模（submitted / reviewing / accepted / rejected）。
- create_feedback 默认 status=submitted，审计如实记录（category=FEEDBACK，actor 默认 AI）。
- get / list_feedbacks 按 source_type / status 过滤；跨域访问抛 EnterpriseIsolationError。
- start_review / accept / reject 必须由真实 USER 发起（红线⑥：AI 不得代替人工判定）。
- 不持有 auto_update_knowledge / approve 等 forbidden 方法（红线②/③/④/⑥）。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import AuditActionCategory, AuditActorKind, AuditService
from agents.enterprise.feedback import FeedbackRecord, FeedbackService, FeedbackStatus
from agents.enterprise.identity import RoleKind
from agents.enterprise.red_line import EnterpriseRedLineViolationError


def _svc(org_id: str = "org-1") -> FeedbackService:
    return FeedbackService(org_id=org_id, audit=AuditService(org_id=org_id))


def test_feedback_status_enum() -> None:
    assert FeedbackStatus.SUBMITTED.value == "submitted"
    assert FeedbackStatus.REVIEWING.value == "reviewing"
    assert FeedbackStatus.ACCEPTED.value == "accepted"
    assert FeedbackStatus.REJECTED.value == "rejected"


def test_create_feedback_default_submitted() -> None:
    svc = _svc()
    rec = svc.create_feedback(
        feedback_id="f1", user_id="u1", source_type="app", content="建议增加导出"
    )
    assert isinstance(rec, FeedbackRecord)
    assert rec.status == FeedbackStatus.SUBMITTED
    assert rec.org_id == "org-1"
    assert rec.source_type == "app"


def test_create_feedback_audit_default_ai() -> None:
    svc = _svc()
    svc.create_feedback(feedback_id="f1", user_id="u1", source_type="app", content="x")
    recs = svc._audit.query(category=AuditActionCategory.FEEDBACK)
    assert len(recs) == 1
    assert recs[0].actor_kind == AuditActorKind.AI  # AI 提交记 AI（红线⑥）
    assert recs[0].action == "submit_feedback"


def test_get_and_list_filters() -> None:
    svc = _svc()
    svc.create_feedback(feedback_id="f1", user_id="u1", source_type="app", content="x")
    svc.create_feedback(feedback_id="f2", user_id="u2", source_type="email", content="y")
    assert svc.get(feedback_id="f1").feedback_id == "f1"
    by_src = svc.list_feedbacks(source_type="app")
    assert len(by_src) == 1 and by_src[0].feedback_id == "f1"
    by_status = svc.list_feedbacks(status=FeedbackStatus.SUBMITTED)
    assert len(by_status) == 2


def test_start_review_requires_human(monkeypatch) -> None:
    svc = _svc()
    svc.create_feedback(feedback_id="f1", user_id="u1", source_type="app", content="x")
    # AI 不得发起审核（红线⑥）
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.start_review(feedback_id="f1", actor_id="ai", actor_kind=AuditActorKind.AI)
    # 真实 USER 可发起
    rec = svc.start_review(
        feedback_id="f1", actor_id="expert-1", actor_kind=AuditActorKind.USER
    )
    assert rec.status == FeedbackStatus.REVIEWING


def test_accept_requires_human_and_sets_status() -> None:
    svc = _svc()
    svc.create_feedback(feedback_id="f1", user_id="u1", source_type="app", content="x")
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.accept(feedback_id="f1", actor_id="ai", actor_kind="ai")
    rec = svc.accept(
        feedback_id="f1", actor_id="expert-1", actor_kind="user", comment="采纳"
    )
    assert rec.status == FeedbackStatus.ACCEPTED
    recs = svc._audit.query(category=AuditActionCategory.FEEDBACK, target="f1")
    assert any(r.action == "accept_feedback" and r.actor_kind == AuditActorKind.USER for r in recs)


def test_reject_requires_human_and_sets_status() -> None:
    svc = _svc()
    svc.create_feedback(feedback_id="f1", user_id="u1", source_type="app", content="x")
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.reject(feedback_id="f1", actor_id="ai", actor_kind=AuditActorKind.AI)
    rec = svc.reject(feedback_id="f1", actor_id="expert-1", actor_kind=AuditActorKind.USER)
    assert rec.status == FeedbackStatus.REJECTED


def test_role_param_accepted_but_org_scoped() -> None:
    # role 参数保留以对齐聚合层约定；反馈按组织作用域返回，不做角色隐藏。
    svc = _svc()
    svc.create_feedback(feedback_id="f1", user_id="u1", source_type="app", content="x")
    assert len(svc.list_feedbacks(role=RoleKind.ADMIN)) == 1
    assert len(svc.list_feedbacks(role=RoleKind.ENGINEER)) == 1


def test_cross_org_isolation() -> None:
    svc_a = _svc("org-a")
    svc_b = _svc("org-b")
    svc_a.create_feedback(feedback_id="f1", user_id="u1", source_type="app", content="x")
    from agents.enterprise.organization import EnterpriseIsolationError

    with pytest.raises(EnterpriseIsolationError):
        svc_b.get(feedback_id="f1")


def test_feedback_forbidden_methods() -> None:
    # 红线②/③/④/⑥：反馈服务不得持有批准/报价/审批/自动改知识等方法。
    svc = _svc()
    for name in (
        "approve",
        "engineering_approved",
        "quote",
        "pricing",
        "sign",
        "authorize",
        "record_human_approval",
        "auto_update_knowledge",
        "auto_merge_knowledge",
        "auto_approve_knowledge",
        "recommend",
        "decide",
    ):
        with pytest.raises(EnterpriseRedLineViolationError):
            _ = getattr(svc, name)
