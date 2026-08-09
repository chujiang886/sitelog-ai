"""Enterprise Knowledge Feedback & Continuous Improvement Layer —— 测试6：权限与人工责任门禁（Phase 3.8.7）。

覆盖：跨服务的权限/人工责任守卫（红线⑥ human-gating + 红线③ 禁自动改知识 + 红线②/④/⑤）：
- 所有新服务的「人工判定」入口（feedback accept/reject/start_review、insight validation、
  workflow human_review/add_validation）必须由真实 USER 发起。
- 跨服务 forbidden 方法名（auto_update_knowledge / auto_merge_knowledge /
  auto_approve_knowledge / approve / engineering_approved / record_human_approval /
  recommend / decide …）统一被 mixin 拦截。
- 跨组织隔离：各服务按 org_id 作用域拒绝跨域读取。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import AuditActorKind, AuditService
from agents.enterprise.feedback import FeedbackService
from agents.enterprise.insight_validation import (
    InsightValidationService,
    ValidationResult,
)
from agents.enterprise.knowledge_candidate import (
    KnowledgeChangeType,
    KnowledgeUpdateCandidateService,
)
from agents.enterprise.knowledge_improvement_workflow import (
    ImprovementStage,
    KnowledgeImprovementWorkflow,
)
from agents.enterprise.organization import EnterpriseIsolationError
from agents.enterprise.red_line import EnterpriseRedLineViolationError

_FORBIDDEN = (
    "auto_update_knowledge",
    "auto_merge_knowledge",
    "auto_approve_knowledge",
    "approve",
    "engineering_approved",
    "quote",
    "pricing",
    "sign",
    "authorize",
    "record_human_approval",
    "recommend",
    "decide",
)


def _audit(org: str) -> AuditService:
    return AuditService(org_id=org)


def test_all_services_forbid_knowledge_and_decision_methods() -> None:
    svcs = [
        FeedbackService(org_id="o", audit=_audit("o")),
        InsightValidationService(org_id="o", audit=_audit("o")),
        KnowledgeUpdateCandidateService(org_id="o", audit=_audit("o")),
        KnowledgeImprovementWorkflow(org_id="o"),
    ]
    for svc in svcs:
        for name in _FORBIDDEN:
            with pytest.raises(EnterpriseRedLineViolationError):
                _ = getattr(svc, name)


def test_feedback_human_gating_across_decisions() -> None:
    svc = FeedbackService(org_id="o", audit=_audit("o"))
    svc.create_feedback(feedback_id="f1", user_id="u1", source_type="app", content="x")
    # 三个判定入口都必须 USER
    for method in ("start_review", "accept", "reject"):
        with pytest.raises(EnterpriseRedLineViolationError):
            getattr(svc, method)(
                feedback_id="f1", actor_id="ai", actor_kind=AuditActorKind.AI
            )
    svc.accept(feedback_id="f1", actor_id="e1", actor_kind=AuditActorKind.USER)
    assert svc.get(feedback_id="f1").status.value == "accepted"


def test_validation_human_gating() -> None:
    svc = InsightValidationService(org_id="o", audit=_audit("o"))
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.create_validation(
            validation_id="v1", insight_id="I-1", validator="ai",
            result=ValidationResult.VALID, actor_kind=AuditActorKind.AI,
        )
    svc.create_validation(
        validation_id="v1", insight_id="I-1", validator="e1",
        result=ValidationResult.VALID, actor_kind=AuditActorKind.USER,
    )
    assert len(svc.list_validations()) == 1


def test_workflow_human_review_gating_only_user() -> None:
    wf = KnowledgeImprovementWorkflow(org_id="o")
    wf.receive_feedback(feedback_id="f1", user_id="u1", source_type="app", content="x")
    wf.begin_analysis(feedback_id="f1")
    wf.propose_from_analysis(
        feedback_id="f1", candidate_id="c1", source="s",
        change_type=KnowledgeChangeType.ADD, content="c", evidence="e",
    )
    with pytest.raises(EnterpriseRedLineViolationError):
        wf.human_review(
            feedback_id="f1", decision=ImprovementStage.ACCEPTED,
            actor_id="ai", actor_kind="ai",
        )
    wf.human_review(
        feedback_id="f1", decision=ImprovementStage.ACCEPTED,
        actor_id="e1", actor_kind="user",
    )
    assert wf.get_case(feedback_id="f1").stage == ImprovementStage.ACCEPTED


def test_cross_org_isolation_all_services() -> None:
    a = dict(
        fb=FeedbackService(org_id="org-a", audit=_audit("org-a")),
        val=InsightValidationService(org_id="org-a", audit=_audit("org-a")),
        cand=KnowledgeUpdateCandidateService(org_id="org-a", audit=_audit("org-a")),
    )
    b = dict(
        fb=FeedbackService(org_id="org-b", audit=_audit("org-b")),
        val=InsightValidationService(org_id="org-b", audit=_audit("org-b")),
        cand=KnowledgeUpdateCandidateService(org_id="org-b", audit=_audit("org-b")),
    )
    a["fb"].create_feedback(feedback_id="f1", user_id="u1", source_type="app", content="x")
    a["val"].create_validation(
        validation_id="v1", insight_id="I-1", validator="e1",
        result=ValidationResult.VALID, actor_kind=AuditActorKind.USER,
    )
    a["cand"].propose_candidate(
        candidate_id="c1", source="s", change_type=KnowledgeChangeType.ADD,
        content="c", evidence="e",
    )
    with pytest.raises(EnterpriseIsolationError):
        b["fb"].get(feedback_id="f1")
    with pytest.raises(EnterpriseIsolationError):
        b["val"].get(validation_id="v1")
    with pytest.raises(EnterpriseIsolationError):
        b["cand"].get(candidate_id="c1")
