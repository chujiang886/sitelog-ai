"""Enterprise Knowledge Intelligence & Semantic Retrieval Layer —— 测试3：检索权限接入（任务6，Phase 3.8.9）。

覆盖（KnowledgeVisibilityPolicy + 引擎 filter_by_permission）：
- ADMIN 可见全部知识类型（含 "all"）。
- DESIGNER 不可见 feedback；ENGINEER 不可见 feedback；EXPERT/REVIEWER 可见 feedback。
- REVIEWER 不可见 design_spec / case。
- 未分类（空类型）默认拒绝。
- 引擎 filter_by_permission 实际按角色策略过滤。
- 默认拒绝：角色未显式授权的类型不可检索。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import AuditService
from agents.enterprise.identity import RoleKind
from agents.enterprise.knowledge_retrieval import (
    KnowledgeItem,
    KnowledgeRetrievalEngine,
)
from agents.enterprise.knowledge_visibility import KnowledgeVisibilityPolicy


def _policy(org_id: str = "org-1") -> KnowledgeVisibilityPolicy:
    return KnowledgeVisibilityPolicy(org_id=org_id)


def _item(kid: str, ktype: str) -> KnowledgeItem:
    return KnowledgeItem(
        knowledge_id=kid, title=kid, content="x", knowledge_type=ktype,
        source="manual", org_id="org-1",
    )


def test_admin_sees_all() -> None:
    p = _policy()
    for ktype in ("design_spec", "regulation", "case", "manual", "governance", "feedback"):
        assert p.is_knowledge_permitted(RoleKind.ADMIN, ktype) is True


def test_designer_cannot_see_feedback() -> None:
    p = _policy()
    assert p.is_knowledge_permitted(RoleKind.DESIGNER, "feedback") is False
    assert p.is_knowledge_permitted(RoleKind.DESIGNER, "design_spec") is True


def test_reviewer_cannot_see_design_spec() -> None:
    p = _policy()
    assert p.is_knowledge_permitted(RoleKind.REVIEWER, "design_spec") is False
    assert p.is_knowledge_permitted(RoleKind.REVIEWER, "governance") is True


def test_unknown_type_denied() -> None:
    p = _policy()
    assert p.is_knowledge_permitted(RoleKind.ADMIN, "") is False
    assert p.is_knowledge_permitted(RoleKind.EXPERT, "secret") is False


def test_engine_filter_respects_role() -> None:
    eng = KnowledgeRetrievalEngine(org_id="org-1", audit=AuditService(org_id="org-1"))
    eng.index(item=_item("k1", "design_spec"))
    eng.index(item=_item("k2", "feedback"))
    # EXPERT 可见 feedback + design_spec
    out_exp = eng.filter_by_permission(role=RoleKind.EXPERT, items=eng.list_items())
    assert {it.knowledge_id for it in out_exp} == {"k1", "k2"}
    # REVIEWER 不可见 design_spec
    out_rev = eng.filter_by_permission(role=RoleKind.REVIEWER, items=eng.list_items())
    assert [it.knowledge_id for it in out_rev] == ["k2"]


def test_visibility_policy_default_deny() -> None:
    p = _policy()
    # 任意角色对未授权类型均默认拒绝
    assert p.is_knowledge_permitted(RoleKind.ENGINEER, "feedback") is False
    assert p.is_knowledge_permitted(RoleKind.DESIGNER, "regulation") is False
