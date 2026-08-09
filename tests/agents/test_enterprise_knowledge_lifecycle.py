"""Enterprise Knowledge Governance & Version Control Layer —— 测试2：生命周期人工门禁与状态机（任务2，Phase 3.8.8）。

硬性 human-gating（红线⑥）：
- activate_version 必须由真实 USER 执行（require_human_actor）；AI 不得激活（禁 AI 自动 active）。
- deprecate_version 必须由真实 USER 执行；AI 不得弃用。
- 状态机约束：仅 REVIEWING 可激活；仅 ACTIVE/REVIEWING 可弃用。

审计联动：激活/弃用节点 actor_kind 强制 USER（KNOWLEDGE_VERSION 分类）。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import AuditActionCategory, AuditActorKind, AuditService
from agents.enterprise.knowledge_version import (
    VersionStatus,
    KnowledgeLifecycleService,
)
from agents.enterprise.red_line import EnterpriseRedLineViolationError


def _svc(org_id: str = "org-1") -> KnowledgeLifecycleService:
    return KnowledgeLifecycleService(org_id=org_id, audit=AuditService(org_id=org_id))


def _draft_then_reviewing(svc: KnowledgeLifecycleService, vid: str = "v1") -> None:
    svc.create_version(version_id=vid, knowledge_id="k", content="a", source="s")
    svc.submit_review(version_id=vid)


def test_activate_requires_user_actor() -> None:
    svc = _svc()
    _draft_then_reviewing(svc, "v1")
    # 红线⑥：AI 不得激活
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.activate_version(
            version_id="v1", actor_id="ai-1", actor_kind=AuditActorKind.AI
        )
    # actor_kind=None 同样被拒（require_human_actor 拒绝 None）
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.activate_version(version_id="v1", actor_id="x", actor_kind=None)


def test_activate_by_user_succeeds() -> None:
    svc = _svc()
    _draft_then_reviewing(svc, "v1")
    v = svc.activate_version(
        version_id="v1", actor_id="user-1", actor_kind=AuditActorKind.USER
    )
    assert v.status is VersionStatus.ACTIVE
    assert svc.active_version(knowledge_id="k") is v
    # 审计节点 actor_kind 强制 USER
    recs = svc._audit.query(category=AuditActionCategory.KNOWLEDGE_VERSION)
    acts = [r.action for r in recs]
    assert "activate_knowledge_version" in acts
    user_recs = [r for r in recs if r.action == "activate_knowledge_version"]
    assert user_recs[0].actor_kind == AuditActorKind.USER


def test_activate_only_from_reviewing() -> None:
    svc = _svc()
    svc.create_version(version_id="v1", knowledge_id="k", content="a", source="s")
    # 未提交复核（仍是 DRAFT）不能激活
    with pytest.raises(ValueError):
        svc.activate_version(
            version_id="v1", actor_id="user-1", actor_kind=AuditActorKind.USER
        )


def test_deprecate_requires_user_actor() -> None:
    svc = _svc()
    _draft_then_reviewing(svc, "v1")
    svc.activate_version(version_id="v1", actor_id="user-1", actor_kind=AuditActorKind.USER)
    # 红线⑥：AI 不得弃用
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.deprecate_version(
            version_id="v1", actor_id="ai-1", actor_kind=AuditActorKind.AI
        )


def test_deprecate_by_user_succeeds() -> None:
    svc = _svc()
    _draft_then_reviewing(svc, "v1")
    svc.activate_version(version_id="v1", actor_id="user-1", actor_kind=AuditActorKind.USER)
    v = svc.deprecate_version(
        version_id="v1", actor_id="user-1", actor_kind=AuditActorKind.USER
    )
    assert v.status is VersionStatus.DEPRECATED
    # 弃用后不再作为 active 版本
    assert svc.active_version(knowledge_id="k") is None
    recs = svc._audit.query(category=AuditActionCategory.KNOWLEDGE_VERSION)
    dep = [r for r in recs if r.action == "deprecate_knowledge_version"]
    assert dep and dep[0].actor_kind == AuditActorKind.USER


def test_deprecate_only_from_active_or_reviewing() -> None:
    svc = _svc()
    svc.create_version(version_id="v1", knowledge_id="k", content="a", source="s")
    # 仍 DRAFT，不能弃用
    with pytest.raises(ValueError):
        svc.deprecate_version(
            version_id="v1", actor_id="user-1", actor_kind=AuditActorKind.USER
        )


def test_full_lifecycle_trace() -> None:
    svc = _svc()
    svc.create_version(version_id="v1", knowledge_id="k", content="a", source="s")
    svc.submit_review(version_id="v1")
    svc.activate_version(version_id="v1", actor_id="u", actor_kind=AuditActorKind.USER)
    # 再发 v2 并激活，active_version 指向最新 ACTIVE
    svc.create_version(version_id="v2", knowledge_id="k", content="b", source="s")
    svc.submit_review(version_id="v2")
    svc.activate_version(version_id="v2", actor_id="u", actor_kind=AuditActorKind.USER)
    active = svc.active_version(knowledge_id="k")
    assert active is not None and active.version_id == "v2"
    # 弃用 v2 后，最早的活跃版本 v1 仍保持 ACTIVE（弃用只改变 v2 自身状态）
    svc.deprecate_version(version_id="v2", actor_id="u", actor_kind=AuditActorKind.USER)
    assert svc.active_version(knowledge_id="k") is not None
    assert svc.active_version(knowledge_id="k").version_id == "v1"
    assert svc.get(version_id="v2").status is VersionStatus.DEPRECATED
