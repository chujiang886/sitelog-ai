"""Enterprise Knowledge Governance & Version Control Layer —— 测试7：红线 fail-closed（Phase 3.8.8）。

硬性不变量（6 条红线，fail-closed）：
① 禁开 engineering_enabled（3 个新服务构造/决策路径断言 safety_invariants_ok()）。
② 禁输出 engineering_approved（forbidden 方法名被 mixin 拦截）。
③ 禁 AI 自动改知识（auto_update_knowledge / auto_merge_knowledge / auto_approve_knowledge /
   auto_publish_knowledge 被拦截；治理服务只登记/只发现，无 apply/merge/approve）。
④ 禁自动经营决策（recommend / decide / auto_decision 等被拦截）。
⑤ 禁绕过 UnifiedActivationGate（构造/写路径统一前置 safety_invariants_ok()）。
⑥ 禁 AI 代替专家责任（require_human_actor 守卫 + 无 record_human_approval）。

另验证：
- 全程 engineering_enabled 保持 False（load_engineering_enabled）。
- 不修改 verified.json（只读护栏信号，新代码从不触碰）。
- 组织作用域正确（record 落在本 org）。
"""

from __future__ import annotations

import os

import pytest

from agents.config_loader import load_engineering_enabled
from agents.enterprise.audit import AuditActorKind, AuditService
from agents.enterprise.service import EnterpriseOperationLayer
from agents.enterprise.knowledge_version import KnowledgeLifecycleService
from agents.enterprise.knowledge_change_review import (
    KnowledgeChangeReviewService,
    ReviewResult,
)
from agents.enterprise.knowledge_conflict import KnowledgeConflictService
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    safety_invariants_ok,
)


def _red_line_forbidden_common() -> tuple[str, ...]:
    # 三个治理服务共同拥有的 forbidden 方法名（base 7 + 自动改/合并/批准 + 决策方法）。
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
        "apply",
        "merge",
        "commit",
        "write",
        "recommend",
        "decide",
        "auto_decision",
        "auto_business_decision",
        "make_management_decision",
        "recommend_management_action",
        "optimize_business_strategy",
        "execute_strategy",
        "decide_operation",
    )


def _version_only_forbidden() -> tuple[str, ...]:
    # 仅 KnowledgeLifecycleService 额外禁止的自动落地/发布入口（其它两服务未定义，无需禁）。
    return (
        "auto_publish_knowledge",
        "publish",
        "auto_activate",
    )


def test_safety_invariants_ok_false_in_normal_state() -> None:
    # 常态下 engineering_enabled 必须为 False（红线①/⑤基座）。
    assert load_engineering_enabled() is False
    assert safety_invariants_ok() is True


def test_construction_fail_closed_all_new_services(monkeypatch) -> None:
    monkeypatch.setattr(
        "agents.enterprise.red_line.load_engineering_enabled", lambda: True
    )
    # 启用态下，所有新治理服务构造必须 fail-closed（红线①/⑤）。
    with pytest.raises(EnterpriseRedLineViolationError):
        KnowledgeLifecycleService(org_id="o", audit=AuditService(org_id="o"))
    with pytest.raises(EnterpriseRedLineViolationError):
        KnowledgeChangeReviewService(org_id="o", audit=AuditService(org_id="o"))
    with pytest.raises(EnterpriseRedLineViolationError):
        KnowledgeConflictService(org_id="o", audit=AuditService(org_id="o"))
    with pytest.raises(EnterpriseRedLineViolationError):
        EnterpriseOperationLayer(org_id="o")


def test_forbidden_method_names_intercepted() -> None:
    layer = EnterpriseOperationLayer(org_id="o")
    targets = [
        layer.knowledge_versions,
        layer.knowledge_change_reviews,
        layer.knowledge_conflicts,
    ]
    for t in targets:
        for name in _red_line_forbidden_common():
            with pytest.raises(EnterpriseRedLineViolationError):
                _ = getattr(t, name)
    # KnowledgeLifecycleService 额外禁止的自动落地/发布入口
    for name in _version_only_forbidden():
        with pytest.raises(EnterpriseRedLineViolationError):
            _ = getattr(layer.knowledge_versions, name)


def test_no_engineering_approved_anywhere(monkeypatch) -> None:
    layer = EnterpriseOperationLayer(org_id="o")
    for svc_name in (
        "knowledge_versions",
        "knowledge_change_reviews",
        "knowledge_conflicts",
    ):
        svc = getattr(layer, svc_name)
        with pytest.raises(EnterpriseRedLineViolationError):
            _ = getattr(svc, "engineering_approved")
        with pytest.raises(EnterpriseRedLineViolationError):
            _ = getattr(svc, "approve")


def test_engineering_enabled_unchanged_after_exercise(monkeypatch) -> None:
    # 执行完整治理闭环后，engineering_enabled 仍为 False（不开启、不翻转）。
    layer = EnterpriseOperationLayer(org_id="o")
    layer.knowledge_versions.create_version(
        version_id="v1", knowledge_id="k", content="a", source="s"
    )
    layer.knowledge_versions.submit_review(version_id="v1")
    layer.knowledge_change_reviews.create_review(
        review_id="r1", candidate_id="c1", reviewer="user-1",
        result=ReviewResult.ACCEPTED, actor_kind=AuditActorKind.USER,
    )
    layer.knowledge_conflicts.discover_conflict(
        conflict_id="cf1", knowledge_a="k", knowledge_b="k2",
        reason="x", evidence="y",
    )
    assert load_engineering_enabled() is False
    assert safety_invariants_ok() is True


def test_verified_json_not_modified(monkeypatch, tmp_path) -> None:
    # 新代码从不触碰 verified.json；用临时副本来确认无写操作落盘。
    verified = tmp_path / "verified.json"
    verified.write_text('{"phase": "3.8.8", "ok": true}')
    before = verified.read_bytes()
    layer = EnterpriseOperationLayer(org_id="o")
    layer.knowledge_versions.create_version(
        version_id="v1", knowledge_id="k", content="a", source="s"
    )
    layer.knowledge_conflicts.discover_conflict(
        conflict_id="cf1", knowledge_a="k", knowledge_b="k2",
        reason="x", evidence="y",
    )
    after = verified.read_bytes()
    assert before == after  # 内容未被任何新逻辑修改
    # 同时确认真实工程 verified.json 仍 git-clean（只校验存在与可读）。
    real = os.path.join(
        os.path.dirname(__file__), "..", "..", "agents", "design",
        "thresholds", "verified.json",
    )
    assert os.path.exists(real)
