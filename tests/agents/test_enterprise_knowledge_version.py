"""Enterprise Knowledge Governance & Version Control Layer —— 测试1：知识版本模型与生命周期服务（任务1+2，Phase 3.8.8）。

覆盖（KnowledgeVersion / KnowledgeLifecycleService）：
- VersionStatus 建模（draft / reviewing / active / deprecated）。
- KnowledgeVersion 数据类（version_id / knowledge_id / version / content_hash / source /
  created_by / created_at / status）；status 初始 DRAFT；__post_init__ 强制枚举。
- create_version 只登记版本元数据（content→hash、版本号单调递增、状态恒 DRAFT），绝不写知识资产（红线③）。
- submit_review 将 DRAFT→REVIEWING（仅非权威「待审」流转）。
- 版本可追踪：同一 knowledge_id 多条版本；list_versions / active_version 过滤正确。
- forbidden 方法拦截（auto_update_knowledge / auto_publish_knowledge / auto_merge_knowledge /
  auto_approve_knowledge / publish / auto_activate / apply / merge / commit / write 等）。
- 跨组织隔离（_get_scoped）。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import AuditActionCategory, AuditActorKind, AuditService
from agents.enterprise.knowledge_version import (
    VersionStatus,
    KnowledgeVersion,
    KnowledgeLifecycleService,
)
from agents.enterprise.red_line import EnterpriseRedLineViolationError


def _svc(org_id: str = "org-1") -> KnowledgeLifecycleService:
    return KnowledgeLifecycleService(org_id=org_id, audit=AuditService(org_id=org_id))


def test_version_status_enum() -> None:
    for name, v in (
        ("DRAFT", "draft"),
        ("REVIEWING", "reviewing"),
        ("ACTIVE", "active"),
        ("DEPRECATED", "deprecated"),
    ):
        assert getattr(VersionStatus, name).value == v


def test_knowledge_version_post_init_normalizes_status() -> None:
    v = KnowledgeVersion(
        version_id="v1", knowledge_id="k1", version=1,
        content_hash="h", source="manual", created_by="u",
        status="active",
    )
    # 字符串 status 被 __post_init__ 规整为枚举
    assert v.status is VersionStatus.ACTIVE
    assert v.org_id == ""  # 默认组织隔离字段


def test_create_version_is_draft_and_hashes_content() -> None:
    svc = _svc()
    v = svc.create_version(
        version_id="v1", knowledge_id="k1", content="hello world",
        source="manual", created_by="u1",
    )
    assert isinstance(v, KnowledgeVersion)
    # 红线③：create_version 只登记元数据，状态恒 DRAFT，绝不写知识资产
    assert v.status is VersionStatus.DRAFT
    assert v.version == 1
    assert v.content_hash == svc._hash_content("hello world")
    assert v.created_by == "u1"
    assert v.org_id == "org-1"
    # 审计如实记录（AI 创建默认 AI）
    recs = svc._audit.query(category=AuditActionCategory.KNOWLEDGE_VERSION)
    assert len(recs) == 1 and recs[0].actor_kind == AuditActorKind.AI


def test_create_version_monotonic_version_number() -> None:
    svc = _svc()
    v1 = svc.create_version(version_id="v1", knowledge_id="k", content="a", source="s")
    v2 = svc.create_version(version_id="v2", knowledge_id="k", content="b", source="s")
    assert v1.version == 1
    assert v2.version == 2
    assert svc.active_version(knowledge_id="k") is None  # 尚未 active


def test_submit_review_draft_to_reviewing() -> None:
    svc = _svc()
    svc.create_version(version_id="v1", knowledge_id="k", content="a", source="s")
    v = svc.submit_review(version_id="v1")
    assert v.status is VersionStatus.REVIEWING
    # 提交复核后仍非 ACTIVE（仅标记待审，须人工激活，红线⑥）
    assert svc.active_version(knowledge_id="k") is None


def test_submit_review_only_from_draft() -> None:
    svc = _svc()
    svc.create_version(version_id="v1", knowledge_id="k", content="a", source="s")
    svc.submit_review(version_id="v1")
    with pytest.raises(ValueError):
        svc.submit_review(version_id="v1")  # 已 REVIEWING，不能重复提交


def test_list_versions_filters() -> None:
    svc = _svc()
    svc.create_version(version_id="v1", knowledge_id="k1", content="a", source="s")
    svc.create_version(version_id="v2", knowledge_id="k2", content="b", source="s")
    svc.submit_review(version_id="v1")
    assert len(svc.list_versions(knowledge_id="k1")) == 1
    assert len(svc.list_versions(status=VersionStatus.REVIEWING)) == 1
    assert len(svc.list_versions()) == 2


def test_forbidden_auto_knowledge_methods() -> None:
    svc = _svc()
    for name in (
        "auto_update_knowledge",
        "auto_publish_knowledge",
        "auto_merge_knowledge",
        "auto_approve_knowledge",
        "publish",
        "auto_activate",
        "apply",
        "merge",
        "commit",
        "write",
    ):
        with pytest.raises(EnterpriseRedLineViolationError):
            _ = getattr(svc, name)


def test_forbidden_decision_methods() -> None:
    svc = _svc()
    for name in (
        "auto_business_decision",
        "make_management_decision",
        "recommend_management_action",
        "optimize_business_strategy",
        "execute_strategy",
        "decide_operation",
        "auto_decision",
        "recommend",
        "decide",
    ):
        with pytest.raises(EnterpriseRedLineViolationError):
            _ = getattr(svc, name)


def test_cross_org_isolation() -> None:
    svc_a = _svc("org-a")
    svc_b = _svc("org-b")
    svc_a.create_version(version_id="v1", knowledge_id="k", content="a", source="s")
    from agents.enterprise.organization import EnterpriseIsolationError

    with pytest.raises(EnterpriseIsolationError):
        svc_b.get(version_id="v1")
