"""Enterprise Knowledge Feedback & Continuous Improvement Layer —— 测试4：经验沉淀工作流（任务4，Phase 3.8.7）。

覆盖（KnowledgeImprovementWorkflow）：
- 状态机 feedback_received → analysis → candidate_created → human_review → accepted / rejected。
- receive_feedback / begin_analysis / propose_from_analysis 仅登记/提议（AI 可发起）。
- human_review 必须由真实 USER 发起（红线⑥：AI 不得代替人工复核判定）。
- 阶段流转守卫：各步骤必须按序，越序抛 EnterpriseRedLineViolationError。
- 候选只提不落地（red line ③，由子服务结构保证）。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import AuditActorKind
from agents.enterprise.insight_validation import ValidationResult
from agents.enterprise.knowledge_candidate import KnowledgeChangeType
from agents.enterprise.knowledge_improvement_workflow import (
    ImprovementStage,
    KnowledgeImprovementWorkflow,
)
from agents.enterprise.red_line import EnterpriseRedLineViolationError


def _wf(org_id: str = "org-1") -> KnowledgeImprovementWorkflow:
    return KnowledgeImprovementWorkflow(org_id=org_id)


def _run_happy_path(wf: KnowledgeImprovementWorkflow, *, accept: bool) -> None:
    wf.receive_feedback(
        feedback_id="f1", user_id="u1", source_type="app", content="建议导出"
    )
    wf.begin_analysis(feedback_id="f1")
    wf.propose_from_analysis(
        feedback_id="f1",
        candidate_id="c1",
        source="feedback-f1",
        change_type=KnowledgeChangeType.ADD,
        content="新增导出说明",
        evidence="feedback-f1",
    )
    decision = ImprovementStage.ACCEPTED if accept else ImprovementStage.REJECTED
    wf.human_review(
        feedback_id="f1",
        decision=decision,
        actor_id="expert-1",
        actor_kind=AuditActorKind.USER,
        comment="ok",
    )


def test_happy_path_accepted() -> None:
    wf = _wf()
    _run_happy_path(wf, accept=True)
    case = wf.get_case(feedback_id="f1")
    assert case.stage == ImprovementStage.ACCEPTED
    assert case.current_reviewer == "expert-1"
    # 反馈终态同步为 accepted
    assert wf.feedback.get(feedback_id="f1").status.value == "accepted"


def test_happy_path_rejected() -> None:
    wf = _wf()
    _run_happy_path(wf, accept=False)
    case = wf.get_case(feedback_id="f1")
    assert case.stage == ImprovementStage.REJECTED
    assert wf.feedback.get(feedback_id="f1").status.value == "rejected"


def test_human_review_requires_user() -> None:
    wf = _wf()
    wf.receive_feedback(feedback_id="f1", user_id="u1", source_type="app", content="x")
    wf.begin_analysis(feedback_id="f1")
    wf.propose_from_analysis(
        feedback_id="f1", candidate_id="c1", source="s", change_type=KnowledgeChangeType.ADD,
        content="c", evidence="e",
    )
    # AI 不得代替人工复核（红线⑥）
    with pytest.raises(EnterpriseRedLineViolationError):
        wf.human_review(
            feedback_id="f1", decision=ImprovementStage.ACCEPTED,
            actor_id="ai", actor_kind=AuditActorKind.AI,
        )


def test_begin_analysis_stage_guard() -> None:
    wf = _wf()
    wf.receive_feedback(feedback_id="f1", user_id="u1", source_type="app", content="x")
    wf.begin_analysis(feedback_id="f1")
    # 重复进入 analysis 应被拦截（须按序）
    with pytest.raises(EnterpriseRedLineViolationError):
        wf.begin_analysis(feedback_id="f1")


def test_propose_requires_analysis_stage() -> None:
    wf = _wf()
    wf.receive_feedback(feedback_id="f1", user_id="u1", source_type="app", content="x")
    # 未进入 analysis 不能直接 propose
    with pytest.raises(EnterpriseRedLineViolationError):
        wf.propose_from_analysis(
            feedback_id="f1", candidate_id="c1", source="s",
            change_type=KnowledgeChangeType.ADD, content="c", evidence="e",
        )


def test_human_review_requires_candidate_stage() -> None:
    wf = _wf()
    wf.receive_feedback(feedback_id="f1", user_id="u1", source_type="app", content="x")
    with pytest.raises(EnterpriseRedLineViolationError):
        wf.human_review(
            feedback_id="f1", decision=ImprovementStage.ACCEPTED,
            actor_id="e1", actor_kind=AuditActorKind.USER,
        )


def test_human_review_invalid_decision() -> None:
    wf = _wf()
    wf.receive_feedback(feedback_id="f1", user_id="u1", source_type="app", content="x")
    wf.begin_analysis(feedback_id="f1")
    wf.propose_from_analysis(
        feedback_id="f1", candidate_id="c1", source="s", change_type=KnowledgeChangeType.ADD,
        content="c", evidence="e",
    )
    with pytest.raises(EnterpriseRedLineViolationError):
        wf.human_review(
            feedback_id="f1", decision=ImprovementStage.ANALYSIS,  # 非 accepted/rejected
            actor_id="e1", actor_kind=AuditActorKind.USER,
        )


def test_add_validation_requires_user() -> None:
    wf = _wf()
    wf.receive_feedback(feedback_id="f1", user_id="u1", source_type="app", content="x")
    wf.begin_analysis(feedback_id="f1")
    wf.propose_from_analysis(
        feedback_id="f1", candidate_id="c1", source="s", change_type=KnowledgeChangeType.ADD,
        content="c", evidence="e",
    )
    # AI 不得验证（红线⑥）
    with pytest.raises(EnterpriseRedLineViolationError):
        wf.add_validation(
            validation_id="v1", feedback_id="f1", validator="ai",
            result=ValidationResult.VALID, actor_kind=AuditActorKind.AI,
        )
    wf.add_validation(
        validation_id="v1", feedback_id="f1", validator="expert-1",
        result=ValidationResult.VALID, actor_kind=AuditActorKind.USER,
    )
    assert len(wf.validations.list_validations()) == 1


def test_list_cases_filter() -> None:
    wf = _wf()
    _run_happy_path(wf, accept=True)
    wf.receive_feedback(feedback_id="f2", user_id="u2", source_type="email", content="y")
    accepted = wf.list_cases(stage=ImprovementStage.ACCEPTED)
    assert len(accepted) == 1 and accepted[0].feedback_id == "f1"
    all_cases = wf.list_cases()
    assert len(all_cases) == 2


def test_workflow_forbidden_methods() -> None:
    wf = _wf()
    for name in (
        "auto_update_knowledge",
        "auto_merge_knowledge",
        "auto_approve_knowledge",
        "approve",
        "engineering_approved",
        "record_human_approval",
        "recommend",
        "decide",
    ):
        with pytest.raises(EnterpriseRedLineViolationError):
            _ = getattr(wf, name)
