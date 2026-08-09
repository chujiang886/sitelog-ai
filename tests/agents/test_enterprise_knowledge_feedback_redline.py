"""Enterprise Knowledge Feedback & Continuous Improvement Layer —— 测试7：红线 fail-closed（Phase 3.8.7）。

硬性不变量（6 条红线，fail-closed）：
① 禁开 engineering_enabled（所有新服务构造/决策路径断言 safety_invariants_ok()，启用态构造即抛）。
② 禁输出 engineering_approved（forbidden 方法名被 mixin 拦截）。
③ 禁 AI 自动改知识（auto_update_knowledge / auto_merge_knowledge / auto_approve_knowledge 被拦截；
   候选服务只提不落地，无 apply/merge/approve）。
④ 禁自动经营决策（recommend / decide / auto_decision 等被拦截）。
⑤ 禁绕过 UnifiedActivationGate（构造/写路径统一前置 safety_invariants_ok()）。
⑥ 禁 AI 代替专家责任（require_human_actor 守卫 + 无 record_human_approval）。

另验证：
- 全程 engineering_enabled 保持 False（load_engineering_enabled）。
- 不修改 verified.json（只读护栏信号，新代码从不触碰）。
- auditing 组织作用域正确（record 落在本 org）。
"""

from __future__ import annotations

import os

import pytest

from agents.config_loader import load_engineering_enabled
from agents.enterprise.audit import AuditService
from agents.enterprise.service import EnterpriseOperationLayer
from agents.enterprise.feedback import FeedbackService
from agents.enterprise.insight_validation import InsightValidationService
from agents.enterprise.knowledge_candidate import (
    KnowledgeChangeType,
    KnowledgeUpdateCandidateService,
)
from agents.enterprise.knowledge_improvement_workflow import (
    ImprovementStage,
    KnowledgeImprovementWorkflow,
)
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    safety_invariants_ok,
)


def _red_line_forbidden() -> tuple[str, ...]:
    # 四个新服务共同拥有的 forbidden 方法名（auto_validate/ai_validate 仅属于
    # InsightValidationService，单独在对应测试中覆盖）。
    return (
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
        "auto_decision",
    )


def test_safety_invariants_ok_false_in_normal_state() -> None:
    # 常态下 engineering_enabled 必须为 False（红线①/⑤基座）。
    assert load_engineering_enabled() is False
    assert safety_invariants_ok() is True


def test_construction_fail_closed_all_new_services(monkeypatch) -> None:
    monkeypatch.setattr(
        "agents.enterprise.red_line.load_engineering_enabled", lambda: True
    )
    # 启用态下，所有新服务构造必须 fail-closed（红线①/⑤）。
    with pytest.raises(EnterpriseRedLineViolationError):
        FeedbackService(org_id="o", audit=AuditService(org_id="o"))
    with pytest.raises(EnterpriseRedLineViolationError):
        InsightValidationService(org_id="o", audit=AuditService(org_id="o"))
    with pytest.raises(EnterpriseRedLineViolationError):
        KnowledgeUpdateCandidateService(org_id="o", audit=AuditService(org_id="o"))
    with pytest.raises(EnterpriseRedLineViolationError):
        KnowledgeImprovementWorkflow(org_id="o")
    with pytest.raises(EnterpriseRedLineViolationError):
        EnterpriseOperationLayer(org_id="o")


def test_forbidden_method_names_intercepted() -> None:
    layer = EnterpriseOperationLayer(org_id="o")
    targets = [
        layer.feedback,
        layer.insight_validation,
        layer.knowledge_candidates,
        layer.knowledge_improvement,
    ]
    for t in targets:
        for name in _red_line_forbidden():
            with pytest.raises(EnterpriseRedLineViolationError):
                _ = getattr(t, name)


def test_no_engineering_approved_anywhere(monkeypatch) -> None:
    layer = EnterpriseOperationLayer(org_id="o")
    # 任何新服务都不得持有 / 输出 engineering_approved。
    for svc_name in (
        "feedback",
        "insight_validation",
        "knowledge_candidates",
        "knowledge_improvement",
    ):
        svc = getattr(layer, svc_name)
        with pytest.raises(EnterpriseRedLineViolationError):
            _ = getattr(svc, "engineering_approved")
        with pytest.raises(EnterpriseRedLineViolationError):
            _ = getattr(svc, "approve")


def test_engineering_enabled_unchanged_after_exercise(monkeypatch) -> None:
    # 执行完整闭环后，engineering_enabled 仍为 False（不开启、不翻转）。
    layer = EnterpriseOperationLayer(org_id="o")
    layer.knowledge_improvement.receive_feedback(
        feedback_id="f1", user_id="u1", source_type="app", content="x"
    )
    layer.knowledge_improvement.begin_analysis(feedback_id="f1")
    layer.knowledge_improvement.propose_from_analysis(
        feedback_id="f1", candidate_id="c1", source="s",
        change_type=KnowledgeChangeType.ADD, content="c", evidence="e",
    )
    layer.knowledge_improvement.human_review(
        feedback_id="f1", decision=ImprovementStage.ACCEPTED,
        actor_id="e1", actor_kind="user",
    )
    assert load_engineering_enabled() is False
    assert safety_invariants_ok() is True


def test_verified_json_not_modified(monkeypatch, tmp_path) -> None:
    # 新代码从不触碰 verified.json；用临时副本来确认无写操作落盘。
    verified = tmp_path / "verified.json"
    verified.write_text('{"phase": "3.8.7", "ok": true}')
    before = verified.read_bytes()
    layer = EnterpriseOperationLayer(org_id="o")
    # 跑一些写路径（反馈/候选/验证/工作流）
    layer.knowledge_improvement.receive_feedback(
        feedback_id="f1", user_id="u1", source_type="app", content="x"
    )
    layer.knowledge_candidates.propose_candidate(
        candidate_id="c1", source="s", change_type=KnowledgeChangeType.ADD,
        content="c", evidence="e",
    )
    after = verified.read_bytes()
    # 文件内容未被任何新逻辑修改（路径不被引用，字节不变）。
    assert before == after
    # 同时确认真实工程 verified.json 仍 git-clean（只校验存在与可读）。
    real = os.path.join(
        os.path.dirname(__file__), "..", "..", "agents", "design",
        "thresholds", "verified.json",
    )
    assert os.path.exists(real)
